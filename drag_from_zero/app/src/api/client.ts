// Thin client over the Phase-1 authoring boundary. 422 -> TopologyValidationError carrying the
// server's error list, surfaced on the UI. Same-origin in prod (run_server serves dist); via the
// Vite proxy in dev.
import type { TopologyJSON } from "../topology/serialize";

export class TopologyValidationError extends Error {
  errors: string[];
  constructor(errors: string[]) {
    super(errors.join("; "));
    this.name = "TopologyValidationError";
    this.errors = errors;
  }
}

async function postJSON(path: string, body: unknown): Promise<any> {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (r.status === 422) {
    const e = await r.json().catch(() => ({ errors: ["invalid"] }));
    throw new TopologyValidationError(e.errors ?? ["invalid topology"]);
  }
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

export async function postTopology(topo: TopologyJSON): Promise<{ id: string }> {
  return postJSON("/api/topology", topo);
}

export async function createRun(opts: { topology_id?: string; topology?: TopologyJSON; task: string }): Promise<{ id: string }> {
  return postJSON("/api/runs", opts);
}

export async function startRun(runId: string): Promise<void> {
  await fetch(`/api/runs/${runId}/start`, { method: "POST" });
}

export async function joinAgent(runId: string, role: string, id?: string): Promise<{ ok: boolean; woke: boolean }> {
  return postJSON(`/api/runs/${runId}/join`, id ? { role, id } : { role });
}

export type Frame =
  | { type: "snapshot"; graph: unknown }
  | { type: "event"; data: { type: string; node_id: string | null; payload: Record<string, unknown> } }
  | { type: "run_finished" }
  | { type: "run_cancelled" }
  | Record<string, unknown>;

export function openEvents(runId: string, onFrame: (f: Frame) => void): WebSocket {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/api/runs/${runId}/events`);
  ws.onmessage = (ev) => {
    try {
      onFrame(JSON.parse(ev.data));
    } catch {
      /* ignore non-JSON frames */
    }
  };
  return ws;
}
