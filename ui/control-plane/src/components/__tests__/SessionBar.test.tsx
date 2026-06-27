/**
 * L5 — SessionBar (zero coverage before this). Lists sessions with status chips, marks the current
 * one, and New creates + switches. Sessions adapter mocked; session store driven through its methods.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { sessionStore } from "../../state/sessionStore";
import { SessionBar } from "../SessionBar";

vi.mock("../../adapter/sessions", () => ({
  listSessions: vi.fn(),
  createSession: vi.fn(),
  cancelRun: vi.fn(),
  runTerminal: vi.fn(),
}));
import { createSession, listSessions } from "../../adapter/sessions";

const meta = (id: string, title: string, status: string) =>
  ({ id, title, status, last_prompt: "", created_at: "2026-06-27T00:00:00" });

beforeEach(() => {
  vi.mocked(listSessions).mockResolvedValue({
    sessions: [meta("t1_demo", "Session 1", "idle"), meta("s_abc", "Feature X", "running")],
    default: "t1_demo",
  });
});
afterEach(() => vi.clearAllMocks());

describe("SessionBar", () => {
  it("lists sessions with status chips and the current value", async () => {
    await sessionStore.refreshList();
    sessionStore.setCurrent("t1_demo");
    render(<SessionBar />);

    expect(await screen.findByRole("option", { name: "Session 1" })).toBeInTheDocument(); // idle → no chip
    expect(screen.getByRole("option", { name: "Feature X · running" })).toBeInTheDocument(); // status chip
    expect((screen.getByLabelText("active session") as HTMLSelectElement).value).toBe("t1_demo");
  });

  it("New creates a session and switches to it", async () => {
    vi.mocked(createSession).mockResolvedValue(meta("s_new", "New", "idle"));
    await sessionStore.refreshList();
    render(<SessionBar />);
    fireEvent.click(screen.getByLabelText("new session"));
    await waitFor(() => expect(vi.mocked(createSession)).toHaveBeenCalled());
    await waitFor(() => expect(sessionStore.current()).toBe("s_new"));
  });
});
