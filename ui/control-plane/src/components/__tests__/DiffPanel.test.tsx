/**
 * L5 — DiffPanel (zero coverage before this). Renders the agent's diff set: status colour + stat,
 * +/- coloured body lines, open-on-click, and the empty state. Diff adapter mocked.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fileStore } from "../../state/fileStore";
import { DiffPanel } from "../DiffPanel";

vi.mock("../../adapter/files", () => ({
  getDiffs: vi.fn(),
  getTree: vi.fn(),
  readFile: vi.fn(),
  writeFile: vi.fn(),
  createPath: vi.fn(),
  renamePath: vi.fn(),
  deletePath: vi.fn(),
}));
import { getDiffs } from "../../adapter/files";

const MODIFIED = {
  path: "calc.py",
  status: "modified" as const,
  additions: 2,
  deletions: 1,
  diff: "@@ -1 +1,2 @@\n-old\n+new1\n+new2\n",
};

beforeEach(() => fileStore.resetForSession());
afterEach(() => vi.clearAllMocks());

describe("DiffPanel", () => {
  it("renders status, stat, and +/- body lines", async () => {
    vi.mocked(getDiffs).mockResolvedValue([MODIFIED]);
    await fileStore.refreshDiffs();
    const { container } = render(<DiffPanel />);

    expect(screen.getByText("calc.py")).toBeInTheDocument();
    expect(container.querySelector(".ide-diff-status.is-modified")).toBeTruthy();
    expect(screen.getByText("+2")).toBeInTheDocument();
    expect(screen.getByText("−1")).toBeInTheDocument();
    expect(container.querySelector(".ide-diff-add")).toBeTruthy(); // a + line is coloured
    expect(screen.getByText("+new1")).toBeInTheDocument();
    expect(screen.getByText("-old")).toBeInTheDocument();
  });

  it("clicking a diff header opens the file in the editor", async () => {
    vi.mocked(getDiffs).mockResolvedValue([MODIFIED]);
    const spy = vi.spyOn(fileStore, "openFile").mockResolvedValue();
    await fileStore.refreshDiffs();
    render(<DiffPanel />);
    fireEvent.click(screen.getByText("calc.py"));
    expect(spy).toHaveBeenCalledWith("workspace", "calc.py");
  });

  it("shows the empty state when there are no diffs", async () => {
    vi.mocked(getDiffs).mockResolvedValue([]);
    await fileStore.refreshDiffs();
    render(<DiffPanel />);
    expect(screen.getByText(/No changes yet/i)).toBeInTheDocument();
  });
});
