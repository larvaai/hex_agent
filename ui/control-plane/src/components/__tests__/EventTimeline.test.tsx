/**
 * E21 Phase 5 — Event Timeline tests. Maps to S21.19.
 *
 * The timeline is virtualized (thousands of events must not become thousands of DOM nodes), it
 * filters by type, and it shows redaction literally — a "[REDACTED]" value renders as text, never
 * the real secret (R3).
 */
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { store } from "../../state/store";
import { EventTimeline, filterEvents } from "../EventTimeline";
import type { TimelineEntry } from "../../state/store";

function entries(n: number): TimelineEntry[] {
  return Array.from({ length: n }, (_, i) => ({
    seq: i + 1,
    type: i % 5 === 0 ? "loop.tool" : "loop.turn",
    uiPayload: { i },
  }));
}

beforeEach(() => {
  store._reset();
  // @tanstack/react-virtual measures the scroll viewport via offsetHeight (jsdom reports 0).
  // Give it a real height so it computes a small visible window instead of rendering nothing.
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, value: 400 });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, value: 400 });
});

afterEach(() => {
  delete (HTMLElement.prototype as unknown as { offsetHeight?: number }).offsetHeight;
  delete (HTMLElement.prototype as unknown as { offsetWidth?: number }).offsetWidth;
  vi.restoreAllMocks();
});

describe("EventTimeline", () => {
  it("filterEvents filters by type", () => {
    const all = entries(2000);
    const tools = filterEvents(all, "loop.tool");
    expect(tools.length).toBe(400); // every 5th
    expect(tools.every((e) => e.type === "loop.tool")).toBe(true);
  });

  it("timeline_virtualized_dom_far_below_total", () => {
    for (const e of entries(2000)) store.applyEvent({ type: e.type, seq: e.seq, uiPayload: e.uiPayload });
    render(<EventTimeline />);
    const rows = screen.getAllByTestId(/^tl-row-/);
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.length).toBeLessThan(100); // virtualized: nowhere near 2000
  });

  it("timeline_shows_redacted", () => {
    store.applyEvent({ type: "loop.tool", seq: 1, uiPayload: { tool: "http", api_key: "[REDACTED]" } });
    render(<EventTimeline />);
    expect(screen.getByText(/\[REDACTED\]/)).toBeInTheDocument();
    expect(screen.queryByText(/sk-/)).toBeNull();
  });
});
