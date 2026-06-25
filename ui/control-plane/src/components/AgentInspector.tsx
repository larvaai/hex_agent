/**
 * Agent Inspector — a pure read of the selected AgentView. Epic E21 (S21.20).
 *
 * Shows role / status / allowed_tools / last_output / permission / context. All of these arrived
 * redacted in the snapshot, so a "[REDACTED]" value renders literally and a secret never surfaces.
 * Optional fields (permission/allowed_tools/context) show "—" when empty (F6) rather than guessing.
 */
import { useCPState } from "../state/store";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="cp-row" style={{ display: "flex", gap: 8, padding: "2px 0", fontSize: 12 }}>
      <span style={{ color: "#6b8294", minWidth: 110 }}>{label}</span>
      <span style={{ color: "#c9d6df", wordBreak: "break-word" }}>{children}</span>
    </div>
  );
}

export function AgentInspector() {
  const { snapshot, selectedAgentId } = useCPState();
  const agent = snapshot?.agents.find((a) => a.agent_id === selectedAgentId) ?? null;

  if (!agent) return <p className="redacted">Select an agent to inspect</p>;

  return (
    <div className="cp-inspector-body">
      <h3 style={{ margin: "0 0 6px" }}>{agent.agent_id}</h3>
      <Row label="role">{agent.role || "—"}</Row>
      <Row label="status">{agent.status}</Row>
      <Row label="allowed tools">{agent.allowed_tools.length ? agent.allowed_tools.join(", ") : "—"}</Row>
      <Row label="last output">{agent.last_output_summary || "—"}</Row>
      <Row label="permission">
        {agent.permission ? <code>{JSON.stringify(agent.permission)}</code> : "—"}
      </Row>
      <Row label="context">
        {Object.keys(agent.context_packet).length ? <code>{JSON.stringify(agent.context_packet)}</code> : "—"}
      </Row>
    </div>
  );
}
