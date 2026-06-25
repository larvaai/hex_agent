/**
 * E21 Phase 6 — Approval modal test. Maps to S21.21.
 *
 * A waiting checkpoint opens the modal; Approve/Reject emit a real RuntimeCommand through the
 * adapter. The invariant: clicking does NOT mutate UI state — the snapshot is unchanged until a
 * runtime event resolves the checkpoint (no optimistic mutation).
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { postCommandMock } = vi.hoisted(() => ({ postCommandMock: vi.fn() }));
vi.mock("../../adapter/controlPlane", () => ({
  postCommand: postCommandMock,
  openStream: vi.fn(() => ({ close: vi.fn() })),
  getSnapshot: vi.fn(),
  KNOWN_EVENT_TYPES: [],
}));

import type { TaskLoopSnapshot } from "../../contracts/generated";
import { store } from "../../state/store";
import { ApprovalModal } from "../ApprovalModal";

function snapshotWaiting(): TaskLoopSnapshot {
  return {
    session_id: "t1",
    status: "in_discussion",
    round_no: 1,
    orchestrator: { last_decision: "continue", reason: "" },
    agents: [],
    pending_agent_calls: [],
    tool_calls: [],
    checkpoints: [
      { checkpoint_id: "cp_demo_1", checkpoint_type: "before_tool_call", risk_level: "high", status: "waiting" },
    ],
    acceptance_status: [],
    last_updated_at: "t",
  };
}

beforeEach(() => {
  store._reset();
  postCommandMock.mockReset();
  postCommandMock.mockResolvedValue({ command_id: "c1", status: "received", seq: 5, rejection_reason: null, created_at: "t" });
});

describe("ApprovalModal", () => {
  it("approve_sends_command_not_mutate", async () => {
    store.setSnapshot(snapshotWaiting());
    const before = store.getState().snapshot;
    render(<ApprovalModal />);
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));

    expect(postCommandMock).toHaveBeenCalledOnce();
    const cmd = postCommandMock.mock.calls[0][0];
    expect(cmd.command_type).toBe("ApproveCheckpoint");
    expect(cmd.payload.checkpoint_id).toBe("cp_demo_1");
    // no optimistic mutation: state is identical until a runtime event resolves it
    expect(store.getState().snapshot).toBe(before);
  });

  it("reject_blocks_action", async () => {
    store.setSnapshot(snapshotWaiting());
    render(<ApprovalModal />);
    await userEvent.click(screen.getByRole("button", { name: /reject/i }));
    expect(postCommandMock.mock.calls[0][0].command_type).toBe("RejectCheckpoint");
  });

  it("renders nothing when no checkpoint is waiting", () => {
    const { container } = render(<ApprovalModal />);
    expect(container).toBeEmptyDOMElement();
  });
});
