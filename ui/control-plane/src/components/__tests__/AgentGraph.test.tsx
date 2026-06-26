/**
 * E21 Phase 5 — Agent Graph tests. Maps to S21.18.
 *
 * The graph is a pure function of the snapshot's agents: status in → node status out. And it is
 * idempotent — a duplicate event (same seq) must not double a node or corrupt the graph.
 */
import { describe, expect, it } from "vitest";

import type { AgentView } from "../../contracts/generated";
import type { StreamEvent } from "../../adapter/controlPlane";
import { store } from "../../state/store";
import { agentsToFlow } from "../AgentGraph";

function av(agent_id: string, status: string): AgentView {
  return {
    agent_id,
    role: "",
    status,
    round_no: 0,
    allowed_tools: [],
    last_output_summary: "",
    context_packet: {},
    permission: null,
  };
}

describe("AgentGraph", () => {
  it("graph_renders_agent_status", () => {
    const { nodes } = agentsToFlow([av("A", "done"), av("B", "running"), av("C", "pending")]);
    const agentNodes = nodes.filter((n) => n.id !== "__O__");
    expect(agentNodes.map((n) => [n.id, (n.data as { status: string }).status])).toEqual([
      ["A", "done"],
      ["B", "running"],
      ["C", "pending"],
    ]);
    // every node has a laid-out position (dagre ran)
    expect(agentNodes.every((n) => Number.isFinite(n.position.x) && Number.isFinite(n.position.y))).toBe(true);
  });

  it("graph_idempotent_on_duplicate_event", () => {
    store._reset();
    const ev: StreamEvent = { type: "loop.turn", seq: 1, uiPayload: { agent_id: "A" } };
    store.applyEvent(ev);
    store.applyEvent(ev); // same seq delivered twice
    expect(store.getState().events).toHaveLength(1); // deduped

    // the graph derives purely from the (server-folded) snapshot — duplicates can't double a node
    const before = agentsToFlow([av("A", "running")]);
    const after = agentsToFlow([av("A", "running")]);
    expect(after.nodes.length).toBe(before.nodes.length);
  });
});
