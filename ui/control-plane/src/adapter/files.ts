/**
 * File transport — the single door for the IDE's /api/files/* surface (read + write).
 *
 * Mirrors the control adapter's discipline: every fetch lives here, the token rides the same
 * X-Auth-Token header the command path uses, and callers get typed shapes back. The backend jails
 * every path to the workspace/project root, so the UI can stay dumb about traversal safety.
 */
import { BASE_URL, CP_TOKEN } from "../config";

export type Scope = "workspace" | "project";
export type NodeKind = "file" | "directory" | "symlink";

export interface TreeNode {
  name: string;
  path: string;
  type: NodeKind;
  size: number;
  mtime_ns: number;
  children?: TreeNode[];
}

export interface TreeResponse {
  scope: Scope;
  root: string;
  tree: TreeNode | null;
  entries: number;
  truncated: boolean;
}

export interface FileContent {
  scope: Scope;
  path: string;
  name: string;
  size: number;
  content: string;
  language: string;
}

export type DiffStatus = "added" | "modified" | "deleted";

export interface DiffEntry {
  path: string;
  status: DiffStatus;
  additions: number;
  deletions: number;
  diff: string;
}

// The backend gates every /api/files/* route (reads included) on this token, so send it on every
// request — a GET can carry a custom header (it just triggers a CORS preflight cross-origin).
const TOKEN = { "X-Auth-Token": CP_TOKEN } as const;
const AUTH = { "Content-Type": "application/json", "X-Auth-Token": CP_TOKEN } as const;

async function unwrap<T>(res: Response): Promise<T> {
  const body = (await res.json().catch(() => ({}))) as T & { error?: string };
  if (!res.ok) throw new Error(body?.error || `request failed: ${res.status}`);
  return body as T;
}

export async function getTree(scope: Scope): Promise<TreeResponse> {
  return unwrap<TreeResponse>(await fetch(`${BASE_URL}/api/files/tree?scope=${scope}`, { headers: TOKEN }));
}

export async function readFile(scope: Scope, path: string): Promise<FileContent> {
  const q = `scope=${scope}&path=${encodeURIComponent(path)}`;
  return unwrap<FileContent>(await fetch(`${BASE_URL}/api/files/read?${q}`, { headers: TOKEN }));
}

export async function writeFile(scope: Scope, path: string, content: string): Promise<{ bytes: number }> {
  return unwrap(
    await fetch(`${BASE_URL}/api/files/write`, {
      method: "PUT",
      headers: AUTH,
      body: JSON.stringify({ scope, path, content }),
    }),
  );
}

export async function createPath(scope: Scope, path: string, kind: "file" | "dir"): Promise<unknown> {
  return unwrap(
    await fetch(`${BASE_URL}/api/files/create`, {
      method: "POST",
      headers: AUTH,
      body: JSON.stringify({ scope, path, kind }),
    }),
  );
}

export async function renamePath(scope: Scope, path: string, to: string): Promise<unknown> {
  return unwrap(
    await fetch(`${BASE_URL}/api/files/rename`, {
      method: "POST",
      headers: AUTH,
      body: JSON.stringify({ scope, path, to }),
    }),
  );
}

export async function deletePath(scope: Scope, path: string): Promise<unknown> {
  const q = `scope=${scope}&path=${encodeURIComponent(path)}`;
  return unwrap(await fetch(`${BASE_URL}/api/files?${q}`, { method: "DELETE", headers: AUTH }));
}

export async function getDiffs(session: string): Promise<DiffEntry[]> {
  const body = await unwrap<{ files: DiffEntry[] }>(
    await fetch(`${BASE_URL}/api/files/diff?session=${encodeURIComponent(session)}`, { headers: TOKEN }),
  );
  return body.files ?? [];
}
