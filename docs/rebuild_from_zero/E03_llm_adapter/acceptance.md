# E03 — Acceptance Criteria (draft)

## S03.1 JSON-mode
- Given `response_format=json_object`, When the model answers an action step, Then output parses as JSON on the first attempt in ≥ target % of calls (baseline to beat: 67% from real run).

## S03.2 lazy init
- Given a fresh process, When the adapter module is imported (no call yet), Then no HTTP client is constructed (verified by patching/inspection).

## S03.3 error handling
- Given the LLM endpoint is unreachable, When `call_llm` runs, Then it returns/raises a structured error with reason, not a raw stack trace into the loop.

## S03.4 config override
- Given env `LLM_MODEL=X`, When `call_llm` runs without explicit model, Then model X is used; And an explicit `model=` arg overrides env.

## S03.5 grammar (optional)
- Given a backend supporting grammar, When a grammar is supplied, Then responses conform to the action schema.
