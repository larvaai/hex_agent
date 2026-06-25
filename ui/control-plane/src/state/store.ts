/**
 * UI store — snapshot + event log, written ONLY by the adapter's onEvent. Epic E21 (Phase 5).
 *
 * The architectural invariant "UI never mutates state directly" lives here: components read this
 * store and dispatch RuntimeCommands, but they never write agent/checkpoint state. Only
 * ``setSnapshot`` (from getSnapshot) and ``applyEvent`` (from the stream) mutate it. Events are
 * deduped by ``seq`` (the server already deduped event_id; seq is the unique stream id), so a
 * duplicate delivery cannot double-render the graph or timeline (S21.18/S21.50).
 */
import { useSyncExternalStore } from "react";

import type { TaskLoopSnapshot } from "../contracts/generated";
import type { StreamEvent } from "../adapter/controlPlane";

export interface TimelineEntry {
  seq: number;
  type: string;
  uiPayload: Record<string, unknown>;
}

export type ConnectionStatus = "connecting" | "open" | "reconnecting" | "closed";

export interface CPState {
  snapshot: TaskLoopSnapshot | null;
  events: TimelineEntry[];
  selectedAgentId: string | null;
  status: ConnectionStatus;
}

type Listener = () => void;

class ControlPlaneStore {
  private state: CPState = { snapshot: null, events: [], selectedAgentId: null, status: "connecting" };
  private seen = new Set<number>();
  private listeners = new Set<Listener>();

  getState = (): CPState => this.state;

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  private commit(next: CPState) {
    this.state = next; // new reference so useSyncExternalStore re-renders
    this.listeners.forEach((l) => l());
  }

  setSnapshot = (snapshot: TaskLoopSnapshot): void => {
    this.commit({ ...this.state, snapshot });
  };

  applyEvent = (event: StreamEvent): void => {
    if (this.seen.has(event.seq)) return; // dedup by seq — duplicate delivery is a no-op
    this.seen.add(event.seq);
    const events = [...this.state.events, { seq: event.seq, type: event.type, uiPayload: event.uiPayload }].sort(
      (a, b) => a.seq - b.seq,
    );
    this.commit({ ...this.state, events });
  };

  selectAgent = (agentId: string | null): void => {
    this.commit({ ...this.state, selectedAgentId: agentId });
  };

  setStatus = (status: ConnectionStatus): void => {
    this.commit({ ...this.state, status });
  };

  // test-only: reset between cases
  _reset = (): void => {
    this.seen = new Set();
    this.commit({ snapshot: null, events: [], selectedAgentId: null, status: "connecting" });
  };
}

export const store = new ControlPlaneStore();

export function useCPState(): CPState {
  return useSyncExternalStore(store.subscribe, store.getState, store.getState);
}
