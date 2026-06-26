/**
 * Sessions + run-control + terminal transport — the door for the opencode-parity surface.
 *
 * Mirrors the file adapter's discipline: every fetch lives here, the token rides the same
 * X-Auth-Token header, callers get typed shapes back. Three small surfaces the IDE grew:
 *   • session history  — list/create conversations (each its own event buffer + diff baseline);
 *   • run control      — POST a cancel for a session's live run (cooperative stop);
 *   • terminal         — run a workspace command (policy-gated server-side) and read its output.
 */
import { BASE_URL, CP_TOKEN } from "../config";

const TOKEN = { "X-Auth-Token": CP_TOKEN } as const;
const AUTH = { "Content-Type": "application/json", "X-Auth-Token": CP_TOKEN } as const;

export interface SessionMeta {
  id: string;
  title: string;
  status: string;
  last_prompt: string;
  created_at: string;
}

export interface TerminalResult {
  ok: boolean;
  argv: string[];
  returncode: number;
  stdout: string;
  stderr: string;
}

async function unwrap<T>(res: Response): Promise<T> {
  const body = (await res.json().catch(() => ({}))) as T & { error?: string };
  if (!res.ok) throw new Error(body?.error || `request failed: ${res.status}`);
  return body as T;
}

export async function listSessions(): Promise<{ sessions: SessionMeta[]; default: string }> {
  return unwrap(await fetch(`${BASE_URL}/api/sessions`, { headers: TOKEN }));
}

export async function createSession(title?: string): Promise<SessionMeta> {
  return unwrap(
    await fetch(`${BASE_URL}/api/sessions`, { method: "POST", headers: AUTH, body: JSON.stringify({ title }) }),
  );
}

export async function cancelRun(session: string): Promise<{ ok: boolean; cancelled: boolean }> {
  return unwrap(
    await fetch(`${BASE_URL}/api/runs/cancel`, { method: "POST", headers: AUTH, body: JSON.stringify({ session }) }),
  );
}

export async function runTerminal(command: string): Promise<TerminalResult> {
  return unwrap(
    await fetch(`${BASE_URL}/api/terminal`, { method: "POST", headers: AUTH, body: JSON.stringify({ command }) }),
  );
}
