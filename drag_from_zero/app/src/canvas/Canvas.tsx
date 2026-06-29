import { useCallback, useMemo, useRef } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  addEdge,
  useReactFlow,
  type Node,
  type Edge,
  type Connection,
  type OnNodesChange,
  type OnEdgesChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { PALETTE, DND_MIME, type PaletteItem } from "./nodeDefs";
import { TopoNode } from "./TopoNode";

interface CanvasProps {
  nodes: Node[];
  edges: Edge[];
  onNodesChange: OnNodesChange;
  onEdgesChange: OnEdgesChange;
  setEdges: (updater: (e: Edge[]) => Edge[]) => void;
  addNode: (item: PaletteItem, position: { x: number; y: number }) => void;
}

function Palette({ addNode }: { addNode: CanvasProps["addNode"] }) {
  return (
    <aside className="palette" aria-label="palette">
      <div className="palette__title">Palette</div>
      {PALETTE.map((p) => (
        <button
          key={p.type}
          className="palette__item"
          draggable
          data-testid={`palette-${p.type}`}
          onDragStart={(e) => {
            e.dataTransfer.setData(DND_MIME, p.type);
            e.dataTransfer.effectAllowed = "move";
          }}
          onClick={() => addNode(p, { x: 60 + Math.random() * 120, y: 40 + Math.random() * 240 })}
        >
          + {p.label}
        </button>
      ))}
      <p className="palette__hint">drag onto the canvas, or click to add</p>
    </aside>
  );
}

export function Canvas(props: CanvasProps) {
  const { nodes, edges, onNodesChange, onEdgesChange, setEdges, addNode } = props;
  const wrapperRef = useRef<HTMLDivElement>(null);
  const { screenToFlowPosition } = useReactFlow();
  const nodeTypes = useMemo(() => ({ agent: TopoNode, tool: TopoNode, router: TopoNode, memory: TopoNode, hook: TopoNode }), []);

  const onConnect = useCallback(
    (c: Connection) => setEdges((es) => addEdge({ ...c, data: { type: "delegates_to" } }, es)),
    [setEdges],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const t = e.dataTransfer.getData(DND_MIME);
      const item = PALETTE.find((p) => p.type === t);
      if (!item) return;
      addNode(item, screenToFlowPosition({ x: e.clientX, y: e.clientY }));
    },
    [addNode, screenToFlowPosition],
  );

  return (
    <div className="canvas" ref={wrapperRef}>
      <Palette addNode={addNode} />
      <div className="canvas__flow" onDrop={onDrop} onDragOver={(e) => e.preventDefault()}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          fitView
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  );
}
