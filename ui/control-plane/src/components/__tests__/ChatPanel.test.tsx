/**
 * L5 — ChatPanel (zero coverage before this). Folds chat.* + loop.tool events into bubbles + tool
 * steps (✓/✗), shows Stop only while the run is live, and never renders a raw secret. Store-driven
 * exactly like the existing EventTimeline test.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { store } from "../../state/store";
import { ChatPanel } from "../ChatPanel";

beforeEach(() => store._reset());
afterEach(() => vi.restoreAllMocks());

describe("ChatPanel", () => {
  it("folds chat + tool events into bubbles and tool steps", () => {
    store.applyEvent({ type: "chat.user", seq: 1, uiPayload: { text: "build calc" } });
    store.applyEvent({ type: "loop.tool", seq: 2, uiPayload: { tool: "fs_write", ok: true, path: "calc.py" } });
    store.applyEvent({ type: "loop.tool", seq: 3, uiPayload: { tool: "fs_read", ok: false } });
    store.applyEvent({ type: "chat.assistant", seq: 4, uiPayload: { text: "done — wrote calc.py" } });
    const { container } = render(<ChatPanel />);

    expect(screen.getByText("build calc")).toBeInTheDocument();
    expect(screen.getByText("done — wrote calc.py")).toBeInTheDocument();
    const tools = container.querySelectorAll(".chat-tool");
    expect(tools.length).toBe(2);
    expect(container.querySelector('.chat-tool[data-ok="true"] .chat-tool-name')?.textContent).toBe("fs_write");
    expect(container.querySelector('.chat-tool[data-ok="false"] .chat-tool-name')?.textContent).toBe("fs_read");
    expect(screen.queryByText(/sk-/)).toBeNull(); // nothing secret-shaped rendered
  });

  it("shows Stop only while the run is live", async () => {
    store.applyEvent({ type: "chat.user", seq: 1, uiPayload: { text: "go" } });
    store.setSnapshot({ session_id: "t", status: "running" } as never);
    render(<ChatPanel />);
    expect(screen.getByLabelText("stop the running agent")).toBeInTheDocument();

    store.setSnapshot({ session_id: "t", status: "finished" } as never);
    await waitFor(() => expect(screen.queryByLabelText("stop the running agent")).toBeNull());
  });
});
