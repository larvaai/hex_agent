# hs-think:critique — consolidation contract (on-demand)

Load this when consolidating lens findings into one verdict. The `critique-consolidator` agent owns
the logic; this is the controller's contract for what to pass in and what comes back.

## Pass in

- The JSON finding arrays from every lens that ran (see `critique-protocol.md` for the shape).
- Prior critique reports under `plans/reports/` (for repeat-offense detection).
- The scope label and the artifact type.
- The names of any lenses that failed or returned `[]` — so the consolidator marks them missing
  instead of pretending they passed.

## What the consolidator does

1. **Cross-lens dedup** — same anchor or same root cause merges into one finding naming every lens
   that raised it. Agreement across lenses is signal, surfaced, not hidden.
2. **Anti-overlap floor** — drop any finding lacking a non-empty `why_it_matters` AND `fix`.
3. **Severity** — `blocker > major > minor`, by blast radius × reachability. A `proven` finding
   outranks a `suspected` one at equal nominal severity.
4. **Top findings** — the three most threatening across all lenses, each with severity, lens, anchor,
   consequence, fix.
5. **Repeat-offense (attached last)** — findings seen in prior reports get an occurrence count (×N)
   and prior references. This is metadata: deleting the findings list must not change the repeat set.
6. **DEC-worthy flag** — items implying an architectural decision are flagged for the controller to
   raise with the user (the consolidator does not record DECs itself).

## What comes back

One consolidated markdown body (neutral tone) plus a proposed verdict:

- **BLOCKED** — at least one `proven` blocker survived.
- **PASS_WITH_RISK** — no surviving blocker, but majors remain, accepted with a named condition.
- **PASS** — no blocker and no unaccepted major survived.

Structure: header (`scope · lenses: … [missing: X]`), severity tally (`blocker N · major N · minor N`),
top findings, per-lens sections, repeat-offense section (if any), DEC-worthy section (if any), verdict
+ one-paragraph rationale.

## Controller responsibilities (NOT the consolidator's)

- Write the report to `plans/reports/<slug>-critique-report.md`.
- In gate mode, write the verdict to `plans/<active-plan>/artifacts/critique-consensus.json`
  (schema `harness/schemas/artifact-critique-consensus.json`): `verdict`, `reviewer` (resolve_actor),
  `role: critique`, `rationale`, `ts`, optional `lenses` and `top_findings`. Enforcement ships OFF: the
  shipped policy lists `critique-consensus` at no stage; an org opts in by adding it to a stage's
  `requires:` in `stage-policy.yaml`, after which the verdict must be `PASS`.
- Raise each DEC-worthy item with the user and, on confirmation, record it via `decision_register.py`.
