# External scouting — Gemini/OpenCode CLI

Use the `ext` flag when a large context window (1M+ tokens) is needed or SCALE is 3-5.

## Tool selection

| SCALE | Tool | Fallback |
|---|---|---|
| ≤ 3 | Gemini CLI | internal-scouting |
| 4-5 | OpenCode CLI | internal-scouting |
| ≥ 6 | → use `internal-scouting.md` | — |

## Installation check

```bash
which gemini
which opencode
```

If missing → ask user:
- **Yes, want to install** → guide installation + auth
- **No** → fall back to `internal-scouting.md`, record `[FALLBACK_INTERNAL]` in the report

## Gemini CLI (SCALE ≤ 3)

```bash
timeout 120 gemini -y -m gemini-2.5-flash --prompt "[prompt]" 2>&1
```

Fallback model on 429: try `gemini-2.5-flash` before giving up.

## OpenCode CLI (SCALE 4-5)

```bash
opencode run "[prompt]" --model opencode/grok-code
```

## Parallel spawn (Bash subagents)

Use the Agent tool with multiple Bash subagents in a single message:

```
Agent 1 (Bash): "timeout 120 gemini -y -m gemini-2.5-flash --prompt 'Scout harness/hooks/ for gate scripts' 2>&1"
Agent 2 (Bash): "timeout 120 gemini -y -m gemini-2.5-flash --prompt 'Scout harness/scripts/ for analytical scripts' 2>&1"
Agent 3 (Bash): "timeout 120 gemini -y -m gemini-2.5-flash --prompt 'Scout harness/rules/ for rule files' 2>&1"
```

## Error handling

| Error signal | Action |
|---|---|
| Exit code ≠ 0 | Drop agent, record error in report |
| `RESOURCE_EXHAUSTED` / `429` | Try fallback model, do not retry |
| `PERMISSION_DENIED` / `UNAUTHENTICATED` | Notify user, fall back to internal |
| 2+ agents fail | Switch entirely to `internal-scouting.md` |

## File content chunking

See `internal-scouting.md` — same formula (500 lines/chunk), applied to
external agents via Bash subagents.
