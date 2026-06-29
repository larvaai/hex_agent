/**
 * L5 — CodeEditor (zero coverage before this). CodeMirror is stubbed (jsdom can't paint it), so the
 * assertions bite the wrapper/state: the tab bar, the dirty pill, language detection, and that
 * Cmd/Ctrl+S writes the buffer through the file store. File adapter mocked.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fileStore } from "../../state/fileStore";
import { CodeEditor } from "../CodeEditor";

vi.mock("@uiw/react-codemirror", () => ({
  default: ({ value }: { value: string }) => <textarea data-testid="cm" value={value} readOnly />,
}));
vi.mock("../../adapter/files", () => ({
  readFile: vi.fn(),
  writeFile: vi.fn(),
  getTree: vi.fn(),
  getDiffs: vi.fn(),
  createPath: vi.fn(),
  renamePath: vi.fn(),
  deletePath: vi.fn(),
}));
import { getDiffs, getTree, readFile, writeFile } from "../../adapter/files";

beforeEach(() => {
  fileStore.resetForSession();
  vi.mocked(readFile).mockResolvedValue({ scope: "workspace", path: "a/b.py", name: "b.py", size: 4, content: "x=1\n", language: "python" });
  // saveActive() refreshes tree+diffs after a write; keep those harmless so save completes cleanly
  vi.mocked(getTree).mockResolvedValue({ scope: "workspace", root: "/", tree: null, entries: 0, truncated: false });
  vi.mocked(getDiffs).mockResolvedValue([]);
});
afterEach(() => vi.clearAllMocks());

describe("CodeEditor", () => {
  it("opens a tab, flags dirty on edit, and Cmd/Ctrl+S saves the buffer", async () => {
    await fileStore.openFile("workspace", "a/b.py");
    render(<CodeEditor />);

    // tab bar shows scope:path and the seed content is bound into the editor
    expect(screen.getByTitle("workspace: a/b.py")).toBeInTheDocument();
    expect((screen.getByTestId("cm") as HTMLTextAreaElement).value).toBe("x=1\n");
    expect(fileStore.activeTab()?.language).toBe("python"); // language detection

    // edit → dirty pill ● + Save enabled
    act(() => fileStore.editActive("x=2\n"));
    expect(screen.getByText(/●/)).toBeInTheDocument();
    expect(screen.getByText("Save")).toBeEnabled();

    // Cmd/Ctrl+S writes the current buffer through the store
    vi.mocked(writeFile).mockResolvedValue({ bytes: 4 });
    fireEvent.keyDown(window, { key: "s", metaKey: true });
    await waitFor(() => expect(vi.mocked(writeFile)).toHaveBeenCalledWith("workspace", "a/b.py", "x=2\n"));
    await waitFor(() => expect(screen.queryByText(/●/)).toBeNull()); // dirty cleared after save
  });

  it("shows the empty state with no open file", () => {
    render(<CodeEditor />);
    expect(screen.getByText(/Open a file from the explorer/i)).toBeInTheDocument();
  });
});
