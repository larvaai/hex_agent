// STUB (Phase 4) — replaced in Phase 6 by the full Agent Inspector (S21.20).
import { useCPState } from "../state/store";

export function AgentInspector() {
  const { snapshot, selectedAgentId } = useCPState();
  const agent = snapshot?.agents.find((a) => a.agent_id === selectedAgentId) ?? null;
  if (!agent) return <p className="redacted">Select an agent</p>;
  return (
    <div className="cp-inspector-body">
      <h3>{agent.agent_id}</h3>
      <div>role: {agent.role || "—"}</div>
      <div>status: {agent.status}</div>
    </div>
  );
}
