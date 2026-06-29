/**
 * L5 — FileExplorer (IDE-half, zero coverage before this). Tree recursion, the agent-changed dot,
 * scope toggle, and open-on-click. The file adapter is mocked; the store is driven through its real
 * methods so the assertions bite the render/fold logic, not the network.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fileStore } from "../../state/fileStore";
import { FileExplorer } from "../FileExplorer";
import type { TreeNode, TreeResponse } from "../../adapter/files";

vi.mock("../../adapter/files", () => ({
  getTree: vi.fn(),
  readFile: vi.fn(),
  writeFile: vi.fn(),
  createPath: vi.fn(),
  renamePath: vi.fn(),
  deletePath: vi.fn(),
  getDiffs: vi.fn(),
}));
import { getTree, readFile } from "../../adapter/files";

const dir = (name: string, children: TreeNode[], mtime = 1): TreeNode =>
  ({ name, path: name, type: "directory", size: 0, mtime_ns: mtime, children });
const file = (name: string, path: string, mtime = 1): TreeNode =>
  ({ name, path, type: "file", size: 1, mtime_ns: mtime });
const tree = (children: TreeNode[]): TreeResponse =>
  ({ scope: "workspace", root: "/ws", tree: { name: "ws", path: "", type: "directory", size: 0, mtime_ns: 0, children }, entries: children.length, truncated: false });

beforeEach(() => {
  fileStore.resetForSession();
  vi.mocked(readFile).mockResolvedValue({ scope: "workspace", path: "readme.md", name: "readme.md", size: 1, content: "x", language: "markdown" });
});
afterEach(() => vi.clearAllMocks());

describe("FileExplorer", () => {
  it("renders nested dirs and files (tree recursion)", async () => {
    vi.mocked(getTree).mockResolvedValue(tree([dir("src", [file("app.ts", "src/app.ts")]), file("readme.md", "readme.md")]));
    await fileStore.refreshTree();
    render(<FileExplorer />);
    expect(await screen.findByText("src")).toBeInTheDocument();
    expect(screen.getByText("app.ts")).toBeInTheDocument(); // depth-0 dir is open → child visible
    expect(screen.getByText("readme.md")).toBeInTheDocument();
  });

  it("clicking a file opens it (openFile with the file's scope+path)", async () => {
    vi.mocked(getTree).mockResolvedValue(tree([file("readme.md", "readme.md")]));
    const spy = vi.spyOn(fileStore, "openFile").mockResolvedValue();
    await fileStore.refreshTree();
    render(<FileExplorer />);
    fireEvent.click(await screen.findByText("readme.md"));
    expect(spy).toHaveBeenCalledWith("workspace", "readme.md");
  });

  it("scope toggle re-fetches the project tree", async () => {
    vi.mocked(getTree).mockResolvedValue(tree([file("readme.md", "readme.md")]));
    await fileStore.refreshTree();
    render(<FileExplorer />);
    fireEvent.click(await screen.findByRole("button", { name: "project" }));
    await waitFor(() => expect(vi.mocked(getTree)).toHaveBeenCalledWith("project"));
  });

  it("marks an agent-changed file with the dot", async () => {
    // first refresh seeds the baseline mtimes; the mount refresh sees a bumped mtime → `changed`
    vi.mocked(getTree)
      .mockResolvedValueOnce(tree([file("a.py", "a.py", 100)]))
      .mockResolvedValue(tree([file("a.py", "a.py", 200)]));
    await fileStore.refreshTree();
    const { container } = render(<FileExplorer />);
    await waitFor(() => expect(container.querySelector(".ide-tree-dot")).toBeTruthy());
  });
});
