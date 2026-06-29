# Control-plane + IDE — test tiers (how to run each)

The E21 control-plane and the live IDE (`ui/ide`, `ui/control-plane`) are tested as a 5-layer
pyramid. **Real-only E2E:** every browser test drives the *real* `python -m ui.ide`; the fake server
(`tools/fake_control_server.py`) is the unit/contract tier only and never appears in E2E.

| Tier | What it proves | Command | Needs 35B? | In CI? |
|---|---|---|---|---|
| L0 unit (pytest) | pure fns, contract, fake-server seam | `pytest -q` | no | **yes** |
| L0 contract (vitest) | adapter / components / contract-seam | `npm --prefix ui/control-plane test` | no | **no** — no Node job (DEC-T5) |
| L1 backend-integration | real `IdeControlServer`/`files`/`runner` in-process, no model | `pytest tests/test_ide_*.py -q` | no | **yes** (part of `pytest tests`) |
| L2 browser E2E (det) | real `ui.ide` + real React, HTTP surface only, no model | `npm --prefix ui/control-plane run test:e2e` | no | **no** — local pre-merge gate |
| L3 browser E2E (live) | real `ui.ide` + real 35B, full agent run | `npm --prefix ui/control-plane run test:e2e:live` | **yes** | **no** |
| L4 manual | visual/feel, real-solve judgment, server-bounce | [manual runbook](./manual-runbook-control-plane.md) | yes | **no** |

CI today (`.github/workflows/ci.yml`) is Python-only: `ruff check .` + `pytest tests` + `pytest
tests_audit`. So only **L0-pytest and L1 actually gate merges**. L0-vitest, L2, L3, L4 are
local-only until a Node CI job is added (a separate decision — DEC-T5). Do not claim they gate.

## One-time setup for the browser tiers (L2/L3)

```bash
npm --prefix ui/control-plane install                       # @playwright/test is a devDep
npm --prefix ui/control-plane exec playwright install chromium   # ~90 MB browser binary
```

L2/L3 spawn the backend **and** Vite themselves (ephemeral ports, killed on teardown) — you do not
boot anything by hand. `test:e2e` runs `--grep-invert @live`; `test:e2e:live` runs `--grep @live`.

## Booting the stack by hand (for L4 manual, or ad-hoc)

```bash
# real IDE backend (runs the agent; serves dist/ if built)
python3 -m ui.ide --host 127.0.0.1 --port 8800 --token dev-token --session t1_demo

# the UI, hot-reload, pointed at that backend (config.ts defaults to http://localhost:8800)
npm --prefix ui/control-plane run dev        # http://localhost:5173

# offline demo with NO agent (deterministic fixture replay — NOT used by any E2E tier):
python3 tools/fake_control_server.py --port 8800 --no-reality
```

The UI is pinned to session `t1_demo` (`ui/control-plane/src/config.ts` `SESSION_ID`), so boot the
backend with `--session t1_demo`.

## The local 35B (L3 + L4)

The agent run needs an OpenAI-compatible endpoint (LM Studio per the project memory). TEXT-mode JSON —
do **not** send `response_format=json_object` (LM Studio rejects it). Defaults
(`llm/adapter.py`): `LLM_BASE_URL=http://localhost:1234/v1`, `LLM_API_KEY=lm-studio`,
`LLM_MODEL=local-model`. Override per run:

```bash
LLM_BASE_URL=http://localhost:1234/v1 \
LLM_MODEL=qwen3.6-35b-a3b-uncensored-claude-genesis \
  npm --prefix ui/control-plane run test:e2e:live
```

If the endpoint is down, the L3 spec **skips with a reason** (the only allowed skip) — never a silent
green. A real run that fails to write a file fails the test.
