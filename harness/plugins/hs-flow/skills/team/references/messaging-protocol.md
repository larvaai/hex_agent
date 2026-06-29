# Messaging Protocol and Task Claiming

> Load this file when you need detail on SendMessage types, task claiming, and plan approval flow within an Agent Team.

## SendMessage Types

| Type | When to use | Required parameters |
|---|---|---|
| `message` | DM to one specific teammate | `recipient` (name, not agent ID) |
| `broadcast` | Blocking issue affecting the whole team | — |
| `shutdown_request` | Request a teammate to exit gracefully | — |
| `shutdown_response` | Teammate approves or rejects shutdown | `request_id` (extracted from JSON request) |
| `plan_approval_response` | Lead approves or rejects a teammate's plan | `request_id` |

- `broadcast` is used very sparingly — only for a genuine blocking issue.
- Do not send structured JSON status in the message body — use plain text.
- Always address teammates by NAME (e.g. `researcher-1`, `dev-2`), not by agent ID.
- Messages must contain actionable content, not just "I'm done".

## Task Claiming — Order of operations

1. Claim the lowest-numbered unblocked task first (earlier tasks provide context for later ones).
2. `TaskUpdate` status → `in_progress` BEFORE starting work.
3. After completion: `TaskUpdate` → `completed` BEFORE sending a message to the lead.
4. Check `TaskList` after each task to discover newly unblocked tasks.
5. If all tasks are blocked: notify the lead and request help unblocking.

## Harness Backing — Race-Free Claims

Harness provides single-winner claim primitives via `harness/scripts/claims.py`:

```
# Acquire claim (O_CREAT|O_EXCL — race-free, 1 winner)
python3 harness/scripts/claims.py acquire <task_id> [--lease-s N]

# Release when done (rename into .done/, do not delete)
python3 harness/scripts/claims.py release <task_id> --claim-id <id>

# Check state (UNCLAIMED | CLAIMED | STALE)
python3 harness/scripts/claims.py status <task_id>

# Reclaim a STALE claim from another teammate (atomic rename-consume)
python3 harness/scripts/claims.py reclaim <task_id>
```

Lease duration comes from `harness/data/team.yaml` (`claims.lease_s`, default 4h).
Audit trail: every acquire/release/reclaim appends an event to the trace log.

## Remote Task Store (optional)

`harness/scripts/task_store.py` — read + add_comment only; does NOT mutate state.
The gate path (hook) is always network-free; task_store is advisory only.
Config: `harness/data/task-store.yaml` (token via env var, not stored in the file).

## Plan Approval Flow

When `--plan-approval` or `plan_mode_required` is set in the task:

1. Teammate works read-only (no file edits) — research and plan the approach.
2. Teammate sends `plan_approval_request` to the lead via ExitPlanMode.
3. Lead reviews → `SendMessage(type: "plan_approval_response", approve: true/false, request_id: <id>)`.
4. Reject: teammate stays in plan mode, revises based on feedback, resubmits.
5. Approve: teammate exits plan mode and begins implementing.

Suggested lead criteria: approve only plans that include test coverage; reject plans that modify a schema without a migration.

## Monitor Pattern

```
1. Lead spawns teammates (run_in_background: true)
2. Teammates TaskUpdate → completed + notify lead
3. Lead checks TaskList after 60s or after each completion message
4. Lead acts on verified task state (spawn tester, shutdown, reassign)
5. Task status lag → message the owner directly before changing status
```

Idle is NOT a completion signal — check task status before drawing conclusions.
