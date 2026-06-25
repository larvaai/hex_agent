# E09 — Acceptance Criteria (draft)

## S09.1 build from config
- Given `roles/code.yaml`, When loaded, Then an Agent with that allowlist/lenses/permissions is produced.

## S09.2 allowlist enforcement
- Given role `code` without `git.git_commit`, When it emits a call to `git.git_commit`, Then output is replaced by a blocker/handoff JSON (tool not executed).

## S09.3 config validation
- Given a role yaml missing `system_prompt`, When loaded, Then a clear ValueError naming the file/field is raised.

## S09.4 separation of duties
- Given role `code` (`owns_validation=false, must_handoff_to=test`), When it tries to finalize as validated, Then it is forced to route to `test`.

## S09.5 scoped prompt
- Given role `business_analyst` (0 tools), When its prompt is built, Then it contains no tool catalog beyond its (empty) allowlist and only its lens group.

## S09.6 single source
- Given both run paths, When they build role `code`, Then they use the same `roles/code.yaml` (no divergent definitions).
