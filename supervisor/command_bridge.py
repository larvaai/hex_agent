"""Bridge Agent O's command intents onto the E21 control plane. Epic E21 (S21.13).

Single responsibility: translate, queue, and apply control-plane commands. It is
the ONLY place the supervisor touches ``RuntimeCommand`` — the loop calls these
functions, never the control-plane internals directly. It does NOT touch
delegation or create sessions; it only mutates the command queues and the roster
(``selected_agents``) on the TaskLoopState.

Design notes that the tests pin:
- ``idempotency_key`` is derived *stably* from a command's intent, never from the
  random ``command_id``/``created_at`` — otherwise dedup would never fire.
- Dedup is by ``idempotency_key`` alone, against both the pending queue and the
  already-applied keys, so the same intent issued across many rounds grows the
  roster exactly once (idempotent, even across a resume).
- ``apply_pending_commands`` trusts O (agent-issued commands bypass
  ``requires_permission``); a non-agent issuer is rejected because the human
  permission path is out of scope for this round.
"""
from __future__ import annotations

from typing import Any

from control.commands import RuntimeCommand, parse_command
from control.errors import ControlContractError

# Every O command is attributed to the orchestrator (trust-O, no permission gate).
_ORCHESTRATOR_ID = "orchestrator"


def _derive_idempotency_key(command_type: str, payload: dict[str, Any]) -> str:
    """A stable key from the command's *intent*.

    For AddAgentToLoop the intent is "add this agent", so ``type:agent_id`` makes
    re-issuing the same add a no-op. This deliberately locks "add a role once per
    loop lifetime" — re-add is out of scope (it pairs with RemoveAgentFromLoop).
    """
    agent_id = str(payload.get("agent_id", "")).strip()
    return f"{command_type}:{agent_id}" if agent_id else command_type


def to_runtime_command(raw: dict[str, Any], *, session_id: str) -> RuntimeCommand:
    """Translate one O-issued command dict into a validated RuntimeCommand.

    ``issued_by`` is always the orchestrator. The idempotency_key is taken from
    ``raw`` when present, else derived stably from the payload. Raises
    ``ControlContractError`` when the result fails control-plane validation — the
    caller turns that into a ``command.rejected`` event.
    """
    if not isinstance(raw, dict):
        raise ControlContractError("O command must be a mapping.")
    command_type = str(raw.get("command_type", "")).strip()
    if not command_type:
        raise ControlContractError("O command requires a non-empty 'command_type'.")
    payload = dict(raw.get("payload") or {})
    idempotency_key = (
        str(raw.get("idempotency_key", "")).strip()
        or _derive_idempotency_key(command_type, payload)
    )
    candidate = {
        "command_type": command_type,
        "session_id": session_id,
        "issued_by": {"type": "agent", "agent_id": _ORCHESTRATOR_ID},
        "idempotency_key": idempotency_key,
        "payload": payload,
    }
    return parse_command(candidate)


def _queued_keys(commands: list[dict[str, Any]]) -> set[str]:
    return {str(c.get("idempotency_key", "")) for c in commands}


def enqueue_commands(state, decision) -> int:
    """Translate ``decision.commands`` and append them to ``state.pending_commands``.

    Deduped by idempotency_key against both the pending queue and the
    already-applied keys. A command that fails translation is skipped silently
    here (it was already shape-checked by ``parse_decision``); the apply step is
    where rejections become events. Returns how many were newly enqueued.
    """
    seen = _queued_keys(state.pending_commands) | set(state.applied_command_keys)
    added = 0
    for raw in decision.commands:
        try:
            cmd = to_runtime_command(raw, session_id=state.session_id)
        except ControlContractError:
            continue
        if cmd.idempotency_key in seen:
            continue
        seen.add(cmd.idempotency_key)
        state.pending_commands.append(cmd.as_dict())
        added += 1
    return added


def apply_pending_commands(state, ctx, *, registry, catalog: set[str]) -> int:
    """Apply every queued command at a safe checkpoint; return the roster growth count.

    Each pending command reaches a terminal decision in this single pass, so the
    queue is cleared afterwards. ``applied`` counts only commands that actually
    grew the roster — Phase 4 uses that as a progress signal (a round that only
    admits a new agent still counts as progress).
    """
    applied = 0
    for raw in state.pending_commands:
        cmd = RuntimeCommand.from_dict(raw)
        key = cmd.idempotency_key

        # Idempotent: a key already applied (including across a resume) never re-applies.
        if key in state.applied_command_keys:
            continue

        # Unknown command_type → reject (don't let one bad command kill the round).
        try:
            registry.assert_known(cmd.command_type)
        except ControlContractError:
            ctx.emit("command.rejected", {
                "idempotency_key": key,
                "reason": f"unknown command_type {cmd.command_type!r}",
            })
            continue

        # Trust-O: only agent-issued commands act here. Human path + permission
        # enforcement are out of scope, so a non-agent issuer is rejected.
        if cmd.issued_by.type != "agent":
            ctx.emit("command.rejected", {
                "idempotency_key": key,
                "reason": "non-agent issuer; permission path not implemented",
            })
            continue

        if registry.apply_at(cmd.command_type) != "next_checkpoint":
            ctx.emit("command.skipped", {
                "idempotency_key": key,
                "reason": "apply_at is not next_checkpoint",
            })
            continue

        # v1 supports AddAgentToLoop only; other declared types are skipped.
        if cmd.command_type != "AddAgentToLoop":
            ctx.emit("command.skipped", {
                "idempotency_key": key,
                "reason": f"{cmd.command_type} not supported in v1",
            })
            continue

        agent_id = str(cmd.payload.get("agent_id", "")).strip()
        if agent_id not in catalog:
            ctx.emit("command.rejected", {
                "idempotency_key": key,
                "reason": f"agent {agent_id!r} not in catalog",
            })
            continue

        # Honoured: record the key for idempotency, grow the roster if it is new.
        state.applied_command_keys.append(key)
        if agent_id not in state.selected_agents:
            state.selected_agents.append(agent_id)
            ctx.emit("loop.agent_added", {"agent_id": agent_id, "idempotency_key": key})
            applied += 1

    # Every pending command got a terminal decision in this pass — clear the queue.
    state.pending_commands = []
    return applied
