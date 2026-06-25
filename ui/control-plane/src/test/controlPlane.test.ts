/**
 * E21 Phase 4 — transport adapter tests. Maps to S21.15 / S21.25 + seam F8/F13.
 *
 * The adapter is the single transport door. These pin the seam foundations: it surfaces only
 * the redacted ui_payload (never a key named `payload`, never a secret), the write path posts a
 * real RuntimeCommand with the token header, the read path carries the token in the query (an
 * EventSource cannot set headers — F8), and a dropped stream reconnects with the last seen seq.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getSnapshot, openStream, postCommand, type StreamEvent } from "../adapter/controlPlane";

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  listeners: Record<string, ((e: unknown) => void)[]> = {};
  onopen: ((e: unknown) => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }
  addEventListener(type: string, h: (e: unknown) => void) {
    (this.listeners[type] ||= []).push(h);
  }
  close() {}
  emit(type: string, data: unknown, lastEventId = "0") {
    (this.listeners[type] || []).forEach((h) => h({ type, data: JSON.stringify(data), lastEventId }));
  }
  fail() {
    this.onerror?.({});
  }
}

beforeEach(() => {
  MockEventSource.instances = [];
  vi.stubGlobal("EventSource", MockEventSource as unknown as typeof EventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("adapter seam", () => {
  it("adapter_reads_ui_payload_only", () => {
    const got: StreamEvent[] = [];
    openStream((e) => got.push(e));
    const es = MockEventSource.instances[0];
    // the server only ever sends ui_payload (already redacted) as `data`
    es.emit("loop.tool", { tool: "http", api_key: "[REDACTED]" }, "1");
    expect(got).toHaveLength(1);
    expect(got[0]).not.toHaveProperty("payload"); // adapter never exposes a raw `payload` key
    expect(JSON.stringify(got[0])).not.toContain("sk-"); // no secret value
    expect((got[0].uiPayload as Record<string, unknown>).tool).toBe("http");
    expect(got[0].type).toBe("loop.tool");
    expect(got[0].seq).toBe(1);
  });

  it("adapter_stream_sends_token_in_query", () => {
    openStream(() => {});
    expect(MockEventSource.instances[0].url).toContain("token=dev-token");
  });

  it("adapter_post_sends_runtime_command", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ command_id: "c1", status: "received", seq: 1, rejection_reason: null, created_at: "t" }),
    }));
    vi.stubGlobal("fetch", fetchMock);
    const cmd = {
      command_type: "ApproveCheckpoint",
      session_id: "t1",
      issued_by: { type: "human", user_id: "u1", agent_id: null },
      idempotency_key: "k1",
      payload: { checkpoint_id: "cp1" },
      command_id: "c1",
      created_at: "t",
      schema_version: 1,
    };
    const ack = await postCommand(cmd as never);
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("/api/commands");
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["X-Auth-Token"]).toBe("dev-token");
    expect(JSON.parse(init.body as string)).toMatchObject({ command_type: "ApproveCheckpoint", idempotency_key: "k1" });
    expect(ack.status).toBe("received");
  });

  it("adapter_reconnect_uses_last_event_id", () => {
    vi.useFakeTimers();
    const got: StreamEvent[] = [];
    const handle = openStream((e) => got.push(e));
    const es1 = MockEventSource.instances[0];
    es1.emit("loop.turn", { n: 1 }, "5");
    expect(got[0].seq).toBe(5);
    es1.fail(); // stream drops
    vi.advanceTimersByTime(2000); // backoff elapses
    const es2 = MockEventSource.instances[1];
    expect(es2).toBeDefined();
    expect(es2.url).toContain("lastEventId=5"); // resumes from last seen
    handle.close();
    vi.useRealTimers();
  });

  it("getSnapshot fetches the snapshot endpoint", async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ session_id: "t1", agents: [] }) }));
    vi.stubGlobal("fetch", fetchMock);
    const snap = await getSnapshot("t1");
    expect((fetchMock.mock.calls[0] as unknown as [string])[0]).toContain("/api/snapshot");
    expect(snap.session_id).toBe("t1");
  });
});
