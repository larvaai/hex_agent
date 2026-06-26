import { Handle, Position, type NodeProps } from "@xyflow/react";
import { REQUIRED_ATTR, type NodeType } from "../topology/serialize";

// One React Flow node for every topology type. Shows the type, an inline editor for the required
// attr (role/tool/rule/hook), and an `entry` toggle for agents. Edits write back via data.onChange.
export interface TopoNodeData extends Record<string, unknown> {
  attrs: Record<string, unknown>;
  onChange: (id: string, attrs: Record<string, unknown>) => void;
}

export function TopoNode({ id, type, data }: NodeProps) {
  const d = data as TopoNodeData;
  const ntype = type as NodeType;
  const req = REQUIRED_ATTR[ntype];
  const attrs = d.attrs ?? {};

  const set = (patch: Record<string, unknown>) => d.onChange(id, { ...attrs, ...patch });

  return (
    <div className={`topo-node topo-${ntype}`}>
      <Handle type="target" position={Position.Left} />
      <div className="topo-node__type">{ntype}</div>
      {req ? (
        <input
          className="topo-node__attr"
          aria-label={`${ntype}-${req}`}
          value={String(attrs[req] ?? "")}
          placeholder={req}
          onChange={(e) => set({ [req]: e.target.value })}
        />
      ) : (
        <div className="topo-node__attr topo-node__attr--static">{String(attrs.name ?? ntype)}</div>
      )}
      {ntype === "agent" && (
        <label className="topo-node__entry">
          <input
            type="checkbox"
            checked={Boolean(attrs.entry)}
            onChange={(e) => set({ entry: e.target.checked || undefined })}
          />
          entry
        </label>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
