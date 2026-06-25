// STUB (Phase 4) — replaced in Phase 5 by the React Flow + dagre Agent Graph.
import { store, useCPState } from "../state/store";

export function AgentGraph() {
  const { snapshot, selectedAgentId } = useCPState();
  return (
    <ul className="cp-agent-list">
      {(snapshot?.agents ?? []).map((a) => (
        <li key={a.agent_id} data-selected={a.agent_id === selectedAgentId} onClick={() => store.selectAgent(a.agent_id)}>
          {a.agent_id}: {a.status}
        </li>
      ))}
    </ul>
  );
}
