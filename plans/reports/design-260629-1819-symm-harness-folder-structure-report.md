---
type: design
date: 260629-1819
scope: propose folder structure for a new symm-harness/ (learning from harness/)
status: structure proposal only — no files created yet
method: workflow (4 DNA extractors + 3 independent proposals + synthesis + adversarial critique)
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# symm-harness — folder structure proposal

## Spirit (what we're building)
A harness whose agent **thinks hard backstage and speaks gently frontstage**:
- **S1** hidden, technical thinker — deep reasoning allowed; user never sees the raw chain.
- **S2** psychological front — re-renders conclusions so a listener isn't overwhelmed.
- **S3** voice config first-class (persona / register / depth / no-markdown).
- **S4** can mobilize reasoning sub-agents; dispatches are logged.
- **S5** every skill call + every hook run is logged.
- **S6** the output layer is a polish pass — tighten wording, speak concisely.

Constraint the user set: **KISS/YAGNI, solo project, no bloat.** Don't reproduce harness/'s
60+ skills / 185k LOC. Carry only the *good bones*: hook-class taxonomy, thin-core SKILL.md +
references drawers, tracked-config vs gitignored-state split.

## The design thesis
**Two rooms + a slot in the wall.** `mind/` reasons and writes one artifact to disk;
`voice/` reads *only* that artifact and re-renders it. The seam is a **file**
(`state/handoff/<session>-conclusion.json`), not a folder name. This is the one decision
everything else hangs on — because in a single Claude session the two layers share a context,
so the wall has to be a *process handoff*, not a frontmatter promise.

## Recommended tree (6 top dirs + 2 root files)

```text
symm-harness/                          # TRACKED except state/
├── README.md                          # one screen: the two rooms, the conclusion.json slot, where logs live
├── symm-hooks.yaml                    # TRACKED posture: per-hook enabled/mode ONLY (class is code-constant; git diff = tamper trail)
│
├── mind/                              # ── BACKSTAGE (S1): the hidden thinker. Raw reasoning lives & dies here.
│   ├── reason/
│   │   ├── SKILL.md                   # driver: decompose → dispatch agents → consolidate → WRITE conclusion.json. layer:thinker, has Task
│   │   └── references/
│   │       └── decompose.md           # load-on-demand: how to split a problem & fan reasoning lenses
│   └── agents/                        # .md reasoners spawned via Task — isolated context, raw chain never returns verbatim
│       ├── deep-reasoner.md           # the powerful worker; returns report + JSON finding
│       └── consolidator.md            # collapses N chains → ONE conclusion.json (the only artifact that crosses the seam)
│
├── voice/                             # ── FRONTSTAGE (S2/S6): interpreter/polish. Reads ONLY conclusion.json.
│   ├── render/
│   │   ├── SKILL.md                   # re-render the conclusion psych-aware. layer:front, allowed-tools EXCLUDES Task; refuse if no conclusion.json
│   │   └── references/
│   │       └── cognitive-load.md      # chunk to ~4 WM items, pain-before-cure, de-jargon (S6)
│   └── rules/
│       ├── psych-front.md             # S2 doctrine (lead with what matters, pace, hide machinery) + humanizer polish, merged
│       └── two-layer-firewall.md      # the seam CONTRACT: render's only input is conclusion.json; wording-only scope-fence
│
├── hooks/                             # ── OBSERVABILITY SPINE (S4/S5) + voice injection (S3). Lifecycle entrypoints ONLY.
│   ├── hook_runtime.py                # PORTED ~verbatim: HOOK_CLASS taxonomy (telemetry|nudge|compliance) + 3 fail-mode wrappers
│   ├── voice_inject.py                # SessionStart, fail-open: voice.yaml → additionalContext POINTER (S3); broken → natural voice
│   ├── subagent_init.py               # SubagentStart: seed "you are a hidden reasoner; your chain stays backstage" (S4)
│   ├── track_skill_invocation.py      # PreToolUse:Skill → one trace line per skill call, dedup (S5)
│   ├── track_subagent_outcome.py      # SubagentStop → {agent, transcript-path, outcome} — the HONEST log unit (S4)
│   └── emit_session_summary.py        # Stop → roll up skills[]/agents[]/duration (S5)
│
├── scripts/                           # ── pure importable libs + deterministic CLIs (hooks import these; no narration-trust)
│   ├── paths.py                       # single PURE root/state resolver (writers mkdir, readers never create)
│   ├── trace.py                       # append-only JSONL writer + the record field-tuple constant. payload_hash, never payload
│   └── voice_resolve.py               # load-tolerant voice.yaml reader (missing/typo → silent DEFAULTS); the injector backend
│
├── data/                              # ── TRACKED human-edited config
│   └── voice.yaml                     # S3 source of truth: persona, register(soft|blunt|off), explanation_depth, no_markdown — doc-comment header
│
└── state/                             # ── GITIGNORED runtime (.gitignore day one)
    ├── handoff/
    │   └── <session>-conclusion.json  # THE SEAM: consolidator writes, render reads — render's ONLY context input
    ├── trace/
    │   └── trace-YYYYMMDD.jsonl       # append-only audit ledger — never rotates (S4/S5 replay spine)
    ├── telemetry/
    │   └── invocations.jsonl          # rotating usage counters (8MB → .bak); fine to lose
    └── sessions/
        └── <session>.json             # per-session rollup from emit_session_summary
```

Top dirs: `mind, voice, hooks, scripts, data, state` (6) + `README.md`, `symm-hooks.yaml`.
**Tracked:** everything except `state/`. **Gitignored:** `state/` only.

## Spirit-coverage matrix
| Spirit | Owner | How |
|---|---|---|
| S1 hidden thinker | `mind/` + `state/handoff/*.json` + `voice/rules/two-layer-firewall.md` | Raw chains run in isolated `Task` contexts; only `consolidator` writes `conclusion.json`; that file is render's *only* input. |
| S2 psychological front | `voice/render/SKILL.md` + `voice/rules/psych-front.md` | Re-renders the conclusion: lead with the point, pace to ~4 WM items, hide machinery. |
| S3 voice config | `data/voice.yaml` → `scripts/voice_resolve.py` → `hooks/voice_inject.py` | Tracked YAML is the single source; SessionStart hook injects resolved knobs as a pointer. **Injected, not enforced** (advisory, fail-open). |
| S4 mobilize agents + log | `mind/agents/*.md` via `reason/SKILL.md`; `hooks/subagent_init.py` + `track_subagent_outcome.py` | Per-**dispatch** logging (hook-driven). Intra-agent steps are NOT line-logged — the sub-agent transcript path is the replay handle. |
| S5 every skill + hook logged | `hooks/track_skill_invocation.py` + `scripts/trace.py` → `state/trace/`; `emit_session_summary.py` | One thin telemetry tap per lifecycle event, append-only JSONL. |
| S6 polish pass | `voice/render/SKILL.md` + `references/cognitive-load.md` | Explain-class refinement over a frozen conclusion; substance frozen, words only; early-exit if it already lands. |

## Learn-from matrix
| From harness/ | Carried mechanism | Where |
|---|---|---|
| L1 hook design | HOOK_CLASS as a **code constant**; 3 fail-mode wrappers (telemetry fail-open / nudge advisory / compliance fail-closed); config flips only `enabled`/`mode`; posture tracked-in-git | `hooks/hook_runtime.py` + `symm-hooks.yaml` |
| L2 skill files | thin-core `SKILL.md` (frozen frontmatter + boundaries + references table) + 2 new keys `layer: thinker\|front`, `logged: true`; deep procedure in `references/` drawers | `mind/reason/`, `voice/render/` |
| L3 filesystem/config | tracked-`data/` vs gitignored-`state/`; pure no-mkdir `paths.py`; two-sink split (append-only audit vs rotating telemetry); field-tuple shape checks, **no jsonschema dep** | `data/`, `state/`, `scripts/` |

## Key file contracts (the 5 load-bearing files)
- **`data/voice.yaml`** — keys: `persona` (none|+1), `register` (soft|blunt|off), `explanation_depth` (1-3), `no_markdown` (bool). Doc-comment header per knob. Loader never raises; unknown key → DEFAULTS. Scope-fenced: conversational prose only.
- **`scripts/trace.py`** — owns the record shape as a constant tuple: `{ts, actor, session, hook, event, tool, target, status, exit, dur_ms, note, payload_hash}`. `event` is a free verb (`skill_call`, `subagent_dispatch`, `front_render`) — new event types need no schema change. `payload_hash = sha256[:12]`, never the payload.
- **`mind/agents/consolidator.md`** — input: the N raw chains from `deep-reasoner`. Output: writes exactly ONE `state/handoff/<session>-conclusion.json` (ranked findings + verdict). The sole artifact permitted across the seam; raw chains die in its isolated context.
- **`voice/render/SKILL.md`** — `layer: front`, `allowed-tools` **excludes Task**. Body: chunk → price jargon → pain-before-cure → de-jargon → check. Boundary: input is `conclusion.json` and nothing else; **refuse if absent**; every number/ID/quote survives — cut words, never evidence; early-exit if it already lands.
- **`hooks/voice_inject.py` + `symm-hooks.yaml`** — `HOOK_CLASS="telemetry"`, fail-OPEN. SessionStart → call `voice_resolve.py` → short `additionalContext` pointing at `psych-front.md` + resolved knobs + the two non-negotiables (universal-harm floor, scope-fence). YAML flips `enabled`/`mode` only.

## First 5 files to write (bootstrap order)
1. `.gitignore` += `symm-harness/state/`, then `hooks/hook_runtime.py` (port ~verbatim) — gitignore first so no runtime ever commits.
2. `scripts/paths.py` + `scripts/trace.py` — the S4/S5 spine, usable before any skill exists.
3. `data/voice.yaml` + `scripts/voice_resolve.py` — voice tunable from day one.
4. `hooks/voice_inject.py` + wire it in `.claude/settings.json` — every session now logs + speaks in voice.
5. `mind/reason/SKILL.md` + `voice/render/SKILL.md` + `mind/agents/{deep-reasoner,consolidator}.md` — the two-room spine + the seam.

## Non-goals (what symm-harness will NOT have)
- No `plugins/` marketplace, no 14-plugin / 60-skill / 15-agent scale. Ships **2 skills + 2 agents**.
- No `schemas/` dir, no `install/` dir, no `pipeline/` dir — contracts live next to the code that owns them; host wiring is `.claude/settings.json`.
- No RBAC / ownership / protected-ref guards — solo = one actor; `resolve_actor()` attribution suffices.
- No `bin/` shim, no `hs_cli.py` dispatcher, no `manifest.json`/digest/`afk/`/`e2e/`/`standards/`.
- No fail-closed gate apparatus (`gate_stage.py`, `verification.json`). Only fail-open telemetry. The one hard control is the `allowed-tools` narrowing + the file-handoff seam.
- Trimmed voice: `register` = soft|blunt|off, `persona` none+1 — NOT the 9-rung ladder / 13-persona catalog / 6-level output_style / interview_rigor triad. S2 already covers "don't overwhelm."

## Honest caveat on the firewall (don't oversell it)
In a single-agent session `mind` and `voice` share one context, so "render mechanically cannot
see the chain" is **discipline, not a kernel wall**. The enforceable version: run `render` as a
**separate invocation seeded only by `conclusion.json`** (fresh context / `/clear` between, or a
dedicated render sub-agent that receives just the file). Defense-in-depth: (1) reasoning isolated
in Task sub-agents, (2) consolidator → file handoff, (3) `allowed-tools` denies render the Task
tool, (4) trace stores `payload_hash` not payload. Strong in combination; none is a hard guarantee
alone. `two-layer-firewall.md` should say "convention + capability-narrowing + process handoff,"
not "mechanically denied."

## Open questions
1. **Render isolation** — do you want render as a *separate session/sub-agent* (real firewall, costs a context hop) or *same-session discipline* (cheaper, leak-by-accident possible)? This is the one decision that changes the seam's strength.
2. **Name** — "symm" = symmetric (depth backstage ↔ clarity frontstage)? Confirm so README + dir naming match intent.
3. **Voice depth** — is `soft|blunt|off` enough, or do you want the harness's harshness ladder ported? (I recommend the 3-level version; S2 carries the rest.)
4. **conclusion.json shape** — minimal `{verdict, findings[], evidence[]}` to start, or richer? Decides `consolidator.md` ↔ `render` contract.
