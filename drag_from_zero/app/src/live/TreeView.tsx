import { nodeVisual, type GraphNode } from "./status";
import type { RunGraph, RunState } from "./useRunStream";

// Render the execution tree (Đồ thị 2) from snapshot.graph. Status + verdict come straight from
// the server (Slice-6b verifier); we never recompute pass/fail here. A parked node exposes an
// "Inject agent" affordance (P3) wired to POST /api/runs/{id}/join.
function nodeById(graph: RunGraph): Map<string, GraphNode> {
  return new Map(graph.nodes.map((n) => [n.id, n]));
}

function TreeNode({ id, graph, depth, onInject, awaitingRoles }: {
  id: string;
  graph: RunGraph;
  depth: number;
  onInject: (role: string) => void;
  awaitingRoles: string[];
}) {
  const map = nodeById(graph);
  const n = map.get(id);
  if (!n) return null;
  const v = nodeVisual(n);
  return (
    <div className="tree-node" style={{ marginLeft: depth * 18 }} data-testid={`tree-node-${id}`}>
      <span className={`tree-node__dot status-${v.cls}`} />
      <span className="tree-node__goal">{n.goal || id}</span>
      <span className={`tree-node__verdict verdict-${v.cls}`} data-verdict={n.verdict}>{v.label}</span>
      {n.runtime.agent && <span className="tree-node__agent">@{n.runtime.agent}</span>}
      {n.children.map((c) => (
        <TreeNode key={c} id={c} graph={graph} depth={depth + 1} onInject={onInject} awaitingRoles={awaitingRoles} />
      ))}
    </div>
  );
}

export function TreeView({ state, onInject }: { state: RunState; onInject: (role: string) => void }) {
  const { graph, status, errors, awaitingRoles } = state;
  return (
    <section className="treeview" aria-label="execution-tree">
      <header className="treeview__head">
        <span>Run</span>
        <span className={`treeview__status status-${status}`} data-testid="run-status">{status}</span>
      </header>

      {errors.length > 0 && (
        <div className="treeview__errors" data-testid="topology-errors">
          <strong>topology rejected (422):</strong>
          <ul>{errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
        </div>
      )}

      {status === "awaiting" && awaitingRoles.length > 0 && (
        <div className="treeview__inject" data-testid="inject-panel">
          parked — waiting for a role:
          {awaitingRoles.map((r) => (
            <button key={r} data-testid={`inject-${r}`} onClick={() => onInject(r)}>
              Inject agent for “{r}”
            </button>
          ))}
        </div>
      )}

      {graph?.root ? (
        <TreeNode id={graph.root} graph={graph} depth={0} onInject={onInject} awaitingRoles={awaitingRoles} />
      ) : (
        <p className="treeview__empty">author a topology and hit Run</p>
      )}
    </section>
  );
}
