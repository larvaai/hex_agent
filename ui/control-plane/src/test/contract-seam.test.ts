// @vitest-environment node
/**
 * E21 Phase 7 — contract-seam test. The DEFINITION OF DONE for the whole plan.
 *
 * This is not a mock: it boots the REAL Python fake server (tools/fake_control_server.py) as a child
 * process and drives the REAL adapter against it, proving the seam is true rather than promised.
 * Four assertions (brainstorm §7):
 *   1. the UI only ever sees the redacted ui_payload — never a raw `payload` key, never a secret (F13);
 *   2. redaction renders as the literal "[REDACTED]";
 *   3. Approve posts a real RuntimeCommand that the server's parse_command accepts (received ack);
 *   4. a forced mid-stream SSE drop is recovered via Last-Event-ID with no loss and no duplication.
 *
 * Because the fake runs the same control/ code the real backend will, "drop-in = change the URL".
 */
import { spawn, type ChildProcess } from "node:child_process";
import net from "node:net";
import { fileURLToPath } from "node:url";

import { EventSource } from "eventsource";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

import type { StreamEvent } from "../adapter/controlPlane";

const REPO_ROOT = fileURLToPath(new URL("../../../../", import.meta.url));
const FIXTURE = fileURLToPath(new URL("../../../../fixtures/control_plane/t1_scenario.events.jsonl", import.meta.url));
const TOKEN = "dev-token";

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on("error", reject);
    srv.listen(0, () => {
      const port = (srv.address() as net.AddressInfo).port;
      srv.close(() => resolve(port));
    });
  });
}

function startServer(port: number, reality: boolean): ChildProcess {
  const args = ["tools/fake_control_server.py", "--port", String(port), "--fixture", FIXTURE];
  if (!reality) args.push("--no-reality");
  return spawn("python3", args, { cwd: REPO_ROOT, stdio: "ignore" });
}

async function waitReady(port: number): Promise<void> {
  const deadline = Date.now() + 8000;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`http://localhost:${port}/api/snapshot?session=t1_demo`);
      if (res.ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error(`fake server on ${port} never became ready`);
}

async function importAdapter(port: number) {
  vi.resetModules();
  vi.stubEnv("VITE_CP_BASE_URL", `http://localhost:${port}`);
  vi.stubEnv("VITE_CP_TOKEN", TOKEN);
  return import("../adapter/controlPlane");
}

function collect(open: () => { close(): void }, sink: StreamEvent[], ms: number): Promise<StreamEvent[]> {
  return new Promise((resolve) => {
    const handle = open();
    setTimeout(() => {
      handle.close();
      resolve(sink);
    }, ms);
  });
}

beforeAll(() => {
  // Node has no global EventSource — polyfill it so the real adapter's openStream works.
  (globalThis as unknown as { EventSource: typeof EventSource }).EventSource = EventSource;
});

// ── deterministic seam (reality off): assertions 1, 2, 3 ──────────────────────
describe("contract seam — read/write (deterministic)", () => {
  let port: number;
  let proc: ChildProcess;

  beforeAll(async () => {
    port = await freePort();
    proc = startServer(port, false);
    await waitReady(port);
  });

  afterAll(() => {
    proc?.kill();
    vi.unstubAllEnvs();
  });

  it("seam_ui_never_reads_raw_payload (1) + seam_renders_redacted (2)", async () => {
    const adapter = await importAdapter(port);
    const events: StreamEvent[] = [];
    await collect(() => adapter.openStream((e) => events.push(e)), events, 800);

    expect(events.length).toBeGreaterThan(0);
    // 1 — no event object exposes a raw `payload` key, and no secret value leaks anywhere
    for (const e of events) {
      expect(Object.prototype.hasOwnProperty.call(e, "payload")).toBe(false);
    }
    expect(JSON.stringify(events)).not.toContain("sk-DEMO-LEAK");
    // 2 — the tool event carried api_key in its raw payload; the seam shows it redacted
    const tool = events.find((e) => e.type === "loop.tool");
    expect(tool).toBeDefined();
    expect((tool!.uiPayload as Record<string, unknown>).api_key).toBe("[REDACTED]");
  });

  it("seam_approve_posts_real_command (3)", async () => {
    const adapter = await importAdapter(port);
    const { approveCheckpoint } = await import("../lib/commands");
    const ack = await adapter.postCommand(approveCheckpoint("cp_demo_1"));
    // the server's parse_command accepted a real RuntimeCommand → synchronous received ack
    expect(ack.status).toBe("received");
    expect(ack.command_id).toBeTruthy();
    expect(typeof ack.seq).toBe("number");
  });
});

// ── reality seam (forced drops): assertion 4 ─────────────────────────────────
describe("contract seam — reconnect via Last-Event-ID (reality)", () => {
  let port: number;
  let proc: ChildProcess;

  beforeAll(async () => {
    port = await freePort();
    proc = startServer(port, true); // reality on: SSE drops mid-stream
    await waitReady(port);
  });

  afterAll(() => {
    proc?.kill();
    vi.unstubAllEnvs();
  });

  it("seam_reconnect_last_event_id (4)", async () => {
    const adapter = await importAdapter(port);
    const events: StreamEvent[] = [];
    await collect(() => adapter.openStream((e) => events.push(e)), events, 3500);

    const seqs = events.map((e) => e.seq).sort((a, b) => a - b);
    const unique = [...new Set(seqs)];
    // no loss: every fixture event (seq 1..9) arrived despite the mid-stream drops
    expect(unique).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);
    // no duplication: Last-Event-ID resumed instead of re-sending what was already seen
    expect(seqs.length).toBe(unique.length);
  }, 12000);
});
