"""E10 S10.13 — capability kind + idempotency drive retry behaviour.

A non-idempotent effect must not be retried (re-running could double-apply it);
a read/idempotent capability may be retried within its attempt budget.
"""
from __future__ import annotations

from core.bootstrap import build_kernel
from middleware import Retry
from middleware.retry import _retryable

ECHO = {"features": {"example_echo": {"enabled": True, "module": "features.example_echo"}}}


class CountingTool:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return {"ok": False, "error": "transient failure"}


def _kernel_with_retry(attempts: int = 3):
    kernel = build_kernel(ECHO)
    kernel.use(Retry(attempts=attempts))
    return kernel


# ── unit: the retry predicate ────────────────────────────────────────────────
def test_retryable_predicate():
    assert _retryable({"metadata": {"kind": "read", "idempotent": True}}) is True
    assert _retryable({"metadata": {"kind": "effect", "idempotent": False}}) is False
    assert _retryable({"metadata": {"policy_block": True}}) is False
    assert _retryable({"metadata": {}}) is True  # unknown -> retryable (backward compatible)


# ── integration: kernel stamps kind, Retry honours it ────────────────────────
def test_effect_not_retried():
    kernel = _kernel_with_retry()
    tool = CountingTool("effect_tool")
    kernel.registry.register_tool("effect_tool", tool, kind="effect", idempotent=False)
    kernel.execute_tool("effect_tool", {})
    assert tool.calls == 1  # side-effect never re-applied


def test_idempotent_read_retried():
    kernel = _kernel_with_retry(attempts=3)
    tool = CountingTool("read_tool")
    kernel.registry.register_tool("read_tool", tool, kind="read", idempotent=True)
    kernel.execute_tool("read_tool", {})
    assert tool.calls == 3  # retried within the attempt budget


def test_plain_tool_retries_unchanged():
    # default kind="tool" keeps the pre-S3 retry behaviour (no regression)
    kernel = _kernel_with_retry(attempts=3)
    tool = CountingTool("plain")
    kernel.registry.register_tool("plain", tool)
    kernel.execute_tool("plain", {})
    assert tool.calls == 3


def test_kind_in_envelope_metadata():
    kernel = build_kernel(ECHO)
    tool = CountingTool("probe")
    kernel.registry.register_tool("probe", tool, kind="effect", idempotent=False, risk="high")
    env = kernel.execute_tool("probe", {})
    assert env["metadata"]["kind"] == "effect"
    assert env["metadata"]["idempotent"] is False
    assert env["metadata"]["risk"] == "high"
