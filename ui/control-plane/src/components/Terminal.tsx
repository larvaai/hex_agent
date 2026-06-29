/**
 * Terminal panel — run a workspace command and read its output. Epic E21 / IDE.
 *
 * Not a PTY: each entry is a request/response (the backend runs the argv with no shell, gated by the
 * same policy the agent's terminal_run tool uses, capped at 30s and 60k of output). That covers the
 * opencode use — run a build/test/ls and see the result — without a websocket. Output is jailed to
 * var/workspace; dangerous argv (shell metachars, destructive commands) are refused server-side.
 */
import { useEffect, useRef, useState } from "react";

import { runTerminal } from "../adapter/sessions";

interface Entry {
  cmd: string;
  stdout: string;
  stderr: string;
  rc: number;
}

export function Terminal() {
  const [cmd, setCmd] = useState("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [entries.length, busy]);

  const run = async () => {
    const c = cmd.trim();
    if (!c || busy) return;
    setBusy(true);
    try {
      const r = await runTerminal(c);
      setEntries((e) => [...e, { cmd: c, stdout: r.stdout, stderr: r.stderr, rc: r.returncode }]);
      setCmd("");
    } catch (err) {
      setEntries((e) => [...e, { cmd: c, stdout: "", stderr: (err as Error).message, rc: -1 }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="term">
      <div className="term-log" aria-label="terminal output">
        {entries.length === 0 ? (
          <p className="term-empty">Run a command in the workspace (no shell; policy-gated, 30s cap).</p>
        ) : (
          entries.map((e, i) => (
            <div key={i} className="term-entry">
              <div className="term-cmd">
                <span className="term-prompt">$</span> {e.cmd}
                <span className="term-rc" data-ok={e.rc === 0}>
                  {e.rc === 0 ? "ok" : `exit ${e.rc}`}
                </span>
              </div>
              {e.stdout ? <pre className="term-out">{e.stdout}</pre> : null}
              {e.stderr ? <pre className="term-err">{e.stderr}</pre> : null}
            </div>
          ))
        )}
        <div ref={endRef} />
      </div>
      <div className="term-input">
        <span className="term-prompt">$</span>
        <input
          aria-label="terminal command"
          value={cmd}
          onChange={(e) => setCmd(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void run();
          }}
          placeholder="ls -la"
          spellCheck={false}
          disabled={busy}
        />
      </div>
    </div>
  );
}
