/**
 * File Explorer — the IDE's left rail. Browse the workspace (or the project), open files into tabs,
 * and do the basic file management an IDE needs (new file/folder, rename, delete).
 *
 * Two scopes: "workspace" is the agent's sandbox (var/workspace) where it edits; "project" is the
 * repo itself, read/edit with the same jail + sensitive-file guards. Files the running agent just
 * wrote flash (the `changed` set from the store), so you can watch edits land in real time.
 */
import { useEffect, useState } from "react";

import { fileStore, useFileState } from "../state/fileStore";
import type { Scope, TreeNode } from "../adapter/files";

interface RowProps {
  node: TreeNode;
  depth: number;
  scope: Scope;
  activeKey: string | null;
  changed: Set<string>;
}

// activeKey/changed are threaded down as props (not read from the store per-row) so a single store
// commit doesn't force every row in the tree to re-render — only the parent recomputes.
function Row({ node, depth, scope, activeKey, changed }: RowProps) {
  const [open, setOpen] = useState(depth < 1);
  const pad = 6 + depth * 12;
  const isChanged = changed.has(node.path);

  if (node.type === "directory") {
    return (
      <div>
        <div className="ide-tree-row" style={{ paddingLeft: pad }} onClick={() => setOpen((v) => !v)}>
          <span className="ide-tree-caret">{open ? "▾" : "▸"}</span>
          <span className="ide-tree-name">{node.name}</span>
        </div>
        {open &&
          (node.children ?? []).map((child) => (
            <Row key={child.path} node={child} depth={depth + 1} scope={scope} activeKey={activeKey} changed={changed} />
          ))}
      </div>
    );
  }

  const active = activeKey === `${scope}:${node.path}`;
  return (
    <div
      className={`ide-tree-row ide-tree-file${active ? " is-active" : ""}${isChanged ? " is-changed" : ""}`}
      style={{ paddingLeft: pad + 12 }}
      onClick={() => fileStore.openFile(scope, node.path)}
      title={node.path}
    >
      <span className="ide-tree-name">{node.name}</span>
      {isChanged && <span className="ide-tree-dot" aria-label="changed" />}
      <span className="ide-tree-actions">
        <button
          title="Rename"
          onClick={(e) => {
            e.stopPropagation();
            const to = window.prompt("Rename to (path under root):", node.path);
            if (to && to !== node.path) void fileStore.rename(scope, node.path, to);
          }}
        >
          ✎
        </button>
        <button
          title="Delete"
          onClick={(e) => {
            e.stopPropagation();
            if (window.confirm(`Delete ${node.path}?`)) void fileStore.remove(scope, node.path);
          }}
        >
          ✕
        </button>
      </span>
    </div>
  );
}

export function FileExplorer() {
  const { scope, tree, treeError, status, activeKey, changed } = useFileState();

  useEffect(() => {
    void fileStore.refreshTree();
  }, []);

  const newEntry = (kind: "file" | "dir") => {
    const path = window.prompt(`New ${kind === "dir" ? "folder" : "file"} path (under root):`, "");
    if (path) void fileStore.create(scope, path.trim(), kind);
  };

  return (
    <div className="ide-explorer">
      <div className="ide-explorer-head">
        <div className="ide-scope">
          {(["workspace", "project"] as Scope[]).map((s) => (
            <button
              key={s}
              className={`ide-seg${scope === s ? " is-active" : ""}`}
              onClick={() => void fileStore.setScope(s)}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="ide-explorer-actions">
          <button title="New file" onClick={() => newEntry("file")}>＋</button>
          <button title="New folder" onClick={() => newEntry("dir")}>📁</button>
          <button title="Refresh" onClick={() => void fileStore.refreshTree()}>⟳</button>
        </div>
      </div>
      <div className="ide-tree">
        {treeError && <div className="ide-error">{treeError}</div>}
        {tree?.tree?.children?.length ? (
          tree.tree.children.map((child) => (
            <Row key={child.path} node={child} depth={0} scope={scope} activeKey={activeKey} changed={changed} />
          ))
        ) : (
          <div className="ide-empty">{treeError ? "" : "Empty — prompt the agent or create a file."}</div>
        )}
      </div>
      {status && <div className="ide-explorer-status">{status}</div>}
    </div>
  );
}
