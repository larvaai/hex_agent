import { describe, it, expect } from "vitest";
import { canvasToTopology, topologyToCanvas, type CanvasNode, type CanvasEdge } from "./serialize";

const planner: CanvasNode = { id: "plan", type: "agent", position: { x: 10, y: 20 }, data: { role: "planner", entry: true } };
const coder: CanvasNode = { id: "code", type: "agent", position: { x: 200, y: 20 }, data: { role: "coder" } };

describe("canvasToTopology", () => {
  it("maps 2 agent nodes + a delegates_to edge to topology JSON", () => {
    const edges: CanvasEdge[] = [{ source: "plan", target: "code", type: "delegates_to" }];
    const topo = canvasToTopology([planner, coder], edges);
    expect(topo.version).toBe(1);
    expect(topo.nodes.map((n) => n.type)).toEqual(["agent", "agent"]);
    expect(topo.nodes[0].role).toBe("planner");
    expect(topo.nodes[0].entry).toBe(true);
    expect(topo.edges).toEqual([{ from: "plan", to: "code", type: "delegates_to" }]);
  });

  it("puts UI-meta under attrs.ui, never on a top-level required key", () => {
    const topo = canvasToTopology([planner], []);
    expect(topo.nodes[0].ui).toEqual({ position: { x: 10, y: 20 } });
    // position must NOT leak to the node top level (would corrupt validate/wiring)
    expect((topo.nodes[0] as Record<string, unknown>).position).toBeUndefined();
    expect(topo.nodes[0].role).toBe("planner"); // required attr untouched by ui meta
  });

  it("does NOT invent a missing required attr (lets the server 422)", () => {
    const noRole: CanvasNode = { id: "x", type: "agent", position: { x: 0, y: 0 }, data: { role: "" } };
    const topo = canvasToTopology([noRole], []);
    expect("role" in topo.nodes[0]).toBe(false); // absent, not silently defaulted
  });

  it("defaults version to 1 and omits budget unless given", () => {
    expect(canvasToTopology([planner], []).budget).toBeUndefined();
    expect(canvasToTopology([planner], [], { max_llm_calls: 50 }).budget).toEqual({ max_llm_calls: 50 });
  });

  it("round-trips position through topologyToCanvas", () => {
    const topo = canvasToTopology([planner, coder], [{ source: "plan", target: "code", type: "delegates_to" }]);
    const back = topologyToCanvas(topo);
    expect(back.nodes[0].position).toEqual({ x: 10, y: 20 });
    expect(back.nodes[0].data.role).toBe("planner");
    expect(back.edges[0]).toEqual({ source: "plan", target: "code", type: "delegates_to" });
  });
});
