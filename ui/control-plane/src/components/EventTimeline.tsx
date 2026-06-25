// STUB (Phase 4) — replaced in Phase 5 by the virtualized, filterable Event Timeline.
import { useCPState } from "../state/store";

export function EventTimeline() {
  const { events } = useCPState();
  return (
    <ol className="cp-timeline-list">
      {events.map((e) => (
        <li key={e.seq}>
          <code>#{e.seq}</code> {e.type}
        </li>
      ))}
    </ol>
  );
}
