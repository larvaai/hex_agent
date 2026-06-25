/**
 * E21 Phase 6 — Agent Inspector test. Maps to S21.20 (+ R3).
 *
 * The Inspector is a pure function of the selected AgentView. It shows role / allowed_tools /
 * last_output / permission, and because those came redacted from the snapshot, a "[REDACTED]"
 * value renders literally — a real secret never appears.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import type { TaskLoopSnapshot } from "../../contracts/generated";
import { store } from "../../state/store";
import { AgentInspector } from "../AgentInspector";

function snapshotWith(agent: TaskLoopSnapshot["agents"][number]): TaskLoopSnapshot {
  return {
    session_id: "t1",
    status: "in_discussion",
    round_no: 1,
    orchestrator: { last_decision: "continue", reason: "" },
    agents: [agent],
    pending_agent_calls: [],
    tool_calls: [],
    checkpoints: [],
    acceptance_status: [],
    last_updated_at: "t",
  };
}

beforeEach(() => store._reset());

describe("AgentInspector", () => {
  it("inspector_hides_secret", () => {
    store.setSnapshot(
      snapshotWith({
        agent_id: "B",
        role: "builder",
        status: "running",
        round_no: 1,
        allowed_tools: ["read_file", "search_code"],
        last_output_summary: "built the module",
        context_packet: { briefing: "use the api", api_key: "[REDACTED]" },
        permission: { allowed_tools: ["read_file"], can_write_artifacts: true },
      }),
    );
    store.selectAgent("B");
    render(<AgentInspector />);

    expect(screen.getByText("builder")).toBeInTheDocument();
    expect(screen.getAllByText(/read_file/).length).toBeGreaterThan(0); // allowed tools + permission
    expect(screen.getByText(/built the module/)).toBeInTheDocument();
    expect(screen.getByText(/\[REDACTED\]/)).toBeInTheDocument(); // redaction shown literally
    expect(screen.queryByText(/sk-/)).toBeNull(); // no raw secret
  });

  it("shows a placeholder when nothing is selected", () => {
    render(<AgentInspector />);
    expect(screen.getByText(/select an agent/i)).toBeInTheDocument();
  });
});
