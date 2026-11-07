"""Host-side chat-completions transport. Credentials never enter task environments."""
from __future__ import annotations

import asyncio
import ipaddress
import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .contracts import Reply, Usage, canonical


class ContextLimit(RuntimeError):
    """Request rejected locally before a generation request or token reservation."""


class ChatModel:
    def __init__(self, base_url, api_key, model, *, temperature=0.0, max_output_tokens=4096,
                 seed=None, input_usd_per_million=None, output_usd_per_million=None, timeout_s=120, allow_private_http=False,
                 tokenizer_preflight=False, context_policy="stop", artifact_identity=None):
        url = urlsplit(base_url)
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("Model URL must not contain credentials, query or fragment")
        private_http = False
        if allow_private_http:
            try:
                private_http = ipaddress.ip_address(url.hostname).is_private
            except ValueError:
                pass
        if url.scheme != "https" and not (url.scheme == "http" and (url.hostname in {"127.0.0.1", "localhost", "::1"} or private_http)):
            raise ValueError("Use HTTPS or a loopback model endpoint")
        if not api_key or not model:
            raise ValueError("A model and a securely supplied key are required")
        self.url, self._key = base_url.rstrip("/") + "/chat/completions", api_key
        self.model, self.timeout = model, timeout_s
        self.parameters = {"temperature": temperature, "max_tokens": max_output_tokens}
        if seed is not None:
            self.parameters["seed"] = seed
        self.rates = (input_usd_per_million, output_usd_per_million)
        if context_policy not in {"stop", "shorten_old_tool_observations"}:
            raise ValueError("Unsupported context policy")
        if context_policy != "stop" and not tokenizer_preflight:
            raise ValueError("Observation shortening requires an exact serving tokenizer")
        self.tokenizer_url = base_url.rstrip("/").removesuffix("/v1") + "/tokenize" if tokenizer_preflight else None
        self.context_policy = context_policy
        self.identity = {"adapter": "chat-completions", "endpoint": base_url, "model": model, "parameters": self.parameters,
                         "input_usd_per_million": input_usd_per_million, "output_usd_per_million": output_usd_per_million,
                         "allow_private_http": allow_private_http, "tokenizer_preflight": tokenizer_preflight,
                         "context_policy": context_policy, "artifact_identity": artifact_identity}

    async def prepare(self, messages, tools):
        if not self.tokenizer_url:
            return None
        def count():
            body = {"model": self.model, "messages": messages, "tools": tools, "add_generation_prompt": True}
            request = urllib.request.Request(self.tokenizer_url, data=canonical(body).encode(), headers={
                "Authorization": "Bearer " + self._key, "Content-Type": "application/json"})
            # Tokenizer and generation requests use the same no-redirect policy.
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None
            with urllib.request.build_opener(NoRedirect).open(request, timeout=self.timeout) as response:
                return json.load(response)
        shortened = []
        while True:
            result = await asyncio.to_thread(count)
            count_value, maximum = result["count"], result["max_model_len"]
            if count_value + self.parameters["max_tokens"] <= maximum:
                return {"prompt_tokens": count_value, "max_model_len": maximum,
                        "max_output_tokens": self.parameters["max_tokens"],
                        "reservation_tokens": count_value + self.parameters["max_tokens"],
                        "shortened_tool_messages": shortened}
            candidates = [(i, m) for i, m in enumerate(messages) if m["role"] == "tool" and len(m.get("content") or "") > 512]
            if self.context_policy == "stop" or not candidates:
                raise ContextLimit(f"Prompt {count_value} + output allowance {self.parameters['max_tokens']} exceeds context {maximum}")
            index, message = candidates[0]
            content = message["content"];keep = max(128, len(content) // 4)
            messages[index] = {**message, "content": content[:keep] + "\n[Earlier tool observation shortened by the common context policy; original output retained in trajectory.]\n" + content[-keep:]}
            shortened.append(index)

    async def complete(self, messages, tools, *, role):
        return await asyncio.to_thread(self._complete, messages, tools)

    def _complete(self, messages, tools):
        body = {"model": self.model, "messages": messages, **self.parameters}
        if tools:
            body["tools"] = tools
        request = urllib.request.Request(self.url, data=canonical(body).encode("utf-8"), headers={
            "Authorization": "Bearer " + self._key, "Content-Type": "application/json"})

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=self.timeout) as response:
                data = json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"Model HTTP {error.code}; usage unknown") from None
        choice = data["choices"][0]
        usage = data["usage"]  # Missing usage is a validity error, never silently zero.
        cost = None
        if all(rate is not None for rate in self.rates):
            # A flat rate is an explicit user-provided accounting convention, not a provider bill.
            cost = (usage["prompt_tokens"] * self.rates[0] + usage["completion_tokens"] * self.rates[1]) / 1_000_000
        message = {k: v for k, v in choice["message"].items() if k in {"role", "content", "tool_calls", "reasoning_content"}}
        message["role"] = "assistant"
        return Reply(message, Usage(usage["prompt_tokens"], usage["completion_tokens"], cost), data.get("model", self.model), choice.get("finish_reason", "unknown"))
