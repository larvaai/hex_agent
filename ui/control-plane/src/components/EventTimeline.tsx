/**
 * Event Timeline — virtualized, filterable stream view. Epic E21 (S21.19).
 *
 * Thousands of events must not become thousands of DOM nodes, so the list is virtualized
 * (@tanstack/react-virtual). Redaction is honoured by construction: each row renders the event's
 * ui_payload, which already carries "[REDACTED]" where a secret was — the raw value never reaches here.
 */
import { useVirtualizer } from "@tanstack/react-virtual";
import { useMemo, useRef, useState } from "react";

import { useCPState, type TimelineEntry } from "../state/store";

export function filterEvents(events: TimelineEntry[], filter: string): TimelineEntry[] {
  const f = filter.trim().toLowerCase();
  if (!f) return events;
  return events.filter(
    (e) => e.type.toLowerCase().includes(f) || JSON.stringify(e.uiPayload).toLowerCase().includes(f),
  );
}

const ROW_HEIGHT = 30;

export function EventTimeline() {
  const { events } = useCPState();
  const [filter, setFilter] = useState("");
  const filtered = useMemo(() => filterEvents(events, filter), [events, filter]);
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: filtered.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 8,
  });

  return (
    <div className="cp-timeline">
      <input
        className="cp-filter"
        placeholder="filter type / agent / tool…"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        style={{ width: "100%", marginBottom: 6, background: "#0b1620", color: "#c9d6df", border: "1px solid #1e3343" }}
      />
      <div ref={parentRef} style={{ height: 360, overflow: "auto" }}>
        <div style={{ height: virtualizer.getTotalSize(), position: "relative", width: "100%" }}>
          {virtualizer.getVirtualItems().map((item) => {
            const e = filtered[item.index];
            return (
              <div
                key={item.key}
                data-testid={`tl-row-${e.seq}`}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  height: ROW_HEIGHT,
                  transform: `translateY(${item.start}px)`,
                  fontSize: 12,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                <code style={{ color: "#6b8294" }}>#{e.seq}</code>{" "}
                <span style={{ color: "#268bd2" }}>{e.type}</span>{" "}
                <span style={{ color: "#93a1a1" }}>{JSON.stringify(e.uiPayload)}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
