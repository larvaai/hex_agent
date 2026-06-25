/**
 * Agent Graph — a pure function of the snapshot's agents, drawn with React Flow + dagre. Epic E21 (S21.18).
 *
 * No optimistic mutation: nodes come straight from ``snapshot.agents`` (server-folded), so the graph
 * only changes after a real event updates the snapshot. ``agentsToFlow`` is exported pure so the
 * status→node mapping is unit-tested without fighting React Flow's layout in jsdom.
 */
import { Background, Handle, Position, ReactFlow } from "@xyflow/react";
import type { Edge, Node, NodeProps, NodeTypes } from "@xyflow/react";
import dagre from "dagre";
import "@xyflow/react/dist/style.css";

import type { AgentView } from "../contracts/generated";
import { store, useCPState } from "../state/store";

const STATUS_COLOR: Record<string, string> = {
  done: "#2aa198",
  running: "#268bd2",
  pending: "#586e75",
  waiting: "#b58900",
  failed: "#dc322f",
};
const ROOT_ID = "__O__";

export function AgentNode({ data }: NodeProps) {
  const d = data as unknown as { label: string; status: string };
  return (
    <div
      data-testid={`agent-node-${d.label}`}
      data-status={d.status}
      style={{
        padding: "6px 10px",
        borderRadius: 6,
        border: `2px solid ${STATUS_COLOR[d.status] ?? "#586e75"}`,
        background: "#0b1620",
        color: "#c9d6df",
        fontSize: 12,
        minWidth: 96,
        textAlign: "center",
      }}
    >
      <Handle type="target" position={Position.Left} />
      <strong>{d.label}</strong>
      <div style={{ color: STATUS_COLOR[d.status] ?? "#6b8294" }}>{d.status}</div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

export function agentsToFlow(agents: AgentView[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 24, ranksep: 56 });
  g.setNode(ROOT_ID, { width: 96, height: 44 });
  agents.forEach((a) => g.setNode(a.agent_id, { width: 130, height: 48 }));
  agents.forEach((a) => g.setEdge(ROOT_ID, a.agent_id));
  dagre.layout(g);

  const at = (id: string) => {
    const n = g.node(id) as { x?: number; y?: number } | undefined;
    return { x: n?.x ?? 0, y: n?.y ?? 0 };
  };

  const nodes: Node[] = [
    { id: ROOT_ID, type: "agent", position: at(ROOT_ID), data: { label: "O", status: "running" } },
    ...agents.map((a) => ({
      id: a.agent_id,
      type: "agent",
      position: at(a.agent_id),
      data: { label: a.agent_id, status: a.status },
    })),
  ];
  const edges: Edge[] = agents.map((a) => ({ id: `O-${a.agent_id}`, source: ROOT_ID, target: a.agent_id }));
  return { nodes, edges };
}

const nodeTypes: NodeTypes = { agent: AgentNode };

export function AgentGraph() {
  const { snapshot } = useCPState();
  const { nodes, edges } = agentsToFlow(snapshot?.agents ?? []);
  return (
    <div style={{ width: "100%", height: "100%", minHeight: 260 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_e, n) => {
          if (n.id !== ROOT_ID) store.selectAgent(n.id);
        }}
      >
        <Background />
      </ReactFlow>
    </div>
  );
}
