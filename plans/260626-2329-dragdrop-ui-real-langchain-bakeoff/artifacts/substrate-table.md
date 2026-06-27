---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Substrate table — fills the DEC-11 gap for L (LangGraph) + Bu (Burr)

Pre-step research for the Phase-4 bakeoff. DEC-11's table (`docs/decisions.md:139-142`,
affects = "new-greenfield-repo…") never scored a langchain-family substrate. Four cells per
challenger; the load-bearing one is **mid-run mutation** — can you add an agent for a role to a
graph/FSM that is *already running*, and resume, without rebuilding/recompiling?

| substrate | local? | license | headless? | mid-run mutation (inject an unknown agent into a running graph) |
|---|---|---|---|---|
| **Z** zerodep (Orchestrator) | yes (in-proc) | repo | yes | **YES** — `join_agent()` adds to the live `Roster`, `_wake_waiting()` re-routes the parked task, `run_until_idle()` resumes. No rebuild. (orchestrator.py:98-103) |
| **L** LangGraph (`StateGraph`) | yes (in-proc) | MIT | yes | **NO (hypothesis)** — a `StateGraph` compiles to a fixed Pregel graph; nodes/edges are immutable post-`compile()`. Conditional edges route only among *pre-declared* nodes; a brand-new agent node unknown at build time needs rebuild+recompile → not a clean mid-run inject. |
| **Bu** Burr (`Application`, cyclic FSM + SQLite) | yes (in-proc) | BSD-3 | yes | **NO / partial (hypothesis)** — actions + transitions are declared up front in `ApplicationBuilder`; persistence enables pause/resume and you can route to a *pre-declared* "specialist" action, but a truly unknown agent injected at runtime still needs a rebuilt `Application`. |

## What this predicts for the bakeoff

The metric is `score = observability_fraction if inject_clean else 0.0` (higher=better), where
`inject_clean` = injected mid-run **and** resumed to child-done **without** recompile/restart.

- Z: `inject_clean=1`; observability probes all pass via the event log → **score ≈ 1.0**.
- L, Bu: if the hypothesis holds, `inject_clean=0` (injection forces a recompile/rebuild) → **score = 0.0**,
  regardless of how many observability probes they pass. That is *data*, not a rigged loss — the bakeoff
  runs them on the **same neutral rubric** and records the failure by number.

So the *expected* verdict (when `.[bakeoff]` is installed) is **Z holds** on the mid-run-inject axis.
But the bakeoff still runs the challengers to record that with scalars, not by assertion — burden of
proof on the challenger (DEC-A4).

## Why no numbers here yet

`langgraph` / `burr` are NOT installed (default zero-dep posture). They are **deliberately not
installed in this run** — the interpreter is shared with several concurrent sessions and a global
`pip install` would pollute it. To produce a real ≥2-candidate verdict:

```bash
python -m venv .venv-bakeoff && . .venv-bakeoff/bin/activate
pip install -e 'drag_from_zero[bakeoff]'
python -m dragzero.bakeoff.run_bakeoff --plan-dir <plan>/artifacts
```

Until then `run_bakeoff` **REFUSES** ("insufficient candidates") rather than crowning Z unopposed,
and no substrate DEC is registered (DEC gate = `candidates ≥ 2`).

## Open

- `[ ]` The mid-run-mutation cells for L/Bu are reasoned from each framework's compile model, not yet
  measured. The bakeoff adapter is the measurement; run it under `.[bakeoff]` to confirm/refute.
