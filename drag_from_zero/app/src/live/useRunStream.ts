import { useCallback, useRef, useState } from "react";
import { createRun, openEvents, postTopology, startRun, joinAgent, TopologyValidationError, type Frame } from "../api/client";
import type { TopologyJSON } from "../topology/serialize";
import type { GraphNode } from "./status";

export interface RunGraph {
  root: string | null;
  nodes: GraphNode[];
  edges: { source: string; target: string; kind: string }[];
}

export interface RunState {
  runId: string | null;
  status: string; // created|running|awaiting|done|blocked|cancelled
  graph: RunGraph | null;
  errors: string[]; // 422 validation errors surfaced from the server
  awaitingRoles: string[]; // roles the run is parked on (P3)
}

const EMPTY: RunState = { runId: null, status: "idle", graph: null, errors: [], awaitingRoles: [] };

export function useRunStream() {
  const [state, setState] = useState<RunState>(EMPTY);
  const wsRef = useRef<WebSocket | null>(null);

  const apply = useCallback((f: Frame) => {
    setState((s) => {
      if (f.type === "snapshot" && "graph" in f) return { ...s, graph: f.graph as RunGraph };
      if (f.type === "run_finished") return { ...s, status: s.status === "awaiting" ? s.status : s.status };
      if (f.type === "run_cancelled") return { ...s, status: "cancelled" };
      if (f.type === "event" && "data" in f) {
        const d = (f as { data: { type: string; payload: Record<string, unknown> } }).data;
        if (d.type === "await_role") {
          const role = String(d.payload?.role ?? "");
          return { ...s, status: "awaiting", awaitingRoles: role ? Array.from(new Set([...s.awaitingRoles, role])) : s.awaitingRoles };
        }
        if (d.type === "agent_joined") return { ...s, status: "running", awaitingRoles: [] };
        if (d.type === "run_end") {
          const st = String((d.payload as Record<string, unknown>)?.status ?? "done");
          return { ...s, status: st };
        }
      }
      return s;
    });
  }, []);

  const run = useCallback(
    async (topo: TopologyJSON, task: string) => {
      wsRef.current?.close();
      setState({ ...EMPTY, status: "starting" });
      try {
        const { id: topologyId } = await postTopology(topo);
        const { id: runId } = await createRun({ topology_id: topologyId, task });
        setState((s) => ({ ...s, runId, status: "running" }));
        wsRef.current = openEvents(runId, apply); // subscribe before start so no frame is missed
        await startRun(runId);
      } catch (err) {
        if (err instanceof TopologyValidationError) setState((s) => ({ ...s, status: "invalid", errors: err.errors }));
        else setState((s) => ({ ...s, status: "error", errors: [String(err)] }));
      }
    },
    [apply],
  );

  const inject = useCallback(
    async (role: string) => {
      if (!state.runId) return;
      await joinAgent(state.runId, role);
    },
    [state.runId],
  );

  return { state, run, inject };
}
