import { useCallback, useState } from "react";
import { ReactFlowProvider, useNodesState, useEdgesState, type Node, type Edge } from "@xyflow/react";
import { Canvas } from "./canvas/Canvas";
import { TreeView } from "./live/TreeView";
import { useRunStream } from "./live/useRunStream";
import { canvasToTopology, type CanvasNode, type CanvasEdge, type NodeType } from "./topology/serialize";
import type { PaletteItem } from "./canvas/nodeDefs";
import "./styles.css";

let seq = 0;
const nextId = (type: string) => `${type[0]}${++seq}`;

export default function App() {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [task, setTask] = useState("Implement an auth module with unit tests");
  const { state, run, inject } = useRunStream();

  // attrs live on node.data.attrs; the node edits them through this callback
  const onAttrChange = useCallback(
    (id: string, attrs: Record<string, unknown>) =>
      setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, data: { ...n.data, attrs } } : n))),
    [setNodes],
  );

  const addNode = useCallback(
    (item: PaletteItem, position: { x: number; y: number }) => {
      const id = nextId(item.type);
      // first agent becomes the entry — a freshly authored 2-agent graph runs without extra clicks
      const isFirstAgent = item.type === "agent" && !nodes.some((n) => n.type === "agent");
      const attrs = { ...item.defaults, ...(isFirstAgent ? { role: "planner", entry: true } : {}) };
      setNodes((ns) => ns.concat({ id, type: item.type, position, data: { attrs, onChange: onAttrChange } }));
    },
    [nodes, onAttrChange, setNodes],
  );

  const onRun = useCallback(() => {
    const cnodes: CanvasNode[] = nodes.map((n) => ({
      id: n.id,
      type: n.type as NodeType,
      position: n.position,
      data: (n.data?.attrs as Record<string, unknown>) ?? {},
    }));
    const cedges: CanvasEdge[] = edges.map((e) => ({
      source: e.source,
      target: e.target,
      type: (e.data?.type as CanvasEdge["type"]) ?? "delegates_to",
    }));
    run(canvasToTopology(cnodes, cedges), task);
  }, [nodes, edges, task, run]);

  return (
    <div className="app">
      <header className="app__bar">
        <strong>drag_from_zero</strong>
        <input className="app__task" value={task} onChange={(e) => setTask(e.target.value)} aria-label="task" />
        <button className="app__run" data-testid="run-btn" onClick={onRun} disabled={nodes.length === 0}>
          ▶ Run
        </button>
      </header>
      <main className="app__main">
        <ReactFlowProvider>
          <Canvas
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            setEdges={setEdges}
            addNode={addNode}
          />
        </ReactFlowProvider>
        <TreeView state={state} onInject={inject} />
      </main>
    </div>
  );
}
