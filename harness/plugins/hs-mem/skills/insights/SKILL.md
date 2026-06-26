---
name: hs-mem:insights
description: "Surface read-only usage insights from harness telemetry — hot vs never-used skills, workflow chains, gate-block patterns — and propose end-user optimizations. Use when reviewing how the harness is actually used. Advisory only; never mutates."
category: mem
license: AGPL-3.0
keywords: [insights, surface, read-only, usage, harness, telemetry]
user-invocable: true
allowed-tools: [Bash, Read]
when_to_use: "Invoke to review how the harness is actually being used and get optimization suggestions: which skills are hot/cold, which owned skills are never invoked, what workflow chains run, where gates block. Read-only — pairs with hs-mem:retro (git-history) and hs:setup (to act on a suggestion)."
argument-hint: "[--days N] [--lens workflow|skill_usage|all]"
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-mem:insights — read-only usage insights

Aggregates the harness telemetry sinks (`harness/state/telemetry/*.jsonl`) through the read-only lens
front-end and narrates what the numbers say, then proposes optimizations the user can act on. It
NEVER mutates config, code, skills, or telemetry — every suggestion is advisory, and acting on one
goes through the normal tools (`/hs:setup`, a skill edit, a backlog entry).

This is the telemetry twin of `hs-mem:retro` (which reads git history). Use both for a full picture.

## Flow

1. **Gather** (read-only, deterministic):

   ```bash
   python3 harness/scripts/analyze_telemetry.py --lens all --days 30
   ```

   Add `--days N` to widen/narrow the window, `--lens skill_usage` (or `workflow`) for one lens,
   `--format json` if you want to post-process. The command prints a `## NOT measured` block — read
   it: it enumerates what telemetry does NOT capture (cost, correctness, non-script wall-clock). Do
   not let a clean number read as full coverage.

2. **Respect the gates.** Each lens carries `gated` / `sufficient`. When `gated: true` the data is
   below the low-volume threshold — report the raw counts but SUPPRESS recommendations (sparse data
   is noise). Say so explicitly rather than over-reading three data points.

3. **Narrate + propose.** For the data that IS sufficient, surface:
   - **Hot skills** — the most-invoked; candidates to keep fast and well-documented.
   - **Never-invoked owned skills** (`never_used_owned`) — trim/merge candidates. RAISE them; never
     auto-remove. A skill may be new, seasonal, or load-bearing-but-rare — ask before cutting.
   - **Workflow chains** vs declared (`skill-chains.yaml`) — undeclared common chains may be worth
     declaring; declared-but-unused chains may be stale.
   - **Gate-block / bypass patterns** — recurring `write_guard_bypass` or gate blocks in
     `hook-telemetry.jsonl` suggest a detector that is too tight or a workflow papering over a gate.

4. **Hand off, do not act.** If a suggestion is config (voice, guard, roster, language) point at
   `/hs:setup`. If it is a skill change, write a `BACKLOG.md` entry. If it is a stage/detector
   tuning, describe the change and let the user decide — detector loosening is a posture decision.

## Boundaries

- READ-ONLY: this skill runs `analyze_telemetry.py` (which never writes) and reads JSONL sinks. It
  must not edit telemetry, config, or code. Producing a report is the whole job.
- Output language follows `harness/data/output.yaml` (default vi); evidence (counts, skill ids,
  session ids) is never translated.
- Never present a suggestion as a decision already made. The user adjudicates; the lens only counts.
