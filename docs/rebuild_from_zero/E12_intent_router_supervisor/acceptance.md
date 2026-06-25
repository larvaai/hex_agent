# E12 — Acceptance Criteria (draft)

## S12.1 routing
- Given a coding request, When classified, Then `target=coding`; Given a "latest paper" request, Then `target=research`.

## S12.2 decision shape
- Given any request, When classified, Then a `RouteDecision` with intent/confidence/needs-flags/steps is returned.

## S12.3 LLM fallback
- Given a request with classifier confidence < threshold, When routing, Then an LLM classifier is consulted and its result used.

## S12.4 safety gate
- Given a request needing repo/code/web, When dispatched, Then SafetyDepartment runs first; And a `blocked` status halts dispatch.

## S12.5 mixed plan
- Given a request combining research + code, When routed, Then a multi-step plan (research → ... → final) is produced and executed in order.

## S12.6 synthesis
- Given department outputs, When finalized, Then the answer merges them with citations and validation evidence.
