---
name: hs-research:repomix
description: >-
  Pack a codebase or subtree into an AI-friendly digest (XML, Markdown, plain,
  JSON). Use for LLM context snapshots, external library audits, or large review prep.
  Pairs with hs:scout.
category: research
license: AGPL-3.0
keywords: [repomix, pack, codebase, subtree, ai-friendly, digest]
when_to_use: "Use for LLM context snapshots, external library audits, or large review prep."
user-invocable: true
allowed-tools: [Bash, Read, Write, Grep, Glob]
metadata:
  owner: harness
  compliance-tier: workflow
argument-hint: "[path] [--style xml|markdown|plain|json] [--include <glob>] [--dry-run]"
---

# hs-research:repomix — pack a codebase into an AI-friendly digest

Packs a repo or subtree into a single file for loading into an LLM.
The `repomix` CLI is an **optional external dependency** — the skill feature-detects
at runtime; if missing, it provides install instructions rather than hard-failing.

> **The artifact is a temporary build output** — do NOT commit the digest to git.
> `harness/state/` is in `.gitignore`; use `tmp/` or a path outside the repo.

## When to use

| Situation | Action |
|---|---|
| Onboarding a new codebase, need the full picture | pack everything, `--style markdown` |
| Implementing a feature, need module context | pack subtree `--include "src/module/**"` |
| Reviewing an external library | `--remote owner/repo` via npx |
| Auditing for secrets before deploy | pack + security check (enabled by default) |
| Context nearing limit, need compression | pair with `hs-meta:context-engineering` |

## CLI check

```bash
# Feature-detect
repomix --version 2>/dev/null || echo "MISSING — install: npm i -g repomix"
```

If the CLI is missing -> recommend installing it, fall back to reading files manually
(`hs:scout` + Read per file), and report `[NO_CLI_FALLBACK]` in the output.

## Workflow

1. **Determine scope** — local repo, subtree, or remote? Accept path/glob from
   the user or ask via AskUserQuestion if missing.

2. **Check tokens first** — load `references/output-handling.md`; estimate expected
   token count before running on a large repo. If the budget is tight ->
   suggest narrowing scope or using `--remove-comments --no-line-numbers`.

3. **Run pack** — see `references/invocation-patterns.md` for example commands
   covering each situation (subtree, remote, security audit, doc context).

4. **Check output** — review token count in the summary; if over budget ->
   refine `--include` / `-i` and rerun. Do not pass a digest larger than the
   budget to the LLM without warning.

5. **Confirm safety** — security check is enabled by default (Secretlint); if
   warnings appear -> review the flagged files before using the digest. Do not
   use `--no-security-check` unless the user explicitly requests it.

6. **Return results** — absolute path of the digest file, token count, and
   warnings (if any). If the digest exceeds the context budget -> suggest
   `hs-meta:context-engineering` to decide which parts to load.

## Common flags

| Flag | Meaning |
|---|---|
| `--style xml\|markdown\|plain\|json` | output format |
| `--include "glob,glob"` | pack only matching files |
| `-i "glob,glob"` | additional ignores beyond .gitignore |
| `--remove-comments` | reduce tokens by stripping comments |
| `--no-line-numbers` | reduce tokens further |
| `--remote owner/repo` | pack a GitHub repo without cloning |
| `--copy` | copy to clipboard instead of writing a file |
| `--token-count-tree [N]` | view token distribution by directory tree |
| `--no-security-check` | disable secret scanning (use with care) |

## Boundaries

- Do NOT commit the digest to git — all output is a temporary build artifact.
- Do not modify code based on digest content — this skill prepares context;
  it does not implement. To implement -> `hs:cook`.
- Do not run `--remote` on a private repo without explicit user confirmation.
- Finish: absolute path of the digest + token count + security warnings
  (if any) + suggested next step (hs-meta:context-engineering / pass to LLM /
  implement).

## HARD-GATE (real wiring)

- **harness/state never-in-git**: `harness/state/` is in `harness/.gitignore`
  — writing digests there is git-safe.
- **No harness gate blocks repomix** — this skill is a pure tool wrapper;
  compliance rests on not committing artifacts (DRY, dev discipline).
- **hs-meta:context-engineering** (`harness/plugins/hs-meta/skills/context-engineering/`):
  run BEFORE to check the budget, run AFTER if the digest is larger than expected.
- **hs:scout** (`harness/plugins/hs/skills/scout/`): run BEFORE repomix if
  file location must be confirmed before deciding on pack scope.
