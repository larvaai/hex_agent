/**
 * L2 global-setup — boot the REAL stack the deterministic browser tier drives:
 *   1. a temp workspace, seeded BEFORE boot (so the default session's diff baseline includes the
 *      seed → an edit shows as `modified`, and a `.env` sits there to prove sensitive-read is blocked);
 *   2. `python -m ui.ide` on an ephemeral port, session `t1_demo` (matches the UI's hardcoded
 *      config.ts SESSION_ID), readiness-polled on /api/snapshot — no fixed sleep (F9);
 *   3. Vite, pointed at that backend via VITE_CP_BASE_URL/TOKEN, readiness-polled.
 * Both are spawned as process groups (detached) so teardown kills the whole tree, not just the handle.
 * The resolved URLs/pids/workspace are written to e2e/.runtime.json for the specs + teardown.
 */
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import net from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";

const CP_DIR = process.cwd(); // `npm --prefix ui/control-plane` runs here
const REPO_ROOT = path.resolve(CP_DIR, "..", "..");
const RUNTIME_FILE = path.join(CP_DIR, "e2e", ".runtime.json");
const TOKEN = "e2e-token";
const SESSION = "t1_demo"; // must equal config.ts SESSION_ID — the UI is pinned to it

const SEED_TARGET = "def add(a, b):\n    return a + b\n";

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const s = net.createServer();
    s.on("error", reject);
    s.listen(0, "127.0.0.1", () => {
      const port = (s.address() as net.AddressInfo).port;
      s.close(() => resolve(port));
    });
  });
}

async function waitForHttp(url: string, capMs: number, label: string): Promise<void> {
  const end = Date.now() + capMs;
  let lastErr = "";
  while (Date.now() < end) {
    try {
      const res = await fetch(url);
      if (res.status >= 200 && res.status < 500) return; // up (200/401/404 all prove it's serving)
    } catch (e) {
      lastErr = String(e);
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`timeout waiting for ${label} at ${url} (${lastErr})`);
}

export default async function globalSetup(): Promise<void> {
  // 1. seed a temp workspace before either server starts
  const workspaceDir = mkdtempSync(path.join(tmpdir(), "ide-e2e-"));
  writeFileSync(path.join(workspaceDir, "e2e_target.py"), SEED_TARGET, "utf-8");
  writeFileSync(path.join(workspaceDir, ".env"), "SECRET=do-not-leak\n", "utf-8");

  const backendPort = await freePort();
  const vitePort = await freePort();
  const backendUrl = `http://127.0.0.1:${backendPort}`;
  const viteUrl = `http://127.0.0.1:${vitePort}`;

  // 2. real ui.ide backend
  const backend = spawn(
    "python3",
    ["-m", "ui.ide", "--host", "127.0.0.1", "--port", String(backendPort), "--token", TOKEN, "--session", SESSION],
    {
      cwd: REPO_ROOT,
      env: { ...process.env, AGENT_WORKSPACE_DIR: workspaceDir, PYTHONUNBUFFERED: "1" },
      detached: true,
      stdio: ["ignore", "inherit", "inherit"],
    },
  );
  await waitForHttp(`${backendUrl}/api/snapshot?session=${SESSION}`, 20_000, "ui.ide backend");

  // 3. Vite dev server, pointed at the real backend
  const vite = spawn(
    path.join(CP_DIR, "node_modules", ".bin", "vite"),
    ["--port", String(vitePort), "--strictPort", "--host", "127.0.0.1"],
    {
      cwd: CP_DIR,
      env: { ...process.env, VITE_CP_BASE_URL: backendUrl, VITE_CP_TOKEN: TOKEN },
      detached: true,
      stdio: ["ignore", "inherit", "inherit"],
    },
  );
  await waitForHttp(viteUrl, 40_000, "vite dev server");

  writeFileSync(
    RUNTIME_FILE,
    JSON.stringify(
      { viteUrl, backendUrl, token: TOKEN, session: SESSION, workspaceDir, backendPid: backend.pid, vitePid: vite.pid },
      null,
      2,
    ),
    "utf-8",
  );
}
