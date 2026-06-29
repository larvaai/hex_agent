# Config reference (on-demand — NOT always-load)

Every tunable knob, the file that holds it, its default, how to change it, and
whether an env var overrides it. This is the index; each YAML file's own header
comment carries the per-knob detail. Load this when a question is "where do I
change X / what does X default to", not on every turn.

Two truths to keep in mind (full text in `harness/rules/harness-contract.md`):

- Config is **tamper-visible, not tamper-proof**: edits land as a git diff and a
  trace line. An env var marked `*` below repoints the config **file** itself — a
  known gap; the pre-push hook scrubs every `HARNESS_*` before judging a push, so
  it cannot weaken a protected-branch push.
- Human-edited config is YAML; machine-written data is JSON/JSONL. Edit the YAML
  by hand, or use the named tool where one exists.

## Conversational register & generated output

| Knob | File | Default | Change how | Env |
|---|---|---|---|---|
| `terminal_voice_level` (0–5) | `harness/data/terminal-voice.yaml` | 5 | edit or `/hs-meta:voice` | `HARNESS_TERMINAL_VOICE` * |
| `voice_level` (1–9) | `harness/data/terminal-voice.yaml` | 5 | edit or `/hs-meta:voice` | * |
| `persona` | `harness/data/terminal-voice.yaml` | none | edit or `/hs-meta:voice` | * |
| `no_markdown` | `harness/data/terminal-voice.yaml` | false | edit or `/hs-meta:voice` | * |
| `interview_rigor` / `action_prompting` / `detail_level` | `harness/data/terminal-voice.yaml` | standard | edit | * |
| `output_style` (off or 0–5; **NOT scope-fenced** — shapes prose AND code, profiles in `harness/data/output-styles/`) | `harness/data/terminal-voice.yaml` | off (null) | edit | * |
| `language` (report/doc prose) | `harness/data/output.yaml` | vi | edit | — |
| `humanize` | `harness/data/output.yaml` | true | edit | — |

The voice knobs are conversational only: they never change code, generated
docs, evidence, or a gate decision.

## Gates, guards & autonomy

| Knob | File | Default | Change how | Env |
|---|---|---|---|---|
| guard `preset` + `overrides` | `harness/data/guard-policy.yaml` | balanced | edit or `guard_config.py` | `HARNESS_GUARD_POLICY` * |
| stage gates (push/pr/ship/deploy) | `harness/data/stage-policy.yaml` | shipped | edit | `HARNESS_STAGE_POLICY` * |
| protected branches | `harness/data/protected-branches.yaml` | shipped | edit | `HARNESS_PROTECTED_BRANCHES` * |
| autonomy level — cook's voluntary pause cadence, resolved by `autonomy_policy.py`: default pauses at plan-approve + ship, `ask_all` after every phase, `god` none. Hard stage gates apply at every level (no level self-ships). | env only | default | — | `HARNESS_AUTONOMY` (default\|ask_all\|god) |
| `cook.parallel` — opt-in multi-agent cook for independent phases (default OFF = sequential, non-breaking). Resolved by `cook_parallel_plan.py`: `--parallel` flag > env > config > default. Every slice verified before merge; full suite at the integration barrier; gates never bypassed. | `harness/data/cook.yaml` | false | edit or `--parallel` | `HARNESS_COOK_PARALLEL` (1/true/yes/on) |
| `cook.parallel_max` — advisory cap on concurrent slices; the orchestrating agent applies it at fan-out (`cook_parallel_plan.py` emits the partition but does not enforce the cap). | `harness/data/cook.yaml` | 4 | edit | — |
| telemetry hooks | (hook class, code) | on | — | `HARNESS_TELEMETRY_DISABLED` |
| hook crash log (exception metadata, no PII) | `harness/hooks/.logs/hook-crashes.log` | on | — | `HARNESS_HOOK_AUDIT_DISABLED` |
| standards line budget (advisory) | (installer warning) | 800 | `export` | `HARNESS_STANDARDS_MAXLOC` |

## Ownership, roster & identity

| Knob | File | Default | Change how | Env |
|---|---|---|---|---|
| `reviewers` / `allow_self_review` / `claims.lease_s` | `harness/data/team.yaml` | [] / false / 14400 | installer prompt or edit | none (one load path by design) |
| fs_guard zones | `harness/data/ownership.yaml` | shipped | edit | `HARNESS_OWNERSHIP_FILE` * |
| work-unit file ownership | `harness/data/work-ownership.yaml` | shipped | edit or `ownership_gate.py` | `HARNESS_WORK_OWNERSHIP_FILE` * |
| per-agent_type write lanes (agent_rbac_guard) | `harness/data/agent-permissions.yaml` | shipped (default_deny + role lanes) | edit | `HARNESS_AGENT_PERMISSIONS_FILE` * |
| recorded actor / agent | env | git email | `export` | `HARNESS_USER`, `HARNESS_AGENT` |

## Pipeline

| Knob | File | Default | Change how | Env |
|---|---|---|---|---|
| declared SDLC chains | `harness/data/skill-chains.yaml` | shipped | edit | `HARNESS_SKILL_CHAINS` * |
| critique `mode`/`lenses`/`loop`/`verdict` | `harness/data/critique.yaml` | shipped | edit | — |

After editing a tracked config, rebuild and re-verify is not required — these are
deployer-localized, so `verify_install --strict` treats edits as customization,
not drift (code still fails on any mismatch).
