# E05 — Acceptance Criteria (draft)

## S05.1 end-to-end loop
- Given a read-only task (e.g. "what changed since last commit"), When `run_single` runs against a live LLM, Then it calls the needed read tools and returns a correct final answer with a clean event log.

## S05.2 agent node
- Given the agent node, When invoked, Then it calls the LLM adapter with JSON-mode and parses via the discipline gate.

## S05.3 routing
- Given `action=tool`, When routing, Then control goes to the tool node; And `action=final` ends the graph.

## S05.4 condense
- Given a large tool result, When the next agent step runs, Then the observation in context is condensed.

## S05.5 reuse
- Given the multi-agent graph, When implemented, Then it imports the same node/loop/discipline (no duplicate loop) — verified by code structure.
