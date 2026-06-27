/**
 * L5 — Terminal (zero coverage before this). Enter runs the command; the entry shows cmd/stdout/rc;
 * the input is disabled while a command is in flight; a server-refused command renders as an error.
 * The terminal adapter is mocked — no real subprocess.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Terminal } from "../Terminal";

vi.mock("../../adapter/sessions", () => ({
  runTerminal: vi.fn(),
  listSessions: vi.fn(),
  createSession: vi.fn(),
  cancelRun: vi.fn(),
}));
import { runTerminal } from "../../adapter/sessions";

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.restoreAllMocks());

describe("Terminal", () => {
  it("Enter runs the command and renders its output + exit ok", async () => {
    vi.mocked(runTerminal).mockResolvedValue({ ok: true, argv: ["ls"], returncode: 0, stdout: "file.txt\n", stderr: "" });
    render(<Terminal />);
    await userEvent.type(screen.getByLabelText("terminal command"), "ls{Enter}");

    expect(await screen.findByText("file.txt")).toBeInTheDocument();
    expect(vi.mocked(runTerminal)).toHaveBeenCalledWith("ls");
    expect(screen.getByText("ok")).toBeInTheDocument();
  });

  it("disables input while a command is in flight", async () => {
    let resolve!: (v: { ok: boolean; argv: string[]; returncode: number; stdout: string; stderr: string }) => void;
    vi.mocked(runTerminal).mockReturnValue(new Promise((r) => (resolve = r)));
    render(<Terminal />);
    const input = screen.getByLabelText("terminal command") as HTMLInputElement;
    await userEvent.type(input, "sleep{Enter}");

    await waitFor(() => expect(input).toBeDisabled()); // busy
    resolve({ ok: true, argv: ["sleep"], returncode: 0, stdout: "", stderr: "" });
    await waitFor(() => expect(input).not.toBeDisabled()); // done
  });

  it("renders a server-refused command as an error", async () => {
    vi.mocked(runTerminal).mockRejectedValue(new Error("command blocked by policy"));
    render(<Terminal />);
    await userEvent.type(screen.getByLabelText("terminal command"), "rm -rf /{Enter}");

    expect(await screen.findByText("command blocked by policy")).toBeInTheDocument();
    expect(screen.getByText("exit -1")).toBeInTheDocument();
  });
});
