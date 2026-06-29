/**
 * Diff Panel — what the agent changed this session. Epic E21 / IDE.
 *
 * The backend snapshots a file baseline when a run starts, so this is a true before/after of the
 * agent's edits (and any of yours since) — the review surface opencode users live in. Each file shows
 * a unified diff with +/- colouring; clicking the header opens the file in the editor.
 */
import { fileStore, useFileState } from "../state/fileStore";
import type { DiffEntry } from "../adapter/files";

function lineClass(line: string): string {
  if (line.startsWith("@@")) return "ide-diff-hunk";
  if (line.startsWith("+") && !line.startsWith("+++")) return "ide-diff-add";
  if (line.startsWith("-") && !line.startsWith("---")) return "ide-diff-del";
  if (line.startsWith("+++") || line.startsWith("---")) return "ide-diff-meta";
  return "ide-diff-ctx";
}

function FileDiff({ entry }: { entry: DiffEntry }) {
  // Diffs are always against the workspace baseline (the agent's sandbox), so open there.
  return (
    <div className="ide-diff-file">
      <div className="ide-diff-head" onClick={() => fileStore.openFile("workspace", entry.path)} title="Open in editor">
        <span className={`ide-diff-status is-${entry.status}`}>{entry.status}</span>
        <span className="ide-diff-path">{entry.path}</span>
        <span className="ide-diff-stat">
          <span className="ide-diff-add">+{entry.additions}</span> <span className="ide-diff-del">−{entry.deletions}</span>
        </span>
      </div>
      <pre className="ide-diff-body">
        {entry.diff
          ? entry.diff.split("\n").map((line, i) => (
              <div key={i} className={lineClass(line)}>
                {line || " "}
              </div>
            ))
          : <div className="ide-diff-ctx">(no textual diff)</div>}
      </pre>
    </div>
  );
}

export function DiffPanel() {
  const { diffs } = useFileState();

  return (
    <div className="ide-diffpanel">
      <div className="ide-diff-toolbar">
        <strong>Agent changes</strong>
        <span className="ide-muted">{diffs.length} file{diffs.length === 1 ? "" : "s"}</span>
        <button className="ide-seg" onClick={() => void fileStore.refreshDiffs()}>⟳ refresh</button>
      </div>
      {diffs.length === 0 ? (
        <div className="ide-empty">No changes yet. Prompt the agent, then check back.</div>
      ) : (
        diffs.map((entry) => <FileDiff key={entry.path} entry={entry} />)
      )}
    </div>
  );
}
