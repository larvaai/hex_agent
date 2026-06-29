# Verify before done — end-of-phase verification

This drawer describes the final verification step of a phase before cook advances
to the next phase or writes an artifact. Backing: `harness/rules/verification-mechanism.md`,
`harness/hooks/gate_stage.py`, `harness/scripts/artifact_check.py`.

## 5 invariants (from verification-mechanism.md)

1. **Anchored**: every claim must be accompanied by a commit SHA, `file:line`, or real command output.
2. **Downstream rejects UNVERIFIABLE**: the next step does not build on unanchored claims.
3. **Artifact is the source**: verdict is written to machine-written JSON, not stated verbally.
4. **Self-report does not self-approve**: gate reads artifact + verdict policy.
5. **Trace records steps**: significant steps emit via `harness/hooks/trace_log.py`.

## End-of-phase checklist

Before writing `verification.json` and advancing the phase:

- [ ] Full suite green (`python3 -m pytest harness/tests/ -q`)
- [ ] No new lint/type/build errors
- [ ] Every acceptance criterion in the phase file has evidence (file:line or command output)
- [ ] No regression in shared touchpoints: walk each caller of a changed function and any module sharing a file/contract with the change
- [ ] Public contract (signature, schema, env var) unchanged — or reason for change clearly documented
- [ ] `verification.json` written per schema `harness/schemas/artifact-verification.json`

## Side-effect check

When a regression or contract break is detected: STOP, ask AskUserQuestion with:
- What is affected (file, test, workflow)
- One-line cause
- 2-4 specific action choices

Do not silently self-patch regressions. Do not advance a phase while any UNVERIFIABLE claim exists.

## Gate wiring

`harness/hooks/gate_stage.py` (PreToolUse Bash, fail-closed, exit 2) reads
`verification.json` from the filesystem before the next stage.
`harness/scripts/artifact_check.py` is a helper for schema validation.
Missing artifact → gate blocks + prints the file creation path.
