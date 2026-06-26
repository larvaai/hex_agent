/**
 * E21 Phase 6 — Prompt box test. Maps to S21.15.
 *
 * Send posts a real SubmitPrompt RuntimeCommand through the adapter and shows the returned
 * CommandAck (command_id + status). The write path is "emit a command", never a direct state edit.
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

import { PromptBox } from "../PromptBox";

beforeEach(() => {
  postCommandMock.mockReset();
  postCommandMock.mockResolvedValue({ command_id: "cmd-42", status: "received", seq: 7, rejection_reason: null, created_at: "t" });
});

describe("PromptBox", () => {
  it("send_posts_command_and_shows_ack", async () => {
    render(<PromptBox />);
    await userEvent.type(screen.getByLabelText(/prompt/i), "do the thing");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(postCommandMock).toHaveBeenCalledOnce();
    const cmd = postCommandMock.mock.calls[0][0];
    expect(cmd.command_type).toBe("SubmitPrompt");
    expect(cmd.payload.prompt).toBe("do the thing");

    await screen.findByText(/cmd-42/);
    expect(screen.getByRole("status")).toHaveTextContent("received");
  });

  it("does not send an empty prompt", async () => {
    render(<PromptBox />);
    await userEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(postCommandMock).not.toHaveBeenCalled();
  });
});
