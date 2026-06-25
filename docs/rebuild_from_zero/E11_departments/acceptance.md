# E11 — Acceptance Criteria (draft)

## S11.1 research output
- Given a research question, When the department runs, Then output has `summary` and `sources[]` with URLs/titles.

## S11.2 research chain
- Given a topic needing web evidence, When run, Then search → source read → extract → citation steps each appear in the trace.

## S11.3 safety review
- Given a request implying a dangerous action, When Safety runs, Then it returns `status=blocked` with notes.

## S11.4 blocking
- Given Safety `status=blocked`, When the supervisor proceeds, Then execution halts and the final answer reports the block.

## S11.5 scoped members
- Given a member agent, When it calls a tool, Then the call respects its role allowlist and workspace sandbox.
