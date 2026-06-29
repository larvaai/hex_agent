# hs-think:critique — lens fan-out protocol (on-demand)

Load this when running a critique. It covers lens selection, batched fan-out, and the finding
contract the consolidator expects.

## 1. Classify the artifact, pick the lens set

Read the artifact and classify it: `plan` / `decision` / `design` / `code` / `diff`. Look up the lens
set in `harness/data/critique.yaml` under `lenses:` (unknown type -> `default`). `--lenses a,b,c`
overrides the config for one run.

Recommended sets (defaults shipped in `critique.yaml`):

| Artifact type | Lenses | Why these |
|---|---|---|
| plan / decision / design | `red-teamer`, `independent-revalidator`, `brainstormer` | failure-mode + irreversibility; sealed-room re-derivation of the load-bearing claim; assumption / alternative challenge |
| code / diff | `red-teamer`, `code-reviewer`, `independent-revalidator` | attack surface; production-readiness (concurrency, trust boundary, N+1); independent re-derivation of a claimed result |

Each lens is an existing read-only agent that already carries the Evidence Filter
(`harness/rules/verification-mechanism.md`): findings anchor to `file:line` / a reproduction / a
triggering input, and separate `proven` from `suspected` (`[UNVERIFIED]`).

## 2. Fan out in batches of ≤2

The harness caps subagents at 2 per turn. Do NOT spawn the whole lens set at once. Collect one batch,
let it return, start the next. Lenses run blind to each other — independence is the point; a lens that
read another's findings would anchor instead of re-deriving.

Give each lens: the artifact (path or content), the scope label, and the finding contract below. Do
NOT pass the other lenses' output, your own running synthesis, or the eventual verdict.

## 3. The finding contract

Ask each lens to END its report with a normalized JSON array so the consolidator does not parse prose:

```json
[
  { "lens": "<agent-name>",
    "anchor": "<file:line | reproduction command | triggering input>",
    "finding": "<neutral one-line statement of the problem>",
    "why_it_matters": "<the consequence if unaddressed>",
    "fix": "<the cheapest fix, or the condition under which it is acceptable>",
    "severity": "blocker | major | minor",
    "status": "proven | suspected" }
]
```

Rules:
- `finding` is a neutral, grounded observation — no sarcasm, no escalation, no remark about the author.
- `anchor` is real evidence from the artifact, never invented. No anchor -> it is not a blocker.
- `why_it_matters` and `fix` are both non-empty, or the consolidator drops the finding (anti-overlap floor).
- A lens with nothing reproducible returns `[]` plus a short "residual risks" note — an honest empty
  beats a padded list.

## 4. Hand off to the consolidator

Collect every lens's JSON array (tolerate a lens that failed or returned `[]` — name it as missing,
do not fabricate its findings). Pass the arrays + any prior critique reports under `plans/reports/`
(for repeat-offense detection) + the scope label to the `critique-consolidator` agent. See
`consolidation-contract.md`.
