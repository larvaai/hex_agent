# root-cause-method — method for identifying root cause

Load when: any bug/issue that needs investigation and fixing.

## Iron rule

```
DO NOT FIX BEFORE PHASE 1 IS COMPLETE
```

Phase 1 not done → no fix may be proposed, even "just to try".

## 4 phases in detail

### Phase 1: Collect evidence (BEFORE any fix)

1. Read the full error message and stack trace — skip no warning lines.
2. Reproduce the failure consistently — record the exact steps. Cannot reproduce:
   collect more data, add instrumentation, do not guess.
3. Check recent changes:
   ```bash
   git log --oneline -20
   git diff HEAD~5 -- '*.yaml' '*.json' '*.env*' '*.config*'
   ```
4. In multi-component systems: log data in/out at each component boundary.
   Run once to identify which component is faulty — then analyze it in depth.
5. Trace data flow backward: where does the bad value originate? See `hypothesis-loop.md`
   section "Tracing back up the call stack".

### Phase 2: Analyze patterns

1. Find similar working code in the same repo.
2. Read the reference implementation in full — understand it completely before comparing.
3. List every difference, however small — "this can't be the cause" is often a signal
   pointing to the most important difference.
4. Identify dependencies: which component, config, or env is required but missing?

### Phase 3: Hypotheses and testing

See `hypothesis-loop.md` for the full procedure.

Quick principles:
- State a specific hypothesis: "X is the cause BECAUSE Y" — no vagueness.
- Test with the smallest possible change: one variable at a time.
- Confirmed → Phase 4. Failed → state a new hypothesis (do not stack fixes).
- After 3 failed hypotheses: STOP, reconsider the architecture.

### Phase 4: Finalize root cause + failing repro test

1. **Write a failing test** that reproduces the failure (rule `harness/rules/tdd-discipline.md`):
   - Test fails intentionally — proves the root cause exists.
   - As simple as possible and automatable.
   - This is the primary output of hs:debug — input for hs:fix.
2. Fix exactly one point: the root cause, not the symptom.
   The actual fix is handed to `hs:fix`.
3. If the fix does not work: STOP. Count the attempts.
   - < 3: return to Phase 1 with the new information.
   - ≥ 3: architectural problem — ask the user, consider `hs-think:brainstorm`.

## Report format

File: `plans/reports/<slug>-debug-report.md`

```markdown
# [Issue name] — Debug Report

## Executive Summary
- **Issue:** (one line)
- **Impact:** (affected user/component, severity)
- **Root cause:** (one line — confirmed, not "likely")
- **Status:** Identified / Needs further investigation
- **Next step:** hs:fix with failing test at <path>

## Timeline
- HH:MM — event

## Technical analysis
### Evidence
(log excerpt, stack trace, query result — trimmed to necessary lines only)

### Eliminated hypotheses
1. H1: ... — eliminated because ...
2. H2: ... — eliminated because ...

### Root cause (confirmed)
(full event chain from trigger to symptom)

## Failing repro test
`<path-to-test>` — run to confirm: `python3 -m pytest <path> -q`

## Open questions
-
```

## Distinguishing "confirmed" vs "likely"

- **Confirmed**: direct evidence (log, trace, reproduction).
- **Likely**: indirect evidence, not yet reproduced.
  → Record clearly in the report; do not fabricate evidence.
