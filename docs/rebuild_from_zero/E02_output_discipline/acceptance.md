# E02 — Acceptance Criteria (draft)

## S02.1 parse + repair
- Given a near-valid JSON (trailing comma / unbalanced brace), When parsed, Then repair succeeds and a valid action dict is returned.
- Given irreparable output, When parsed, Then a `JsonGateError` with stage/cause is raised.

## S02.2 parse-error budget
- Given `max_parse_errors=3`, When the model emits invalid JSON 3 times, Then the run stops with a classified parse error; And step budget is not decremented by retries.

## S02.3 condense
- Given a tool result > N chars, When condensed, Then re-fed context ≤ cap and key fields preserved.

## S02.4 finish gate
- Given a run that edited code and has no passing validation, When the model returns `final`, Then it is blocked and the model is asked to validate or declare a blocker.

## S02.5 loop budget
- Given the same `tool+args` called `max_same_tool_calls` times, When called again, Then the runtime blocks further repeats and routes to finish.

## S02.6 shared module
- Given orchestrator and multi-agent graph, When both run, Then both import the same `discipline` functions (verified by import graph / no duplicated definitions).
