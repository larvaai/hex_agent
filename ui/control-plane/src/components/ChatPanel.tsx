/**
 * Chat panel — the conversation thread, the heart of the opencode loop. Epic E21 / IDE.
 *
 * The agent doesn't "chat" in free text (its protocol is strict JSON), so a faithful thread is
 * folded from the event stream the runner already emits: ``chat.user`` (the prompt), ``loop.tool``
 * (each step the agent took, inline), ``chat.assistant`` (the final answer), ``chat.error`` (a
 * failure or a user Stop). Because those events live in the session buffer, the thread reconstructs
 * on reload and when switching sessions — no client-side history to lose.
 *
 * The composer is the existing PromptBox (one door for SubmitPrompt); Stop appears only while a run
 * is live and posts a cooperative cancel for the current session.
 */
import { useEffect, useMemo, useRef } from "react";

import { cancelRun } from "../adapter/sessions";
import { useSessionState } from "../state/sessionStore";
import { useCPState } from "../state/store";
import type { TimelineEntry } from "../state/store";
import { PromptBox } from "./PromptBox";

type Bubble =
  | { seq: number; kind: "user" | "assistant" | "error"; text: string; cancelled?: boolean }
  | { seq: number; kind: "tool"; tool: string; path?: string; ok: boolean };

const RUNNING = new Set(["in_discussion", "waiting_tool", "running", "dispatched"]);

function toBubbles(events: TimelineEntry[]): Bubble[] {
  const out: Bubble[] = [];
  for (const e of events) {
    const p = e.uiPayload as Record<string, unknown>;
    if (e.type === "chat.user") out.push({ seq: e.seq, kind: "user", text: String(p.text ?? "") });
    else if (e.type === "chat.assistant") out.push({ seq: e.seq, kind: "assistant", text: String(p.text ?? "") });
    else if (e.type === "chat.error")
      out.push({ seq: e.seq, kind: "error", text: String(p.text ?? ""), cancelled: Boolean(p.cancelled) });
    else if (e.type === "loop.tool")
      out.push({
        seq: e.seq,
        kind: "tool",
        tool: String(p.tool ?? ""),
        path: p.path ? String(p.path) : undefined,
        ok: Boolean(p.ok),
      });
  }
  return out; // store keeps events seq-sorted
}

function ToolStep({ tool, path, ok }: { tool: string; path?: string; ok: boolean }) {
  return (
    <div className="chat-tool" data-ok={ok}>
      <span className="chat-tool-mark">{ok ? "✓" : "✗"}</span>
      <code className="chat-tool-name">{tool}</code>
      {path ? <span className="chat-tool-path">{path}</span> : null}
    </div>
  );
}

export function ChatPanel() {
  const { events, snapshot } = useCPState();
  const { current } = useSessionState();
  const bubbles = useMemo(() => toBubbles(events), [events]);
  const running = RUNNING.has(snapshot?.status ?? "");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [bubbles.length]);

  return (
    <div className="chat">
      <div className="chat-log" aria-label="conversation">
        {bubbles.length === 0 ? (
          <p className="chat-empty">Ask the agent to read, write, or change files. Watch each step here.</p>
        ) : (
          bubbles.map((b) =>
            b.kind === "tool" ? (
              <ToolStep key={b.seq} tool={b.tool} path={b.path} ok={b.ok} />
            ) : (
              <div key={b.seq} className={`chat-msg chat-${b.kind}`}>
                <span className="chat-role">
                  {b.kind === "user" ? "you" : b.kind === "error" ? (b.cancelled ? "stopped" : "error") : "agent"}
                </span>
                <div className="chat-text">{b.text || (b.kind === "assistant" ? "(no message)" : "")}</div>
              </div>
            ),
          )
        )}
        <div ref={endRef} />
      </div>
      {running ? (
        <button className="chat-stop" onClick={() => void cancelRun(current)} aria-label="stop the running agent">
          ■ Stop
        </button>
      ) : null}
      <PromptBox />
    </div>
  );
}
