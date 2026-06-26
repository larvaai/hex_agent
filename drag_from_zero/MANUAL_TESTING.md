# Manual testing — drag_from_zero

The automated suite (`python -m pytest -q`) is **deterministic** — it never touches real weights
or a browser. This runbook covers what only a human + real environment can verify: a local model
through the orchestrator, the verifier gate over real files, and the Agent-IDE UI in a browser.

Every step has a **command**, an **expected** result, and an explicit **PASS if…**. Run from the
`drag_from_zero/` directory.

## Prerequisites

- Python ≥ 3.11. Editable install: `pip install -e .`
- **Real model (steps 3–6):** LM Studio (or a llama.cpp server) exposing an OpenAI-compatible
  endpoint. Default assumed: `http://localhost:1234/v1`. Load a model, then:
  ```bash
  export OPENAI_BASE_URL=http://localhost:1234/v1   # or your endpoint
  export MODEL=<your-model-id>                       # e.g. qwen2.5-coder
  export OPENAI_API_KEY=lm-studio                    # any non-empty string for LM Studio
  ```
- **Browser (step 5):** `pip install -e ".[test-browser]" && python -m playwright install chromium`

---

## 1. Deterministic smoke (no weights) — sanity that the harness runs

```bash
python demo.py
python -m pytest -q
```
**Expected:** `demo.py` prints an event log then an execution tree with a delegated child
(`● … [done]`). pytest prints `N passed`.
**PASS if:** both finish with exit 0, no traceback, and the pytest line says `passed` with `0 failed`.

---

## 2. Deterministic eval report — the scoring gauges work

```bash
python run_eval.py
```
**Expected:** a table per scenario (`fix-bug`, `trivial-answer`) with columns `pass% mean min max var`.
**PASS if:** `fix-bug` shows `delegates_to:coder` at 100% and `trivial-answer` shows `solves_solo`
at 100% — the gauges discriminate good behaviour.

---

## 3. Real local run with tools — the model does real edits

```bash
mkdir -p work
python run_local.py --sandbox ./work --task "Add a test for parse_config"
```
**Expected:** the event log shows `tool_called` / `tool_result` (read_file / write_file), the tree
ends with a decision, and files appear/change under `./work`. Output is non-deterministic.
**PASS if:** the run ends with a terminal decision (not a traceback) **and** at least one file under
`./work` was created or modified. A `fallback: …` decision is acceptable but note it (see step 6d).

> The harness (events, tree, gates) is byte-identical to the deterministic tests — only the adapter
> behind the LLM port changed. If the model is weak, the run still *completes*; it just scores worse.

---

## 4. Real eval (token burn) — pass-rate / variance over trials

```bash
python run_eval.py --real --trials 5
```
**Expected:** the same table, now scored over 5 real trials; numbers vary by model quality.
**PASS if:** the report renders all scenarios with `N=5` aggregated (pass% + variance computed).
Interpret: a model that over-delegates a trivial question fails `solves_solo`; one that never
delegates the coding task fails `delegates_to:coder`. That signal is the point — not a fixed score.

---

## 5. Agent-IDE UI in a browser (real model) — the verifier gate, visible

```bash
python run_server.py --real
# then open http://127.0.0.1:8000   (omit --real for the FakeLLM demo)
```
Click **Run** (the play button). Watch the graph + chat.
**Expected (mirrors README §6a):**
- the UI boots from `/api/session` and draws the root node;
- the tree decomposes live (`t1 → t2 → …`) as the planner delegates;
- chat narrates translated verdicts: `routing the goal …`, `too big → decomposed into …`,
  `✓ reduced — children done` / `✓ passed`, `run finished · <status> · N steps`;
- switch to the **Workspace** tab → file chips open the artifacts the agents actually wrote;
- **no uncaught console errors** (open devtools).
**PASS if:** all four bullets are observed and the run reaches a `run finished` line.

> **Anti-gaming, visible:** the server ships a `DONE_WHEN` spec (`run_server.py`) the **code**
> re-derives over the sandbox. If the real model claims a subtask done but never writes
> `tests/auth.test.ts` (or a `report.md` with `coverage` + `\d+ passed`), that node turns
> **blocked/FAIL** even though the model said "done". The model never sets its own verdict.

---

## 6. Failure-mode probes — resilience is a designed feature here

### 6a. Local model unreachable → graceful, not a crash
Stop LM Studio (or point at a dead port), then:
```bash
OPENAI_BASE_URL=http://localhost:9/v1 python run_local.py --task "x"
```
**Expected:** `[!] Could not reach an LLM at … ` on stderr + a hint to start the server.
**PASS if:** exit code is `2` and there is **no Python traceback** — the connection error is handled.

### 6b. Server survives a dead model
```bash
OPENAI_BASE_URL=http://localhost:9/v1 python run_server.py --real
```
Open the UI, click Run.
**PASS if:** the server stays up, the UI shows a `blocked` outcome (a `block` frame), and the
process does **not** die — `Run._run` swallows the exception into a block, never killing the thread.

### 6c. Budget halt stops a runaway
```bash
python run_local.py --task "deep multi-step task" --max-llm-calls 2
```
**Expected:** the event log contains `budget_exceeded` after 2 LLM calls; the tree shows a halted node.
**PASS if:** `budget_exceeded` appears and the run stops at the limit (≤ 2 `task_started`).

### 6d. Unparseable model output → safe solo fallback (observable)
With a weak/chatty model that doesn't emit clean JSON, run step 3 or 4 and read the trace.
**Expected:** a decision with `reasoning: "fallback: …"` (the adapter made one repair attempt, then
fell back to `solo` rather than crashing); `run_eval --real`'s `no_llm_fallback` scorer drops below 1.0.
**PASS if:** the run continues to a terminal state and the fallback is **visible** in the trace /
score — degraded, never crashed. (A connection failure is 6a, not a fallback — distinct paths.)

### 6e. Sandbox path-jail (real model, opportunistic)
If a real model ever emits a tool call with a `..`-escaping or absolute path, the event log shows a
`tool_result` with `ok=false` and `escapes sandbox`, and the run continues.
**PASS if:** no file is ever written outside the `--sandbox` root. (Deterministically pinned by
`tests/unit/test_tools_fs_unit.py` and `tests/integration` tool-loop tests; this is the live check.)

---

## What automated covers vs. this runbook

| Concern | Automated (default `pytest -q`) | This runbook |
|---|---|---|
| harness invariants, fold, registries, sandbox jail | ✅ unit + integration | — |
| topology→runtime→server over the wire | ✅ e2e (FakeLLM/RecordedLLM) | — |
| verifier gate (claim ≠ verdict) | ✅ e2e + slice6b | step 5 (real model) |
| real local model behaviour | ⏭️ `pytest -m real_llm` (env-gated) | steps 3,4,6 |
| real browser rendering | ⏭️ `pytest -m browser` (opt-in) | step 5 |

`pytest -m real_llm` and `pytest -m browser` automate slices of steps 3–6 when their prerequisites
are present; this runbook is the human pass that judges *quality* and *UX*, which a counter cannot.
