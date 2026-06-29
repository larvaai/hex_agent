"""Real local-LLM adapter behind the `LLM` port (Slice 2).

Targets any OpenAI-compatible chat endpoint — LM Studio (`http://localhost:1234/v1`)
or a llama.cpp server. Pure stdlib (`urllib`), no third-party deps.

The model is asked to return a strict JSON object (plan + DelegationDecision).
Local models are unreliable about that, so the adapter:
  1. extracts JSON even when wrapped in ```fences``` or prose,
  2. normalizes/validates the shape,
  3. on failure, makes ONE stricter repair call,
  4. if still unusable, returns a safe `solo` fallback (observable via `_meta`)
     so the orchestrator degrades gracefully instead of crashing.

None of this touches the core: the orchestrator and the Slice 1 tests are
unchanged. `RecordedLLM` replays canned responses through the *same* parsing
path, giving a deterministic end-to-end test of the real-LLM plumbing.
"""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Callable, Optional

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_VALID_MODES = {"solo", "delegate"}


class LLMFormatError(ValueError):
    """The model output could not be coerced into a plan + decision."""


# --------------------------------------------------------------------------- #
# JSON extraction / coercion
# --------------------------------------------------------------------------- #
def _first_balanced_object(s: str) -> Optional[str]:
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of a model reply (fenced or prose-wrapped)."""
    if not text:
        return None
    candidates: list[str] = []
    fence = _FENCE.search(text)
    if fence:
        candidates.append(fence.group(1))
    candidates.append(text)
    for c in candidates:
        obj = _first_balanced_object(c)
        if obj is not None:
            try:
                data = json.loads(obj)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
    return None


def _normalize_steps(steps) -> list:
    out = []
    if isinstance(steps, list):
        for i, s in enumerate(steps):
            if isinstance(s, dict) and "description" in s:
                out.append({
                    "id": str(s.get("id", f"s{i + 1}")),
                    "description": str(s["description"]),
                    "status": s.get("status", "pending"),
                })
            elif isinstance(s, str):
                out.append({"id": f"s{i + 1}", "description": s, "status": "pending"})
    return out


def coerce_response(raw: str) -> dict:
    """Parse a raw model reply into the `{"plan":..., "decision":...}` contract.

    Raises LLMFormatError if no usable decision can be recovered.
    """
    data = extract_json(raw)
    if not isinstance(data, dict):
        raise LLMFormatError("no JSON object found in model output")

    # a tool action is a valid non-terminal step
    action = data.get("action")
    if isinstance(action, dict) and action.get("type") == "tool":
        tool = action.get("tool")
        if not isinstance(tool, str) or not tool:
            raise LLMFormatError("tool action without a tool name")
        args = action.get("args") if isinstance(action.get("args"), dict) else {}
        return {"action": {"type": "tool", "tool": tool, "args": args}}

    decision = data.get("decision")
    if not isinstance(decision, dict) or decision.get("mode") not in _VALID_MODES:
        raise LLMFormatError(f"invalid or missing decision: {decision!r}")
    if decision["mode"] == "delegate" and not decision.get("target"):
        raise LLMFormatError("delegate decision without a target role")

    plan = data.get("plan") if isinstance(data.get("plan"), dict) else {}
    return {
        "plan": {"steps": _normalize_steps(plan.get("steps")), "next": plan.get("next")},
        "decision": {
            "mode": decision["mode"],
            "target": decision.get("target"),
            "subtask": decision.get("subtask"),
            "reasoning": decision.get("reasoning", ""),
        },
    }


def coerce_triage(raw: str) -> dict:
    """Parse a model triage reply into {"triage": {kind, text?|goal?+done_when?, reasoning}}.

    Total + pure: NEVER raises. Unparseable / unclassifiable output falls back to treating the
    whole reply as an answer (observable via a `_meta.fallback` marker) — the orchestrator's
    CODE still adjudicates any done_when, so a hallucinated criterion can't sneak through here.
    """
    data = extract_json(raw)
    node = None
    if isinstance(data, dict):
        node = data.get("triage") if isinstance(data.get("triage"), dict) else data
    if not isinstance(node, dict) or node.get("kind") not in ("answer", "task"):
        return {"triage": {"kind": "answer", "text": (raw or "").strip()}, "_meta": {"fallback": True}}
    if node["kind"] == "task":
        triage = {"kind": "task", "goal": node.get("goal"),
                  "done_when": list(node.get("done_when") or []), "reasoning": node.get("reasoning", "")}
    else:
        triage = {"kind": "answer", "text": node.get("text"), "reasoning": node.get("reasoning", "")}
    return {"triage": triage}


def solo_fallback(reason: str) -> dict:
    """Safe default when the model output is unrecoverable — observable via _meta."""
    return {
        "plan": {"steps": [], "next": None},
        "decision": {"mode": "solo", "target": None, "subtask": None, "reasoning": f"fallback: {reason}"},
        "_meta": {"fallback": True, "reason": reason},
    }


# --------------------------------------------------------------------------- #
# Prompting
# --------------------------------------------------------------------------- #
_SYSTEM = (
    "You are an agent inside a multi-agent orchestrator. At your plan step you "
    "MUST return ONLY a JSON object (no prose, no markdown) with this shape:\n"
    '{"plan": {"steps": [{"id": "s1", "description": "..."}], "next": "<short next step or null>"}, '
    '"decision": {"mode": "solo|delegate", "target": "<role to delegate to, required if delegate>", '
    '"subtask": "<subtask text, required if delegate>"}}\n'
    "Use mode=delegate only when another role should own a subtask; otherwise mode=solo.\n"
    'To gather information first, return a tool action instead: '
    '{"action": {"type": "tool", "tool": "<name>", "args": {...}}}. '
    "After tools, return your final plan+decision."
)


def build_messages(ctx: dict, roles: Optional[list] = None, strict: bool = False) -> list:
    parts = [f"Your role: {ctx['role']}."]
    if roles:
        parts.append(f"Available roles to delegate to: {', '.join(roles)}.")
    tools = ctx.get("tools")
    if tools:
        parts.append(f"Available tools: {', '.join(tools)}.")
    observations = ctx.get("observations")
    if observations:
        parts.append("Tool results so far:")
        for o in observations:
            status = "ok" if o.get("ok") else "error"
            body = str(o.get("output") or o.get("error") or "")[:400]
            parts.append(f"- {o.get('tool')} [{status}]: {body}")
    parts.append(f"Task: {ctx['task']}")
    parts.append(f"Depth in tree: {ctx.get('depth', 0)}.")
    parts.append("Return the JSON object now (a tool action, or your final plan+decision).")
    user = "\n".join(parts)
    system = _SYSTEM
    if strict:
        system += "\nIMPORTANT: your previous reply was not valid JSON. Return ONLY the raw JSON object, nothing else."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


_TRIAGE_SYSTEM = (
    "You are the entry worker of an agent runtime. Classify the user's input, then return ONLY a "
    "JSON object (no prose, no markdown):\n"
    '{"kind": "answer|task", '
    '"text": "<direct answer, when kind=answer>", '
    '"goal": "<one-line goal, when kind=task>", '
    '"done_when": [{"check": "file_exists", "params": {}, "artifact": "relative/path"}]}\n'
    "kind=answer for a question you can answer directly in text. kind=task when the user wants work "
    "done that yields a verifiable artifact. Each done_when is a typed triple {check, params, "
    "artifact} — a QUESTION the gate answers, never a verdict. NEVER include a passed/status/score "
    "field; the gate writes the verdict, not you."
)


def build_triage_messages(ctx: dict, strict: bool = False) -> list:
    system = _TRIAGE_SYSTEM
    if strict:
        system += "\nIMPORTANT: your previous reply was not valid JSON. Return ONLY the raw JSON object."
    user = f"Classify this input and return the JSON object now:\n{ctx.get('input', '')}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


_LENS_SYSTEM = (
    "You are ONE lens in a multi-lens advisory. Answer the question from your single angle in ONE "
    "short line of prose. You ADVISE only — never a verdict, never JSON, never a passed/status/score "
    "field. The agent decides; you only add a perspective."
)


def build_lens_messages(ctx: dict) -> list:
    """A lens prompt: the lens question + the situation + any upstream lens lines, verbatim. A lens
    returns prose (one line), NOT JSON — so there is no repair ladder, just first-non-empty-line."""
    parts = [ctx.get("prompt", "")]
    inp = ctx.get("input")
    if inp:
        parts.append("Situation:")
        parts.append(inp if isinstance(inp, str) else json.dumps(inp, ensure_ascii=False))
    upstream = ctx.get("upstream") or {}
    if upstream:
        parts.append("Upstream lens notes:")
        parts.extend(f"- {lid}: {line}" for lid, line in upstream.items())
    parts.append("Answer in ONE short line (prose, no JSON).")
    user = "\n".join(p for p in parts if p)
    return [{"role": "system", "content": _LENS_SYSTEM}, {"role": "user", "content": user}]


def _first_nonempty_line(raw: str) -> str:
    for line in (raw or "").splitlines():
        if line.strip():
            return line.strip()
    return (raw or "").strip()


# --------------------------------------------------------------------------- #
# Transport
# --------------------------------------------------------------------------- #
def http_transport(base_url: str, api_key: str, model: str, temperature: float = 0.2, timeout: float = 60.0) -> Callable[[list], str]:
    """Build an OpenAI-compatible /chat/completions caller (stdlib urllib)."""

    def transport(messages: list) -> str:
        url = base_url.rstrip("/") + "/chat/completions"
        body = json.dumps({"model": model, "messages": messages, "temperature": temperature, "stream": False}).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
        return payload["choices"][0]["message"]["content"]

    return transport


# --------------------------------------------------------------------------- #
# Adapters (implement the LLM port: .complete(ctx) -> dict)
# --------------------------------------------------------------------------- #
class OpenAICompatLLM:
    """Drive a real local model. `transport` is injectable for tests."""

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        model: str = "local-model",
        api_key: str = "lm-studio",
        roles: Optional[list] = None,
        temperature: float = 0.2,
        timeout: float = 60.0,
        transport: Optional[Callable[[list], str]] = None,
    ) -> None:
        self.roles = list(roles) if roles else None
        self._transport = transport or http_transport(base_url, api_key, model, temperature, timeout)
        self.last_meta: dict = {}

    def complete(self, ctx: dict) -> dict:
        if ctx.get("request") == "triage":
            return self._complete_triage(ctx)
        if ctx.get("request") == "lens":
            return self._complete_lens(ctx)
        raw = self._transport(build_messages(ctx, self.roles, strict=False))
        try:
            out = coerce_response(raw)
            self.last_meta = {"repaired": False, "fallback": False}
            return out
        except LLMFormatError:
            pass
        # one stricter repair attempt
        raw2 = self._transport(build_messages(ctx, self.roles, strict=True))
        try:
            out = coerce_response(raw2)
            self.last_meta = {"repaired": True, "fallback": False}
            return out
        except LLMFormatError as e:
            self.last_meta = {"repaired": True, "fallback": True}
            return solo_fallback(str(e))

    def _complete_triage(self, ctx: dict) -> dict:
        """Triage variant of the parse/repair ladder: coerce_triage never raises, so the fallback
        is signalled by a `_meta` marker rather than an exception. One stricter repair call, then
        the safe answer-fallback — the same graceful-degradation contract as the plan path."""
        out = coerce_triage(self._transport(build_triage_messages(ctx, strict=False)))
        if "_meta" not in out:
            self.last_meta = {"repaired": False, "fallback": False}
            return out
        out2 = coerce_triage(self._transport(build_triage_messages(ctx, strict=True)))
        fell_back = "_meta" in out2
        self.last_meta = {"repaired": True, "fallback": fell_back}
        return out2

    def _complete_lens(self, ctx: dict) -> dict:
        """Lens variant: prose, not JSON. One call, take the first non-empty line, wrap as
        {"lens": line} for lens._one_line. No repair/fallback ladder — a lens line is free-text."""
        line = _first_nonempty_line(self._transport(build_lens_messages(ctx)))
        self.last_meta = {"repaired": False, "fallback": False}
        return {"lens": line}


class RecordedLLM:
    """Replay canned assistant replies through the SAME parse/repair path.

    Deterministic: drives the full orchestrator loop in tests without weights. Two modes (at most
    one): `responses` is consumed in CALL ORDER (the orchestrator runs depth-first); `by_lens` keys
    lens lines by lens-id so a combo replays identically regardless of stage order (F7). A lens ctx
    in by_lens mode returns WITHOUT touching the positional counter, so mixing the two never skews
    the order-sensitive path; a missing keyed id raises KeyError (loud, never a silent empty line).
    """

    def __init__(self, responses: list = None, *, by_lens: dict = None) -> None:
        if responses is not None and by_lens is not None:
            raise ValueError("RecordedLLM takes responses OR by_lens, not both")
        self._responses = list(responses or [])
        self._by_lens = dict(by_lens) if by_lens is not None else None
        self._i = 0
        self.last_meta: dict = {}

    def complete(self, ctx: dict) -> dict:
        if ctx.get("request") == "lens" and self._by_lens is not None:
            return {"lens": self._by_lens[ctx.get("lens_id")]}  # keyed; KeyError is loud (F7)
        if self._i >= len(self._responses):
            raise IndexError("RecordedLLM exhausted: more LLM calls than recorded responses")
        raw = self._responses[self._i]
        self._i += 1
        if ctx.get("request") == "triage":  # replay through the SAME triage parse path
            out = coerce_triage(raw)
            self.last_meta = {"fallback": "_meta" in out}
            return out
        try:
            out = coerce_response(raw)
            self.last_meta = {"fallback": False}
            return out
        except LLMFormatError as e:
            self.last_meta = {"fallback": True}
            return solo_fallback(str(e))
