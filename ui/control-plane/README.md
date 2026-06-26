# E21 Control Plane UI → Agent IDE

A React + Vite + TypeScript UI for the E21 realtime control plane, now grown into an
**opencode-style IDE**: prompt the agent, watch it run (graph + timeline), and **browse, edit, and
review the agent's file changes** alongside it.

## Run the IDE (live backend)

The live backend (`ui/ide/`) speaks the *same* control contract the fake does (it reuses `control/`)
but runs the **real agent** and adds a `/api/files/*` surface (tree/read/write/create/rename/delete/diff).

```bash
npm --prefix ui/control-plane run build   # build the UI once (the server serves dist/)
python3 -m ui.ide --port 8800             # one-command IDE → open http://127.0.0.1:8800
```

For hot-reload development, run the API and the Vite dev server separately:

```bash
python3 -m ui.ide --port 8800             # API only
npm --prefix ui/control-plane run dev     # UI at http://localhost:5173 → talks to :8800
```

Prompt the agent in the bottom dock (e.g. *"Create calc.py with an add(a,b) function"*). It runs
against the local LLM (`LLM_BASE_URL`, default LM Studio `localhost:1234`); files it writes land in
`var/workspace` and appear + flash in the explorer, with the diff under the **Changes** tab. Editing a
file in the CodeMirror editor and pressing ⌘/Ctrl+S writes it back. No LLM is needed to browse/edit.

The agent is told its exact tool names (`fs_write` etc.) via a catalog injected into the system prompt,
so it edits reliably instead of guessing tool names.

---

## Fake-backend slice (original contract harness)

The fake (`tools/fake_control_server.py`) reuses `control/` — the same `Redactor`, `SessionSeq`,
`parse_command`, registries, and `build_snapshot` the live backend does — so wiring a backend is
**"change the URL"**, not "re-render".

## Run the demo

Two processes. From the repo root:

```bash
# 1) the fake control server (loads the T1 fixture, deterministic)
python3 tools/fake_control_server.py --port 8800 --no-reality

# 2) the UI dev server (defaults to http://localhost:8800)
npm --prefix ui/control-plane run dev
# open the printed URL (e.g. http://localhost:5173)
```

The T1 scenario renders: Agent **Graph** (O → A done / B done / C pending), the **Timeline**
of the 9 events (the `loop.tool` event shows `"api_key":"[REDACTED]"` — never the raw secret),
the **Approval modal** for the waiting checkpoint (Approve / Reject), the **Inspector** (click a
node), and the **Prompt box** (Send → a `SubmitPrompt` command, with the returned ack).

Pass nothing / `--no-reality` for a clean replay; drop `--no-reality` to inject latency and
forced mid-stream SSE drops (the UI recovers via `Last-Event-ID`).

## Test

```bash
npm --prefix ui/control-plane run test      # vitest: adapter, components, contract-seam
npm --prefix ui/control-plane run build     # tsc --noEmit + vite build
```

The **contract-seam test** (`src/test/contract-seam.test.ts`) is the definition of Done: it
boots the real fake server as a child process and drives the real adapter against it, asserting
(1) the UI only ever sees the redacted `ui_payload`, (2) redaction renders as `[REDACTED]`,
(3) Approve posts a real `RuntimeCommand` the server accepts, and (4) a forced SSE drop is
recovered via `Last-Event-ID` with no loss and no duplication.

## Drop-in to the real backend

`src/config.ts` is the only transport config. When the real backend emits the same envelope
(it reuses the same `control/` contracts), point the UI at it with **zero render changes**:

```bash
VITE_CP_BASE_URL=https://your-backend npm --prefix ui/control-plane run dev
```

That zero-diff swap is the criterion this slice exists to make true.

## Architecture (one-way data flow)

```
fake server ──HTTP/SSE──▶ src/adapter/controlPlane.ts ──▶ src/state/store.ts ──▶ components
                          (the single transport door)       (written only here)     (read + dispatch commands)
```

- The **adapter** is the only place that touches `fetch` / `EventSource`. It surfaces the
  redacted `ui_payload`, carries the read token via `?token=` (an `EventSource` can't set
  headers), and reconnects with backoff resuming `Last-Event-ID`.
- The **store** is written only by the adapter's `onEvent` (dedup by `seq`). Components never
  mutate runtime state — every action is a `RuntimeCommand` posted through the adapter.
- TS types in `src/contracts/generated.d.ts` are **generated** from the `control/` dataclasses
  (`python tools/gen_ts_contracts.py`); `--check` is the CI drift guard.
