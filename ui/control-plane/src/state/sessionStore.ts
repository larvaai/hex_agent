/**
 * Session store — which conversation is active, and the list of all of them. Epic E21 / IDE.
 *
 * Session history (opencode parity) means the UI is no longer pinned to one session id. This holds
 * the *current* session (every command/snapshot/stream/diff is scoped to it) and the known list.
 * ``currentSession()`` is a plain getter so non-React modules (command builder, file store) can read
 * the active id without a hook; React views use ``useSessionState``. Switching is just ``setCurrent``
 * — the App's wiring effect keys on it and re-points the stream + snapshot at the new session.
 */
import { useSyncExternalStore } from "react";

import { listSessions, type SessionMeta } from "../adapter/sessions";
import { SESSION_ID } from "../config";

export interface SessionState {
  current: string;
  sessions: SessionMeta[];
}

type Listener = () => void;

class SessionStore {
  private state: SessionState = { current: SESSION_ID, sessions: [] };
  private listeners = new Set<Listener>();

  getState = (): SessionState => this.state;

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private commit(next: Partial<SessionState>) {
    this.state = { ...this.state, ...next };
    this.listeners.forEach((l) => l());
  }

  current = (): string => this.state.current;

  setCurrent = (id: string): void => {
    if (id !== this.state.current) this.commit({ current: id });
  };

  /** Refresh the session list (status chips track the live run via the snapshot-driven refresh). */
  refreshList = async (): Promise<void> => {
    try {
      const res = await listSessions();
      this.commit({ sessions: res.sessions });
    } catch {
      /* server not up yet — leave the list as-is */
    }
  };
}

export const sessionStore = new SessionStore();

export const currentSession = (): string => sessionStore.current();

export function useSessionState(): SessionState {
  return useSyncExternalStore(sessionStore.subscribe, sessionStore.getState, sessionStore.getState);
}
