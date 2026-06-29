# Workflow handoffs (on-demand)

Handoff table between SDLC steps -- who receives what, what is handed over, where to stop.
Matches `harness/data/skill-chains.yaml` (lens: declared-vs-actual).

| # | From -> To | Handover | Pass condition |
|---|---|---|---|
| 1 | idea -> hs:plan | problem description + constraints | standards loaded |
| 2 | hs:plan -> red-team | plan.md + phases | plan fully written |
| 3 | red-team -> validate | disposition table Accept/Reject | findings with evidence processed |
| 4 | validate -> HUMAN reviewer | Validation Log, Failed: 0 | all blocking questions finalized |
| 5 | HUMAN reviewer -> hs:cook | plan approved + DECs recorded | explicit approval (all autonomy stops here) |
| 5a | HUMAN reviewer -> hs-flow:afk | plan approved + DECs recorded | unattended (AFK) variant of #5: replaces manual cook with an unattended loop; still requires explicit approval at the front, human re-reviews at the tail (#5b) |
| 5b | hs-flow:afk -> hs:test | code + unattended commit loop | relevant suite green; human verifies before ship (counterpart of #6 for the unattended branch) |
| 6 | hs:cook -> hs:test | code + TDD tests per-phase | relevant suite green |
| 7 | hs:test -> hs:cook | QA report, ALL failures listed | any failure -> fix loop (chain 3) |
| 8 | hs:test -> artifact | verification.json verdict | 100% pass (PASS) |
| 9 | review -> artifact | review-decision.json | verdict PASS required for hard stage |
| 10 | artifact -> ship | gate_stage reads artifacts | gate pass; ship is the second HUMAN checkpoint |

Enterprise delta: handoff 9 adds reviewer role-check; handoff 10 connects to
GitLab MR (ticket_id seam already exists in the schema).

**Handoff #5 -- context isolation:** between "HUMAN reviewer"
and "hs:cook", RECOMMENDED to `/clear` so cook runs from a clean context
(planning carryover -- research/red-team/debate -- skews cook). hs:plan returns
an **ABSOLUTE PATH** so the post-`/clear` session can still locate the plan.
Nudge `cook_isolation_nudge` (advisory, fail-open) fires when hs:plan + hs:cook
are detected in the same session (best-effort). This is a recommendation, NOT a
gate -- it does not block cook.

## Orchestrator pre/parallel handoffs

Orchestrator discover/understand/triage connect into chain 1-10 above, numbers
unchanged:

| From -> To | Handover | Pass condition |
|---|---|---|
| hs-research:discover -> hs:plan | discovery brief (problem + evidence + chosen direction + open questions + out-of-scope) | brief finalized; RECOMMENDED /clear between discovery<->plan -- nudge `discover_isolation_nudge` (advisory, default OFF) |
| hs:understand -> hs:plan/hs:triage | codebase map (read-only) | map sufficient for design/localization; do NOT modify code |
| hs:triage -> hs:fix | triaged defect + repro (localized) | severity not architectural -> fast-path |
| hs:triage -> hs:plan | defect affects architecture / 3+ failing hypotheses | escalate to full pipeline instead of fast-fix |
| hs-flow:afk | unattended branch of the plan->test pipeline: inserted between #5 and #6 (rows #5a/#5b in table above) | plan approved; loop commits freely in the middle, human reviews at both ends (#5a entry, #5b exit) |
| hs-research:discover/research/triage/cook/predict -> hs-think:bakeoff | ≥2 measurable candidate directions + a mechanical metric, reasoning can't separate them | preconditions hold (else fall back to hs-think:predict) — escalation, not a default step |
| hs-think:bakeoff -> hs:plan/hs:cook | verdict (winner + full scoreboard) OR tie_within_noise→human | verdict written; winner is outside the noise band (tie/insufficient -> hand to human, do NOT proceed) |
| hs:plan/hs-research:discover -> hs-think:critique | artifact under critique (plan / chosen direction) + scope | lenses fan out (batched ≤2), consolidated to one verdict; gate mode also writes `critique-consensus.json` (advisory by default — enforcement OFF until a stage opts the kind into `stage-policy.yaml` `requires:`, a write-guarded human edit) |

`hs:triage` reuses fix-loop #6/#7 and the same gate `verification.json` #8 -- does not create a new gate.
`hs-flow:afk` does NOT create a new gate: routes Ralph sandbox | fallback native, still stops at both human-reviewer endpoints (#5a/#5b) and verifies via `verification.json` #8.
Matches `harness/data/skill-chains.yaml` (4 chains added accordingly). Archetype contract: `harness/rules/orchestrator-skills.md`.
