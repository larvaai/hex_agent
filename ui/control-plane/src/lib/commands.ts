/**
 * RuntimeCommand builders — the one place the UI shapes a command. Epic E21 (S21.3/S21.15).
 *
 * Every write is a RuntimeCommand (the UI never mutates state directly). ``idempotency_key`` is a
 * fresh uuid per build, so a double-click produces two keys the server can dedup safely (S21.10);
 * ``command_type`` must be one the registry knows (ApproveCheckpoint / RejectCheckpoint /
 * SubmitPrompt — the last added in this phase, F5/D8) or the fake gateway 400s it.
 */
import type { RuntimeCommand } from "../contracts/generated";
import { currentSession } from "../state/sessionStore";

export function buildCommand(
  command_type: string,
  payload: Record<string, unknown> = {},
  opts: { userId?: string; sessionId?: string } = {},
): RuntimeCommand {
  const id = crypto.randomUUID();
  return {
    command_type,
    session_id: opts.sessionId ?? currentSession(),
    issued_by: { type: "human", user_id: opts.userId ?? "ui-user", agent_id: null },
    idempotency_key: id, // fresh per click → server dedups; double-click is safe
    payload,
    command_id: id,
    created_at: new Date().toISOString(),
    schema_version: 1,
  };
}

export const approveCheckpoint = (checkpointId: string): RuntimeCommand =>
  buildCommand("ApproveCheckpoint", { checkpoint_id: checkpointId });

export const rejectCheckpoint = (checkpointId: string): RuntimeCommand =>
  buildCommand("RejectCheckpoint", { checkpoint_id: checkpointId });

export const submitPrompt = (prompt: string): RuntimeCommand => buildCommand("SubmitPrompt", { prompt });
