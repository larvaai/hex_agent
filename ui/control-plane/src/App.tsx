/**
 * App shell — wires the adapter stream into the store and lays out the control plane. Epic E21.
 *
 * Data flows one way: getSnapshot + openStream → store; components read the store and dispatch
 * RuntimeCommands through the adapter. The shell never mutates agent/checkpoint state itself.
 * Phase 5 mounts the Graph + Timeline; Phase 6 mounts the Inspector + Approval modal + Prompt box.
 */
import { useEffect } from "react";

import { getSnapshot, openStream } from "./adapter/controlPlane";
import { AgentGraph } from "./components/AgentGraph";
import { AgentInspector } from "./components/AgentInspector";
import { ApprovalModal } from "./components/ApprovalModal";
import { EventTimeline } from "./components/EventTimeline";
import { PromptBox } from "./components/PromptBox";
import { SESSION_ID } from "./config";
import { store, useCPState } from "./state/store";

const BADGE: Record<string, string> = {
  connecting: "#b58900",
  open: "#2aa198",
  reconnecting: "#cb4b16",
  closed: "#586e75",
};

export default function App() {
  const { status, snapshot } = useCPState();

  useEffect(() => {
    let active = true;
    const refresh = () => {
      getSnapshot(SESSION_ID)
        .then((snap) => active && store.setSnapshot(snap))
        .catch(() => {});
    };
    refresh();
    const handle = openStream(store.applyEvent, {
      onStatus: store.setStatus,
      onResync: refresh, // out-of-ring → re-fetch the snapshot (F7)
    });
    return () => {
      active = false;
      handle.close();
    };
  }, []);

  return (
    <div className="cp-app">
      <header className="cp-header">
        <h1>E21 Control Plane</h1>
        <span className="cp-badge" style={{ background: BADGE[status] ?? "#586e75" }} aria-label={`connection ${status}`}>
          {status}
        </span>
        <span className="cp-session">session: {snapshot?.session_id ?? "—"}</span>
      </header>

      <main className="cp-grid">
        <section className="cp-panel cp-graph" aria-label="Agent Graph">
          <AgentGraph />
        </section>
        <section className="cp-panel cp-timeline" aria-label="Event Timeline">
          <EventTimeline />
        </section>
        <section className="cp-panel cp-inspector" aria-label="Agent Inspector">
          <AgentInspector />
        </section>
        <section className="cp-panel cp-prompt" aria-label="Prompt">
          <PromptBox />
        </section>
      </main>

      <ApprovalModal />
    </div>
  );
}
