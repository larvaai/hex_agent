/** Read the runtime descriptor global-setup wrote (URLs, token, temp workspace path, pids). */
import { readFileSync } from "node:fs";
import path from "node:path";

export interface Runtime {
  viteUrl: string;
  backendUrl: string;
  token: string;
  session: string;
  workspaceDir: string;
  backendPid: number;
  vitePid: number;
}

export function runtime(): Runtime {
  return JSON.parse(readFileSync(path.join(process.cwd(), "e2e", ".runtime.json"), "utf-8"));
}
