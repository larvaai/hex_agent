/**
 * Session bar — switch conversations or start a new one. Epic E21 / IDE.
 *
 * Switching is a one-liner (``setCurrent``); the App's wiring effect keys on the current session and
 * re-points the stream + snapshot + diffs at it. New creates a fresh server-side session (its own
 * event buffer + diff baseline) and switches to it.
 */
import { useEffect } from "react";

import { createSession } from "../adapter/sessions";
import { sessionStore, useSessionState } from "../state/sessionStore";

export function SessionBar() {
  const { current, sessions } = useSessionState();

  useEffect(() => {
    void sessionStore.refreshList();
  }, []);

  const onNew = async () => {
    try {
      const created = await createSession();
      await sessionStore.refreshList();
      sessionStore.setCurrent(created.id);
    } catch {
      /* server down — ignore */
    }
  };

  return (
    <span className="ide-sessions">
      <select
        className="ide-session-select"
        value={current}
        onChange={(e) => sessionStore.setCurrent(e.target.value)}
        aria-label="active session"
      >
        {sessions.length === 0 ? (
          <option value={current}>{current}</option>
        ) : (
          sessions.map((s) => (
            <option key={s.id} value={s.id}>
              {s.title}
              {s.status && s.status !== "idle" ? ` · ${s.status}` : ""}
            </option>
          ))
        )}
      </select>
      <button className="ide-newsession" onClick={() => void onNew()} aria-label="new session">
        + New
      </button>
    </span>
  );
}
