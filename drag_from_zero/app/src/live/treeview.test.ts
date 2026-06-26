import { describe, it, expect } from "vitest";
import { nodeVisual } from "./status";

describe("nodeVisual — renders the server verdict verbatim, never faked-pass", () => {
  it("FAIL verdict renders blocked (red), never green", () => {
    const v = nodeVisual({ verdict: "FAIL", runtime: { status: "blocked" } });
    expect(v.cls).toBe("blocked");
    expect(v.cls).not.toBe("done");
  });

  it("PASS verdict renders done", () => {
    expect(nodeVisual({ verdict: "PASS", runtime: { status: "done" } }).cls).toBe("done");
  });

  it("unverified renders neutral — never a faked pass, even when the model claimed done", () => {
    const v = nodeVisual({ verdict: "unverified", runtime: { status: "done" } });
    expect(v.cls).toBe("unverified");
    expect(v.cls).not.toBe("done");
    expect(v.label).not.toMatch(/pass/i);
  });

  it("pending stays pending", () => {
    expect(nodeVisual({ verdict: "pending", runtime: { status: "pending" } }).cls).toBe("pending");
  });
});
