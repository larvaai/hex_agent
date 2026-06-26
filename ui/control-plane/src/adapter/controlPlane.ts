/**
 * Control-plane transport adapter — the single door for every fetch/EventSource. Epic E21 (Phase 4).
 *
 * Why one door: the repo's whole design is "one chokepoint". This is the UI's transport chokepoint,
 * and the contract-seam test (Phase 7) bolts onto it. It is intentionally thin — the *server* owns
 * swapping transports (change the URL); the adapter just normalises the wire into the typed shapes
 * from generated.d.ts and guarantees the seam invariants:
 *   • it surfaces only the redacted ui_payload the server streams — it never sees a raw payload;
 *   • the write path posts a real RuntimeCommand with the token header (it does not mutate any state);
 *   • the read path carries the token in the query because an EventSource cannot set headers (F8/D7);
 *   • a dropped stream reconnects with backoff, resuming from the last seen seq (Last-Event-ID, S21.25),
 *     and an out-of-ring `resync` event asks the app to re-fetch the snapshot rather than losing events (F7).
 */
import type { CommandAck, RuntimeCommand, TaskLoopSnapshot } from "../contracts/generated";
import { BASE_URL, CP_TOKEN } from "../config";

export interface StreamEvent {
  type: string;
  seq: number;
  uiPayload: Record<string, unknown>;
}

export type ConnectionStatus = "connecting" | "open" | "reconnecting" | "closed";

export interface StreamOptions {
  lastEventId?: string;
  onResync?: () => void;
  onStatus?: (status: ConnectionStatus) => void;
  eventTypes?: string[];
  maxBackoffMs?: number;
}

export interface StreamHandle {
  close(): void;
}

// SSE frames carry `event: <type>`, so a default onmessage never fires — we subscribe per type.
export const KNOWN_EVENT_TYPES = [
  "loop.team_composed",
  "loop.decision",
  "loop.turn",
  "loop.tool",
  "loop.parse_error",
  "loop.finished",
  "loop.blocked",
  "loop.failed",
  "checkpoint.reached",
  "approval.requested",
  "approval.approved",
  "approval.rejected",
  "permission.changed",
  "command.received",
  "command.accepted",
  "command.rejected",
  "command.applied",
];

export async function getSnapshot(session?: string): Promise<TaskLoopSnapshot> {
  const url = `${BASE_URL}/api/snapshot${session ? `?session=${encodeURIComponent(session)}` : ""}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`snapshot request failed: ${res.status}`);
  return (await res.json()) as TaskLoopSnapshot;
}

export async function postCommand(cmd: RuntimeCommand): Promise<CommandAck> {
  // Write = emit a RuntimeCommand. The adapter does NOT touch any UI state; the visible change
  // only happens later when the runtime publishes the resulting event over the stream.
  const res = await fetch(`${BASE_URL}/api/commands`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Auth-Token": CP_TOKEN },
    body: JSON.stringify(cmd),
  });
  return (await res.json()) as CommandAck; // 200 (received) and 400 (rejected) both return an ack-shaped body
}

export function openStream(onEvent: (event: StreamEvent) => void, opts: StreamOptions = {}): StreamHandle {
  const types = opts.eventTypes ?? KNOWN_EVENT_TYPES;
  const maxBackoff = opts.maxBackoffMs ?? 10_000;
  let source: EventSource | null = null;
  let closed = false;
  let lastEventId = opts.lastEventId;
  let attempt = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const connect = () => {
    if (closed) return;
    opts.onStatus?.(attempt === 0 ? "connecting" : "reconnecting");
    let url = `${BASE_URL}/api/stream?token=${encodeURIComponent(CP_TOKEN)}`;
    if (lastEventId) url += `&lastEventId=${encodeURIComponent(lastEventId)}`;
    source = new EventSource(url);

    source.onopen = () => {
      attempt = 0;
      opts.onStatus?.("open");
    };

    const handler = (ev: MessageEvent) => {
      if (ev.lastEventId) lastEventId = ev.lastEventId;
      let uiPayload: Record<string, unknown> = {};
      try {
        uiPayload = JSON.parse(ev.data) as Record<string, unknown>;
      } catch {
        uiPayload = {};
      }
      onEvent({ type: ev.type, seq: Number(ev.lastEventId || 0), uiPayload });
    };
    for (const type of types) source.addEventListener(type, handler as EventListener);

    source.addEventListener("resync", () => {
      // out-of-ring: the gap fell off the buffer — re-fetch the snapshot, do not treat as an error (F7)
      opts.onResync?.();
    });

    source.onerror = () => {
      if (closed) return;
      source?.close();
      attempt += 1;
      const backoff = Math.min(maxBackoff, 250 * 2 ** (attempt - 1));
      opts.onStatus?.("reconnecting");
      timer = setTimeout(connect, backoff);
    };
  };

  connect();

  return {
    close() {
      closed = true;
      if (timer) clearTimeout(timer);
      source?.close();
      opts.onStatus?.("closed");
    },
  };
}
