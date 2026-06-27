// Canvas <-> topology.json serializer (DEC-A3: the canvas IS topology.json, 1:1 with Đồ thị-1).
// UI-meta (position, ...) lives under node.attrs.ui — inert to wiring.py (it reads only
// role/tool/hook/rule/config/entry). The serializer NEVER invents a required field: a missing
// role is left absent so the server's Topology.validate returns 422, never silently defaulted.

export type NodeType = "agent" | "tool" | "router" | "memory" | "hook";
export type EdgeType = "delegates_to" | "uses_tool" | "subscribes" | "routes";

export const NODE_TYPES: NodeType[] = ["agent", "tool", "router", "memory", "hook"];
export const EDGE_TYPES: EdgeType[] = ["delegates_to", "uses_tool", "subscribes", "routes"];

// The required attr per node type (mirror topology.py:90). "" = no required attr.
export const REQUIRED_ATTR: Record<NodeType, string> = {
  agent: "role",
  tool: "tool",
  router: "rule",
  hook: "hook",
  memory: "",
};

export interface XY { x: number; y: number }

export interface CanvasNode {
  id: string;
  type: NodeType;
  position: XY;
  data: Record<string, unknown>; // authored attrs: role/tool/rule/hook/entry/...
}

export interface CanvasEdge {
  source: string;
  target: string;
  type?: EdgeType; // edge kind; defaults to delegates_to
}

export interface TopoNode {
  id: string;
  type: string;
  ui?: { position?: XY };
  [k: string]: unknown;
}

export interface TopologyJSON {
  version: number;
  nodes: TopoNode[];
  edges: { from: string; to: string; type: string }[];
  budget?: { max_llm_calls?: number };
}

function isEmpty(v: unknown): boolean {
  return v === undefined || v === null || v === "";
}

export function canvasToTopology(
  nodes: CanvasNode[],
  edges: CanvasEdge[],
  budget?: { max_llm_calls?: number },
): TopologyJSON {
  const topoNodes: TopoNode[] = nodes.map((n) => {
    const out: TopoNode = { id: n.id, type: n.type };
    for (const [k, v] of Object.entries(n.data ?? {})) {
      if (k === "ui") continue; // ui is reserved for canvas meta, set below
      if (!isEmpty(v)) out[k] = v; // omit empties → server 422 catches a truly-missing required attr
    }
    out.ui = { position: n.position }; // UI-meta round-trips via attrs.ui (DEC-A3)
    return out;
  });

  const topoEdges = edges.map((e) => ({
    from: e.source,
    to: e.target,
    type: (e.type ?? "delegates_to") as string,
  }));

  const topo: TopologyJSON = { version: 1, nodes: topoNodes, edges: topoEdges };
  if (budget) topo.budget = budget;
  return topo;
}

// Inverse — load a stored topology back onto the canvas (reads attrs.ui.position; grid-falls-back).
export function topologyToCanvas(topo: TopologyJSON): { nodes: CanvasNode[]; edges: CanvasEdge[] } {
  const nodes: CanvasNode[] = (topo.nodes ?? []).map((n, i) => {
    const { id, type, ui, ...attrs } = n;
    const position = (ui?.position as XY | undefined) ?? { x: 80 + (i % 4) * 200, y: 80 + Math.floor(i / 4) * 140 };
    return { id, type: type as NodeType, position, data: attrs };
  });
  const edges: CanvasEdge[] = (topo.edges ?? []).map((e) => ({
    source: e.from,
    target: e.to,
    type: e.type as EdgeType,
  }));
  return { nodes, edges };
}
