# Manual runbook — control-plane IDE (the irreducible cases)

Human checklist for what automation can't cheaply cover: visual/feel, real-solve judgment, the live
approval interaction, and server-bounce reconnect. Each step: **action → expected → ✅/❌**.

**Boot** (one terminal each):
```bash
python3 -m ui.ide --host 127.0.0.1 --port 8800 --token dev-token --session t1_demo
LLM_BASE_URL=http://localhost:1234/v1 LLM_MODEL=<your-35b> :   # ensure the 35B is up (LM Studio, TEXT-mode JSON)
npm --prefix ui/control-plane run dev                          # UI at http://localhost:5173
```
Open http://localhost:5173.

| # | Action | Expected | ✅/❌ |
|---|---|---|---|
| 1 | Cold load | Graph shows the root node; chat shows its placeholder; the file tree populates from the workspace. | |
| 2 | **Real solve** — prompt `create calc.py with add(a,b)`, Send | Timeline streams `loop.*`; chat folds the prompt → a tool step ✓ → an assistant bubble; `calc.py` appears in the tree (changed flash); run pill → `finished`. **Judge: did it actually write a correct `add`?** | |
| 3 | **Redaction (human-eye security)** — run a prompt whose tool args carry a secret-keyed field (or seed one) | On-screen shows `[REDACTED]`; the raw secret is **absent** from the DOM and from devtools Network/Console (open them and search). | |
| 4 | **Approve interaction** (manual-only — no live gate in the backend, see note) | If/when a checkpoint surfaces, the Approval modal appears bottom-right; click Approve → modal clears, run resumes. | |
| 5 | **Kill-server reconnect** — `kill` the `ui.ide` process mid-run, then relaunch it (same port) | Connection badge → `RECONNECTING`; on relaunch it reconnects and the stream emits a **resync** frame (the buffer is empty after a bounce — this is resync, *not* a resume); timeline does not duplicate rows. | |
| 6 | **Editor** — open a file, edit, watch the dirty pill ●, `⌘/Ctrl+S` | Dirty ● appears on edit, clears on save; diff updates; syntax highlight is correct for the language. | |
| 7 | **Terminal** — open the dock, run `ls`; then try `rm -rf /` or `sudo …` | `ls` prints stdout + exit code; the destructive/blocked command is **refused** (policy), not run. | |
| 8 | **Multi-session** — `+ New`, then switch between sessions | Dropdown updates; graph / timeline / chat / explorer reset to a clean state for the switched-to session (shared workspace, separate event buffer + diff baseline). | |
| 9 | **Visual / responsive** — resize; check badges | Layout stays intact; `RECONNECTING`/run-pill styling reads correctly; dark/light (if applicable) is legible. | |

## Why steps 4 & 5 are manual (cut from L3 after red-team)

- **Approval (F4).** `ui/ide/server.py:173-174` — `ApproveCheckpoint`/`RejectCheckpoint` are no-ops
  beyond `command.received`; the single-agent runner has **no live approval gate**, so a *waiting*
  checkpoint never reaches the UI to be clicked end-to-end. The modal/interaction can only be judged
  by hand. (Logged as a candidate backend slice — DEC-T4.)
- **Server-bounce (F5).** A relaunched `ui.ide` is a fresh process with an **empty in-memory buffer**
  (`ui/ide/session.py`, no persistence). Last-Event-ID then hits `needs_resync` and the server emits a
  **resync** frame — the honest invariant to eyeball — not a resume. "No duplicate rows" here is a
  property of total state loss, not real resume; true resume is covered at L0 against a persistent
  buffer. Same-port relaunch is also TIME_WAIT-flaky, so this stays manual.

## Done when

Every L3-skippable + visual case above is checked, and a new dev can run any tier straight from the
[README](./README.md) table with zero tribal knowledge.
