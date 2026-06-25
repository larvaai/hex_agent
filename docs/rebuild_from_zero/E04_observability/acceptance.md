# E04 — Acceptance Criteria (draft)

## S04.1 event stream
- Given a completed run, When I read `events.jsonl`, Then events are ordered by sequence and include a `run_started` and `run_finished` StateEvent.

## S04.2 summary
- Given a finished run, When I read `summary.json`, Then it contains `metrics` (steps, llm_calls, parse_errors, tool_calls, finish_gate_blocks, ...) and `status`.

## S04.3 inspect list/summary
- Given ≥1 run, When `inspect list`, Then runs are listed newest-first; And `inspect summary latest` prints the latest summary.

## S04.4 event filtering
- Given a run, When `inspect events latest --kind ObservationEvent --tool git.git_status`, Then only matching events are shown; And `--json` emits valid JSON.

## S04.5 toggle
- Given `AGENT_EVENT_LOG=0`, When a run executes, Then it completes and no event files are written.
