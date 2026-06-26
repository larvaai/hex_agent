/**
 * File UI store — open tabs, dirty state, tree, and the agent's diff set. Epic E21 / IDE.
 *
 * Same one-way shape as the control-plane store (useSyncExternalStore + immutable commits), but this
 * one is allowed to drive writes: editing is the whole point of an IDE. Every mutation goes through a
 * method here so components stay declarative — they render state and call actions, never fetch inline.
 *
 * "Agent changed this file" is detected the cheap, honest way the legacy console used: flatten the
 * tree on each refresh and diff mtimes against the previous flatten. A file the running agent just
 * wrote flashes in the explorer; if it is the open tab and unedited, the editor reloads it.
 */
import { useSyncExternalStore } from "react";

import {
  createPath,
  deletePath,
  getDiffs,
  getTree,
  readFile,
  renamePath,
  writeFile,
  type DiffEntry,
  type Scope,
  type TreeNode,
  type TreeResponse,
} from "../adapter/files";
import { SESSION_ID } from "../config";

export interface Tab {
  scope: Scope;
  path: string;
  name: string;
  language: string;
  content: string;
  saved: string;
  dirty: boolean;
}

export type FileView = "editor" | "diff";

export interface FileState {
  scope: Scope;
  tree: TreeResponse | null;
  treeError: string | null;
  tabs: Tab[];
  activeKey: string | null;
  view: FileView;
  diffs: DiffEntry[];
  changed: Set<string>;
  status: string | null;
}

type Listener = () => void;

const tabKey = (scope: Scope, path: string) => `${scope}:${path}`;

function flatten(node: TreeNode | null, into = new Map<string, number>()): Map<string, number> {
  if (!node) return into;
  if (node.path) into.set(node.path, node.mtime_ns);
  (node.children ?? []).forEach((child) => flatten(child, into));
  return into;
}

class FileStore {
  private state: FileState = {
    scope: "workspace",
    tree: null,
    treeError: null,
    tabs: [],
    activeKey: null,
    view: "editor",
    diffs: [],
    changed: new Set(),
    status: null,
  };
  private prevTree = new Map<string, number>();
  private listeners = new Set<Listener>();

  getState = (): FileState => this.state;

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private commit(next: Partial<FileState>) {
    this.state = { ...this.state, ...next };
    this.listeners.forEach((l) => l());
  }

  activeTab(): Tab | null {
    return this.state.tabs.find((t) => tabKey(t.scope, t.path) === this.state.activeKey) ?? null;
  }

  // ── tree ──────────────────────────────────────────────────────────────────
  setScope = async (scope: Scope): Promise<void> => {
    this.prevTree = new Map();
    this.commit({ scope, changed: new Set() });
    await this.refreshTree();
  };

  refreshTree = async (): Promise<void> => {
    try {
      const tree = await getTree(this.state.scope);
      const flat = flatten(tree.tree);
      const changed = new Set<string>();
      if (this.prevTree.size) {
        for (const [path, mtime] of flat) {
          const old = this.prevTree.get(path);
          if (old === undefined || old !== mtime) changed.add(path);
        }
      }
      this.prevTree = flat;
      this.commit({ tree, treeError: null, changed });
      this.maybeReloadOpen(changed);
    } catch (err) {
      this.commit({ treeError: (err as Error).message });
    }
  };

  /** A file the agent just wrote, if open and clean, is reloaded so the editor never goes stale. */
  private maybeReloadOpen(changed: Set<string>) {
    const active = this.activeTab();
    if (active && active.scope === this.state.scope && !active.dirty && changed.has(active.path)) {
      void this.reloadTab(active.scope, active.path);
    }
  }

  private async reloadTab(scope: Scope, path: string) {
    try {
      const file = await readFile(scope, path);
      const key = tabKey(scope, path);
      // Re-check dirty against LIVE state at commit time: the user may have started typing during
      // the async read, and silently overwriting their buffer would lose those edits.
      this.commit({
        tabs: this.state.tabs.map((t) =>
          tabKey(t.scope, t.path) === key && !t.dirty
            ? { ...t, content: file.content, saved: file.content, dirty: false }
            : t,
        ),
      });
    } catch {
      /* file may have been deleted by the agent; leave the tab as-is */
    }
  }

  // ── tabs ──────────────────────────────────────────────────────────────────
  openFile = async (scope: Scope, path: string): Promise<void> => {
    const key = tabKey(scope, path);
    const existing = this.state.tabs.find((t) => tabKey(t.scope, t.path) === key);
    if (existing) {
      this.commit({ activeKey: key, view: "editor" });
      return;
    }
    try {
      const file = await readFile(scope, path);
      const tab: Tab = {
        scope,
        path,
        name: file.name,
        language: file.language,
        content: file.content,
        saved: file.content,
        dirty: false,
      };
      this.commit({ tabs: [...this.state.tabs, tab], activeKey: key, view: "editor", status: null });
    } catch (err) {
      this.commit({ status: (err as Error).message });
    }
  };

  setActive = (key: string): void => this.commit({ activeKey: key, view: "editor" });

  closeTab = (key: string): void => {
    const tabs = this.state.tabs.filter((t) => tabKey(t.scope, t.path) !== key);
    const activeKey =
      this.state.activeKey === key ? (tabs.length ? tabKey(tabs[tabs.length - 1].scope, tabs[tabs.length - 1].path) : null) : this.state.activeKey;
    this.commit({ tabs, activeKey });
  };

  editActive = (content: string): void => {
    const key = this.state.activeKey;
    if (!key) return;
    this.commit({
      tabs: this.state.tabs.map((t) =>
        tabKey(t.scope, t.path) === key ? { ...t, content, dirty: content !== t.saved } : t,
      ),
    });
  };

  saveActive = async (): Promise<void> => {
    const tab = this.activeTab();
    if (!tab || !tab.dirty) return;
    try {
      await writeFile(tab.scope, tab.path, tab.content);
      const key = tabKey(tab.scope, tab.path);
      this.commit({
        tabs: this.state.tabs.map((t) =>
          tabKey(t.scope, t.path) === key ? { ...t, saved: t.content, dirty: false } : t,
        ),
        status: `saved ${tab.path}`,
      });
      await this.refreshTree();
      await this.refreshDiffs();
    } catch (err) {
      this.commit({ status: (err as Error).message });
    }
  };

  // ── view + diffs ──────────────────────────────────────────────────────────
  setView = async (view: FileView): Promise<void> => {
    this.commit({ view });
    if (view === "diff") await this.refreshDiffs();
  };

  refreshDiffs = async (): Promise<void> => {
    try {
      this.commit({ diffs: await getDiffs(SESSION_ID) });
    } catch (err) {
      this.commit({ status: (err as Error).message });
    }
  };

  // ── mutations ─────────────────────────────────────────────────────────────
  create = async (scope: Scope, path: string, kind: "file" | "dir"): Promise<void> => {
    try {
      await createPath(scope, path, kind);
      await this.refreshTree();
      if (kind === "file") await this.openFile(scope, path);
    } catch (err) {
      this.commit({ status: (err as Error).message });
    }
  };

  rename = async (scope: Scope, path: string, to: string): Promise<void> => {
    try {
      await renamePath(scope, path, to);
      this.closeTab(tabKey(scope, path));
      await this.refreshTree();
    } catch (err) {
      this.commit({ status: (err as Error).message });
    }
  };

  remove = async (scope: Scope, path: string): Promise<void> => {
    try {
      await deletePath(scope, path);
      this.closeTab(tabKey(scope, path));
      await this.refreshTree();
    } catch (err) {
      this.commit({ status: (err as Error).message });
    }
  };
}

export const fileStore = new FileStore();

export function useFileState(): FileState {
  return useSyncExternalStore(fileStore.subscribe, fileStore.getState, fileStore.getState);
}

export { tabKey };
