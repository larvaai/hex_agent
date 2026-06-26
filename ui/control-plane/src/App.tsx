/**
 * App shell — the IDE. Epic E21 / IDE.
 *
 * Left: file explorer. Center: editor / diff tabs. Right: the agent observability rail (graph,
 * timeline, inspector). Bottom: the prompt dock — talk to the agent, watch it edit, review the diff.
 *
 * Data still flows one way for runtime state: the control adapter streams loop.* events into the
 * control store, components read it. The file side adds a parallel store the editor *does* write to —
 * editing is the point. When new agent events arrive, we refresh the tree + diffs so files the agent
 * writes appear and flash live.
 */
import { useEffect } from "react";

import { getSnapshot, openStream } from "./adapter/controlPlane";
import { AgentGraph } from "./components/AgentGraph";
import { AgentInspector } from "./components/AgentInspector";
import { ApprovalModal } from "./components/ApprovalModal";
import { CodeEditor } from "./components/CodeEditor";
import { DiffPanel } from "./components/DiffPanel";
import { EventTimeline } from "./components/EventTimeline";
import { FileExplorer } from "./components/FileExplorer";
import { PromptBox } from "./components/PromptBox";
import { SESSION_ID } from "./config";
import { fileStore, useFileState } from "./state/fileStore";
import { store, useCPState } from "./state/store";

const BADGE: Record<string, string> = {
  connecting: "#b58900",
  open: "#2aa198",
  reconnecting: "#cb4b16",
  closed: "#586e75",
};

const RUN_BADGE: Record<string, string> = {
  finished: "#2aa198",
  failed: "#dc322f",
  blocked: "#cb4b16",
  waiting_tool: "#268bd2",
  in_discussion: "#b58900",
};

export default function App() {
  const { status, snapshot, events } = useCPState();
  const { view, diffs } = useFileState();

  // Wire the control stream once.
  useEffect(() => {
    let active = true;
    const refresh = () => {
      getSnapshot(SESSION_ID)
        .then((snap) => active && store.setSnapshot(snap))
        .catch(() => {});
    };
    refresh();
    const handle = openStream(store.applyEvent, { onStatus: store.setStatus, onResync: refresh });
    return () => {
      active = false;
      handle.close();
    };
  }, []);

  // As the agent emits events: re-fold the snapshot (so the graph + status pill track the live
  // stream) and refresh files it wrote. Debounced on a trailing-edge timer so a burst of events
  // collapses to one refresh instead of 3 fetches per event; the `active` guard drops a stale
  // resolution after unmount or a superseding event.
  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      if (!active) return;
      getSnapshot(SESSION_ID)
        .then((snap) => active && store.setSnapshot(snap))
        .catch(() => {});
      void fileStore.refreshTree();
      void fileStore.refreshDiffs();
    }, 250);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [events.length]);

  const runStatus = snapshot?.status ?? "created";

  return (
    <div className="ide">
      <header className="ide-header">
        <span className="ide-logo">⬡ Agent IDE</span>
        <span className="ide-runpill" style={{ background: RUN_BADGE[runStatus] ?? "#586e75" }}>{runStatus}</span>
        <span className="ide-grow" />
        <span className="ide-badge" style={{ background: BADGE[status] ?? "#586e75" }} aria-label={`connection ${status}`}>
          {status}
        </span>
        <span className="ide-session">session: {snapshot?.session_id ?? SESSION_ID}</span>
      </header>

      <div className="ide-body">
        <aside className="ide-left" aria-label="Explorer">
          <FileExplorer />
        </aside>

        <main className="ide-center" aria-label="Editor">
          <div className="ide-center-head">
            <button className={`ide-seg${view === "editor" ? " is-active" : ""}`} onClick={() => void fileStore.setView("editor")}>
              Editor
            </button>
            <button className={`ide-seg${view === "diff" ? " is-active" : ""}`} onClick={() => void fileStore.setView("diff")}>
              Changes{diffs.length ? ` (${diffs.length})` : ""}
            </button>
          </div>
          <div className="ide-center-body">{view === "editor" ? <CodeEditor /> : <DiffPanel />}</div>
        </main>

        <aside className="ide-right" aria-label="Agent">
          <section className="ide-rail-panel ide-rail-graph">
            <h3 className="ide-rail-title">Agent graph</h3>
            <div className="ide-rail-graph-body">
              <AgentGraph />
            </div>
          </section>
          <section className="ide-rail-panel">
            <h3 className="ide-rail-title">Timeline</h3>
            <EventTimeline />
          </section>
          <section className="ide-rail-panel">
            <h3 className="ide-rail-title">Inspector</h3>
            <AgentInspector />
          </section>
        </aside>
      </div>

      <footer className="ide-prompt-dock" aria-label="Prompt">
        <PromptBox />
      </footer>

      <ApprovalModal />
    </div>
  );
}
