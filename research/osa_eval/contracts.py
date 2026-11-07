from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def public_id(value: str) -> str:
    return "id-" + digest({"protocol_identifier": value})[:24]


def model_event(event) -> dict:
    return {**event.__dict__, "id": public_id(event.id), "thread": public_id(event.thread),
            "task_id": public_id(event.task_id or event.id)}


def mask_protocol_ids(value, events):
    mapping = {identifier: public_id(identifier) for event in events for identifier in [event.id, event.thread, event.task_id or event.id]}
    natural_fields = {"text", "content", "scope", "summary", "title", "reason", "instruction"}
    def walk(item, key=None):
        if key in natural_fields:
            return item
        if isinstance(item, dict):
            return {k: walk(v, k) for k, v in item.items()}
        if isinstance(item, list):
            return [walk(v) for v in item]
        return mapping.get(item, item) if isinstance(item, str) else item
    return walk(value)


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cost_usd: float | None = None

    def __post_init__(self):
        if any(type(v) is not int or v < 0 for v in (self.input_tokens, self.output_tokens)):
            raise ValueError("Provider usage must contain nonnegative integer token counts")
        if self.cost_usd is not None and (not math.isfinite(self.cost_usd) or self.cost_usd < 0):
            raise ValueError("Cost must be finite and nonnegative")

    @property
    def tokens(self):
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class Reply:
    message: dict
    usage: Usage
    model: str
    finish_reason: str = "stop"


@dataclass(frozen=True)
class Event:
    id: str
    thread: str
    text: str
    arrival_s: float = 0.0
    task_id: str | None = None
    kind: str = "request"

    def __post_init__(self):
        if not self.id or not self.thread or not self.text:
            raise ValueError("Events require id, thread and text")
        if not math.isfinite(self.arrival_s) or self.arrival_s < 0:
            raise ValueError("Arrival time must be finite and nonnegative")
        if self.kind not in {"request", "followup", "context"}:
            raise ValueError("Unsupported event kind")


class Model(Protocol):
    identity: dict
    async def complete(self, messages: list[dict], tools: list[dict], *, role: str) -> Reply: ...


class Workspace(Protocol):
    """Commands run exclusively in a benchmark-owned environment."""
    identity: dict
    async def execute(self, command: str, timeout_s: float) -> dict: ...


@dataclass(frozen=True)
class Limits:
    slots: int = 4
    model_concurrency: int = 4
    token_budget: int = 1_000_000
    # Legacy fallback; exact policy uses the serving tokenizer plus max output.
    request_token_reservation: int = 131_072
    reservation_policy: str = "context_window"
    max_steps: int = 100
    tool_timeout_s: float = 60
    task_timeout_s: float = 3000

    def __post_init__(self):
        if self.reservation_policy not in {"context_window", "exact_prompt_plus_max_output"}:
            raise ValueError("Unknown token reservation policy")
        for name in ("slots", "model_concurrency", "token_budget", "request_token_reservation", "max_steps"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("tool_timeout_s", "task_timeout_s"):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive and finite")

    def public(self):
        return asdict(self)
