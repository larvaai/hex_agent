/**
 * L2 global-teardown — kill the backend + Vite process *groups* (not just the spawn handles, which
 * would leak the children), then remove the temp workspace. Reads e2e/.runtime.json written by setup.
 */
import { existsSync, readFileSync, rmSync } from "node:fs";
import path from "node:path";

const RUNTIME_FILE = path.join(process.cwd(), "e2e", ".runtime.json");

function killGroup(pid: number | undefined): void {
  if (!pid) return;
  try {
    process.kill(-pid, "SIGTERM"); // negative pid → the whole detached process group
  } catch {
    try {
      process.kill(pid, "SIGTERM");
    } catch {
      /* already gone */
    }
  }
}

export default async function globalTeardown(): Promise<void> {
  if (!existsSync(RUNTIME_FILE)) return;
  const rt = JSON.parse(readFileSync(RUNTIME_FILE, "utf-8"));
  killGroup(rt.vitePid);
  killGroup(rt.backendPid);
  if (rt.workspaceDir && rt.workspaceDir.includes("ide-e2e-")) {
    rmSync(rt.workspaceDir, { recursive: true, force: true });
  }
  rmSync(RUNTIME_FILE, { force: true });
}
