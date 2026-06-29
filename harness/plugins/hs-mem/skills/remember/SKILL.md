---
name: hs-mem:remember
description: "Capture the session's real knowledge — decisions made, non-obvious facts learned, user feedback — into the right durable home (DEC ledger, auto-memory, or BACKLOG) after you approve each entry. Use when you just made an architectural decision, learned something non-obvious, got correcting feedback worth keeping, or when the decision-capture nudge fires."
category: mem
license: AGPL-3.0
keywords: [remember, capture, session, real, knowledge, decisions]
user-invocable: true
allowed-tools: [Bash, Read, Write, Edit]
when_to_use: "Invoke at the end of a work chunk to record what should outlive the session: a decision made (-> DEC), a non-obvious fact or constraint learned (-> memory), or feedback on how to work (-> feedback memory). Pairs with the decision_capture_nudge hook, which flags an unrecorded decision-shaped change; this skill does the actual capture, with the human approving every entry before it is written."
argument-hint: "[--since <git-ref>] [hint about what to capture]"
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-mem:remember — explicit knowledge capture

The LLM-backed C-leg of memory-v2. Where the `decision_capture_nudge` hook is a
deterministic "you shipped a decision-shaped change and the ledger did not move"
nudge, this skill does the real judgment: it reads the recent session, decides
WHAT is worth keeping, and proposes durable entries — never auto-writing a
decision or a gate. The human approves each one before it lands.

## When it earns its keep

- A **decision** was made (a choice between approaches, a threshold, a schema, a
  scope cut) -> record a DEC.
- Something **non-obvious** was learned that the repo does not already encode (a
  constraint, a gotcha, a verified fact) -> record a memory.
- The user gave **feedback** on HOW to work (a correction, a confirmed approach)
  -> record a feedback memory.

If none holds, say so and write nothing. Capturing noise is worse than capturing
nothing.

## The homes (one fact, one home)

| Kind | Home | Channel |
|---|---|---|
| Architectural decision | `docs/decisions.md` (or the active plan's Validation Log before the register is wired) | `harness/scripts/decision_register.py` |
| Durable fact / constraint / gotcha | the session auto-memory dir | a memory file + a one-line `MEMORY.md` pointer |
| User-work feedback | the session auto-memory dir | a `feedback`-type memory (with **Why** + **How to apply**) |
| Deferred work | `BACKLOG.md` | one line + a report link |

## Flow (always human-in-the-loop)

1. **Review** — read the recent turns (and the `--since <git-ref>` diff when
   given) for decisions, learnings, and feedback. Evidence-anchored: each
   candidate cites a file:line, an ID, a quote, or a concrete change. No
   fabrication — if you cannot point at evidence, do not propose it.
2. **Classify** — sort each candidate into DEC / memory / feedback / backlog and
   confirm it is not already recorded (search the ledger + the memory index
   first; one home per fact — update an existing entry rather than duplicate).
3. **Propose** — present the candidates as a short numbered list: kind, the exact
   text to write, the destination, and the evidence. Recommend which are worth
   keeping and which are noise.
4. **Approve** — the user picks which to write (all / some / none / edited).
   Nothing is written before this.
5. **Write** — only the approved entries, each through its channel above. A DEC
   goes through `harness/scripts/decision_register.py` (it stamps actor + ts); a
   memory is a file plus its `MEMORY.md` pointer.

## Hard rules

- **Never auto-write a DEC or touch a gate-config file.** This skill proposes;
  the human approves; the register writes. A gate-enforcing file (`stage-policy`,
  `ownership`, the guard list, a hook) is never edited here — it is human-placed.
- **No dev-id labels in shipped artifacts** — DEC / plan IDs live in the ledger
  and register tooling, never leaking into code comments, test names, or commits.
- **Evidence is never invented and never translated** — file:line / IDs / SHAs /
  quotes are copied verbatim.
- **Output language** follows `harness/data/output.yaml`; this instruction text
  stays English.

## Pairs with

- `decision_capture_nudge` — the A-leg hook (deterministic, nudge-class, default
  OFF) that fires the reminder bringing you here.
- `harness/scripts/memory_gap.py` — the fence / parse-gap detector behind the
  older memory-gap nudge; a different, lower-tier signal.
