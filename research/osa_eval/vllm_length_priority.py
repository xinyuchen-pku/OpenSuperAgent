"""Task-owned, hash-pinned vLLM 0.20 Chat API compatibility launcher.

Backports length priority from upstream PR59324 for the two full-response
branches and the streaming branch used by this deployment. Installed packages
are never written. This does not implement the other changes in that PR.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

EXPECTED_SHA256 = "50b0eacd6acd4cfdaf1aa69a765be9c1bf1c3fac993cfdb95d9ef413a0be884e"
UPSTREAM = "https://github.com/vllm-project/vllm/pull/59324"


def transformed_methods(raw: bytes) -> tuple[list[ast.AsyncFunctionDef], dict]:
    actual = hashlib.sha256(raw).hexdigest()
    if actual != EXPECTED_SHA256:
        raise RuntimeError(f"Unsupported vLLM serving source: {actual}")
    tree = ast.parse(raw.decode("utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == "OpenAIServingChat")
    methods = [copy.deepcopy(n) for n in cls.body
               if isinstance(n, ast.AsyncFunctionDef) and n.name in {
                   "chat_completion_full_generator", "chat_completion_stream_generator"}]
    assert len(methods) == 2 and all(not n.decorator_list for n in methods)
    expressions, stream_branches = [], []

    class Fix(ast.NodeTransformer):
        full = 0
        stream = 0

        def visit_keyword(self, node):
            if node.arg == "finish_reason" and isinstance(node.value, ast.IfExp) and any(
                isinstance(n, ast.Constant) and n.value == "tool_calls"
                for n in ast.walk(node.value)
            ):
                old = node.value
                node.value = ast.IfExp(
                    test=ast.parse("output.finish_reason == 'length'", mode="eval").body,
                    body=ast.Constant("length"), orelse=old)
                expressions.append((copy.deepcopy(old), copy.deepcopy(node.value)))
                self.full += 1
            return node

        def visit_If(self, node):
            self.generic_visit(node)
            if any(isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
                   and n.value.value == "tool_calls" and any(
                       isinstance(t, ast.Name) and t.id == "finish_reason_" for t in n.targets)
                   for n in node.body):
                new = ast.If(
                    test=ast.parse("output.finish_reason == 'length'", mode="eval").body,
                    body=[ast.Assign(targets=[ast.Name(id="finish_reason_", ctx=ast.Store())],
                                     value=ast.Constant("length"))], orelse=[node])
                stream_branches.append((copy.deepcopy(node), copy.deepcopy(new)))
                self.stream += 1
                return ast.copy_location(new, node)
            return node

    fix = Fix()
    for method in methods:
        fix.visit(method)
        ast.fix_missing_locations(method)
    assert (fix.full, fix.stream) == (2, 1), (fix.full, fix.stream)
    checked = 0
    # Compare actual old/new expressions and streaming branch over engine-stop
    # conditions and tool-parser states. Every non-length outcome must agree.
    for reason in (None, "stop", "length", "abort"):
        for called in (False, True):
            for harmony in (False, True):
                scope = dict(output=SimpleNamespace(finish_reason=reason),
                             is_finish_reason_tool_calls=called,
                             tool_call_info=SimpleNamespace(tools_called=called),
                             auto_tools_called=called, tools_streamed=[called],
                             tool_choice_function_name=None, i=0,
                             self=SimpleNamespace(use_harmony=harmony),
                             harmony_tools_streamed=[called])
                for old, new in expressions:
                    a = eval(compile(ast.fix_missing_locations(ast.Expression(old)), "old", "eval"), scope)
                    b = eval(compile(ast.fix_missing_locations(ast.Expression(new)), "new", "eval"), scope)
                    assert b == ("length" if reason == "length" else a)
                    checked += 1
                for old, new in stream_branches:
                    a, b = dict(scope), dict(scope)
                    exec(compile(ast.fix_missing_locations(ast.Module([old], [])), "old", "exec"), a)
                    exec(compile(ast.fix_missing_locations(ast.Module([new], [])), "new", "exec"), b)
                    assert b["finish_reason_"] == ("length" if reason == "length" else a["finish_reason_"])
                    checked += 1
    receipt = dict(original_module_sha256=actual, changed_full_branches=fix.full,
                   changed_stream_branches=fix.stream, contract_cases_passed=checked,
                   patched_ast_sha256=hashlib.sha256(ast.dump(ast.Module(methods, [])).encode()).hexdigest(),
                   upstream_reference=UPSTREAM, installed_package_files_modified=False)
    return methods, receipt


def install() -> dict:
    # Avoid shadowing unrelated packages with this launcher's directory.
    here = str(Path(__file__).resolve().parent)
    sys.path[:] = [p for p in sys.path if str(Path(p or ".").resolve()) != here]
    module = importlib.import_module("vllm.entrypoints.openai.chat_completion.serving")
    methods, receipt = transformed_methods(Path(module.__file__).read_bytes())
    namespace = dict(vars(module))
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    code = ast.fix_missing_locations(ast.Module(body=[future, *methods], type_ignores=[]))
    exec(compile(code, str(Path(__file__).resolve()), "exec"), namespace)
    for method in methods:
        original = getattr(module.OpenAIServingChat, method.name)
        assert not original.__code__.co_freevars
        replacement = namespace[method.name]
        replacement.__qualname__ = original.__qualname__
        setattr(module.OpenAIServingChat, method.name, replacement)
    receipt.update(bootstrap_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   vllm_version=importlib.import_module("vllm").__version__)
    if target := os.environ.get("OSA_VLLM_COMPAT_RECEIPT"):
        Path(target).write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print("OSA_VLLM_COMPAT=" + json.dumps(receipt), flush=True)
    return receipt


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--contract-check":
        _, receipt = transformed_methods(Path(sys.argv[2]).read_bytes())
        print(json.dumps(receipt))
    else:
        install()
        runpy.run_module("vllm.entrypoints.openai.api_server", run_name="__main__", alter_sys=True)
