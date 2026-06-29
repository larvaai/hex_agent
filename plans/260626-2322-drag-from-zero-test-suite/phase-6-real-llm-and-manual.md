---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 6 — env-gated real-LLM E2E + manual runbook

**Goal:** (a) automated tests that hit a real local model but stay out of CI's way, and (b)
the human runbook the user explicitly asked for. This is where real token burn lives.

## Part A — env-gated real-LLM tests (marker=real_llm)

Skip rule (in `tests/conftest.py`, phase 1): every `real_llm` item skips unless
`OPENAI_BASE_URL` is set. Assert **shape, never content** — a local 35B is non-deterministic.

- `tests/real_llm/test_local_llm_smoke.py` (`@pytest.mark.real_llm`):
  - build `OpenAICompatLLM(base_url=$OPENAI_BASE_URL, model=$MODEL)`; one
    `runtime.run("Fix parse_config and add a test")` through the real orchestrator+tools+sandbox,
    `Budget(max_llm_calls=8)` so a wandering model can't burn forever.
  - assert: run terminates; root status ∈ {done, blocked, halted} (no hang, no crash);
    every DELEGATION_DECIDED has `mode ∈ {solo, delegate}`; if `delegate`, `target` non-empty.
  - **fallback handling (red-team #5):** count `_meta.fallback` / `reasoning^="fallback:"` and
    EXPOSE it as test output; gate only on "≥1 valid decision produced", not on zero fallback —
    a separate `xfail`-able assertion checks `no_fallback` for a model that's behaving.
  - `adapters/llm_local.OpenAICompatLLM` transport is real here (the unit layer already covers
    the injectable-transport parse path deterministically).
- `tests/real_llm/test_eval_real_smoke.py` (`@pytest.mark.real_llm`) — `run_eval --real
  --trials 2` path: `run_suite` with an `OpenAICompatLLM` factory produces a report whose rows
  carry numeric pass_rate/variance; assert structure + that variance is computed (not that any
  particular score is hit).

## Part B — `drag_from_zero/MANUAL_TESTING.md` (the runbook)

Co-located with the subproject it tests (like its README) — explicitly-requested deliverable.
Structure: **prerequisites**, then numbered steps, each with `command` · `expected` ·
`PASS if…`. Cover:

1. **Prereqs** — LM Studio (or llama.cpp) serving an OpenAI-compatible endpoint at
   `http://localhost:1234/v1`; a loaded model; `OPENAI_BASE_URL`/`MODEL` env; for browser:
   `pip install -e ".[test-browser]"` + `playwright install chromium`. State the assumption (U3).
2. **Deterministic smoke (no weights)** — `python demo.py` → expect event log + tree with a
   delegated child; `python run_eval.py` → scored report. PASS if both print without error.
3. **Real local run (tools, real edits)** — `python run_local.py --sandbox ./work --task
   "Add a test for parse_config"` → expect the model to read/write files under `./work`;
   inspect `./work`. PASS if a file was created/edited and the run ended with a decision
   (not a crash); fallback is acceptable but noted.
4. **Real eval (token burn)** — `python run_eval.py --real --trials 5` → read pass-rate /
   variance per scorer. PASS if the report renders N trials; interpret over/under-delegation.
5. **Server + browser (real model)** — `python run_server.py --real`, open
   `http://127.0.0.1:8000` → click Run → tree decomposes live (t1→t2→…), chat narrates
   translated verdicts ("reduced — children done", "run finished · done · N steps"), file
   chips open artifacts the agent wrote, no console errors. PASS = all four observed
   (mirrors README §6a's "verified end-to-end in a real browser").
6. **Failure-mode probes (resilience is a feature here):**
   - LM Studio **down** → `run_local.py` → expect graceful `solo_fallback` (observable via
     `_meta`), no stack trace. PASS if it degrades, not crashes.
   - **bad path** → ask the model (or a recorded reply) to write outside the sandbox →
     expect a failed `tool_result` with `SandboxError`, run continues. PASS if no escape.
   - **budget halt** → set a tiny `max_llm_calls` in a topology → expect BUDGET_EXCEEDED and
     a HALTED tree. PASS if the run stops at the limit.
   - **missing role** → delegate to a role nobody fills → expect TASK_WAITING (parked), then
     `join_agent` resumes. PASS if it parks rather than mis-routes.

## TDD framing

- **Red proof:** unset `OPENAI_BASE_URL` → `pytest -m real_llm` reports *skipped*, not
  failed/collected-error (proves the gate). With it set + LM up, the smoke runs.
- The runbook itself: dry-run each numbered step once against a live model; fix any step whose
  "expected" doesn't match reality before declaring the phase done.

## Acceptance

- [ ] `pytest -m real_llm` skips cleanly with no env; runs and asserts shape with env + model up.
- [ ] fallback count surfaced, not silently gating (red-team #5 honored).
- [ ] `MANUAL_TESTING.md` present; every step has command + expected + explicit PASS criterion;
      includes the 4 failure-mode probes.
- [ ] default `pytest -q` unaffected (real_llm excluded).
- [ ] whole-plan acceptance (plan.md) re-checked: default suite deterministic & green; matrix full.
