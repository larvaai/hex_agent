# E13 — Acceptance Criteria (draft)

## S13.1 artifact chain
- Given a product prompt, When the factory runs, Then artifacts `00_vision…10_implementation_spec` exist under `var/factory_runs/<id>/`.

## S13.2 per-stage files
- Given any stage, When it completes, Then its declared artifact file is written and recorded in the stage results.

## S13.3 validation stage
- Given a weak/incomplete product spec, When the validator runs, Then it flags gaps and the pipeline does not proceed to code handoff.

## S13.4 handoff
- Given a completed spec, When handoff is built, Then a `code_handoff_packet` + `implementation_spec.md` path are produced for E10.

## S13.5 routing in
- Given intent `product-build`, When the supervisor dispatches, Then the factory is invoked.
