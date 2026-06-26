/**
 * App shell — the IDE. Epic E21 / IDE.
 *
 * Left: file explorer. Center: editor / diff tabs. Right: tabbed Chat | Agent — Chat is the
 * conversation loop (prompt → steps → answer), Agent is the observability rail (graph, timeline,
 * inspector). Bottom: a collapsible terminal dock. Header: session switcher + run/connection status.
 *
 * Runtime state flows one way (the control adapter streams events into the store; components read it);
 * the file side adds a parallel store the editor *does* write to. The wiring effect keys on the
 * current session, so switching conversations re-points the stream, snapshot, and diffs at it.
 */
import { useEffect, useState } from "react";

import { getSnapshot, openStream } from "./adapter/controlPlane";
import { AgentGraph } from "./components/AgentGraph";
import { AgentInspector } from "./components/AgentInspector";
import { ApprovalModal } from "./components/ApprovalModal";
import { ChatPanel } from "./components/ChatPanel";
import { CodeEditor } from "./components/CodeEditor";
import { DiffPanel } from "./components/DiffPanel";
import { EventTimeline } from "./components/EventTimeline";
import { FileExplorer } from "./components/FileExplorer";
import { SessionBar } from "./components/SessionBar";
import { Terminal } from "./components/Terminal";
import { fileStore, useFileState } from "./state/fileStore";
import { sessionStore, useSessionState } from "./state/sessionStore";
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
  cancelled: "#cb4b16",
  blocked: "#cb4b16",
  waiting_tool: "#268bd2",
  in_discussion: "#b58900",
};

type RightTab = "chat" | "agent";

export default function App() {
  const { status, snapshot, events } = useCPState();
  const { view, diffs } = useFileState();
  const { current } = useSessionState();
  const [rightTab, setRightTab] = useState<RightTab>("chat");
  const [termOpen, setTermOpen] = useState(false);

  // Wire the control stream for the current session. Re-runs on switch: reset the store so the new
  // session's replay lands clean, then re-point snapshot + stream + diffs at it.
  useEffect(() => {
    store.resetForSession();
    fileStore.resetForSession(); // reset BOTH stores so the switched-to session lands clean
    let active = true;
    const refresh = () => {
      getSnapshot(current)
        .then((snap) => active && store.setSnapshot(snap))
        .catch(() => {});
    };
    refresh();
    void fileStore.refreshTree();
    void fileStore.refreshDiffs();
    const handle = openStream(store.applyEvent, { session: current, onStatus: store.setStatus, onResync: refresh });
    return () => {
      active = false;
      handle.close();
    };
  }, [current]);

  // As events arrive: re-fold the snapshot (graph + run pill track the live stream), refresh files
  // the agent wrote, and refresh the session list (status chips). Debounced on a trailing-edge timer.
  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      if (!active) return;
      getSnapshot(current)
        .then((snap) => active && store.setSnapshot(snap))
        .catch(() => {});
      void fileStore.refreshTree();
      void fileStore.refreshDiffs();
      void sessionStore.refreshList();
    }, 250);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [events.length, current]);

  const runStatus = snapshot?.status ?? "created";

  return (
    <div className={`ide${termOpen ? " is-term-open" : ""}`}>
      <header className="ide-header">
        <span className="ide-logo">⬡ Agent IDE</span>
        <span className="ide-runpill" style={{ background: RUN_BADGE[runStatus] ?? "#586e75" }}>{runStatus}</span>
        <SessionBar />
        <span className="ide-grow" />
        <button
          className={`ide-termtoggle${termOpen ? " is-active" : ""}`}
          onClick={() => setTermOpen((v) => !v)}
          aria-label="toggle terminal"
        >
          ▸_ Terminal
        </button>
        <span className="ide-badge" style={{ background: BADGE[status] ?? "#586e75" }} aria-label={`connection ${status}`}>
          {status}
        </span>
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
          <div className="ide-rail-tabs">
            <button className={`ide-seg${rightTab === "chat" ? " is-active" : ""}`} onClick={() => setRightTab("chat")}>
              Chat
            </button>
            <button className={`ide-seg${rightTab === "agent" ? " is-active" : ""}`} onClick={() => setRightTab("agent")}>
              Agent
            </button>
          </div>
          {rightTab === "chat" ? (
            <ChatPanel />
          ) : (
            <div className="ide-rail-agent">
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
            </div>
          )}
        </aside>
      </div>

      {termOpen ? (
        <section className="ide-term-dock" aria-label="Terminal">
          <div className="ide-term-head">
            <span className="ide-term-title">Terminal · workspace</span>
            <button className="ide-term-close" onClick={() => setTermOpen(false)} aria-label="close terminal">
              ✕
            </button>
          </div>
          <Terminal />
        </section>
      ) : null}

      <ApprovalModal />
    </div>
  );
}
