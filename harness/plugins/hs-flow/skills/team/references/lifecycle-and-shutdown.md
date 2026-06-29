# Lifecycle and Shutdown

> Load this file when you need detail on the shutdown protocol, idle state, TeamDelete, error recovery, and abort.

## Team lifecycle

```
TeamCreate → TaskCreate x N → spawn teammates → monitor → synthesize → shutdown all → TeamDelete
```

A session can have at most one team — call `TeamDelete` before creating a new team.

## Shutdown Protocol (teammate receiving shutdown_request)

1. Approve shutdown UNLESS currently in the middle of a critical operation.
2. If work is complete: `TaskUpdate` → `completed` BEFORE approving.
3. If work is unfinished: keep the task status as-is (or set `blocked` with a brief handoff note) BEFORE approving or rejecting.
4. Reject: explain briefly why.
5. Extract `requestId` from the JSON shutdown request → pass it into `shutdown_response`.

Shutdown may be slow — a teammate finishes its current request before exiting.

## Idle State — Normal behavior

- Idle after sending a message is NORMAL — not an error.
- Idle = waiting for input, not a lost connection.
- Sending a message to an idle teammate will wake it up.
- **Do not** treat an idle notification as a completion signal — check task status instead.

## TeamDelete

```
TeamDelete()   # no parameters — call only after all teammates have shut down
```

Deletes shared team resources. Fails if active teammates remain.

## Display Modes

| Mode | When to use |
|---|---|
| `auto` (default) | split panes if inside tmux, otherwise in-process |
| `in-process` | single terminal — `Shift+Up/Down` to navigate, `Ctrl+T` for task list |
| `tmux/split` | one pane per teammate — requires tmux or iTerm2 |

Split panes are NOT supported in: VS Code terminal.

## Error Recovery

1. **Check status**: `Shift+Up/Down` (in-process) or click pane (split).
2. **Redirect**: send a direct message with adjusted instructions.
3. **Replace**: shut down the failing teammate, spawn a new teammate for the same task (`TaskUpdate` reset to `pending`).
4. **Reassign**: `TaskUpdate` the stuck task to someone else to unblock dependents.

## Abort Team

```
1. SendMessage(type: "shutdown_request") to each teammate
2. TeamDelete()
```

No response: close the terminal or kill the session.
Orphaned tmux: `tmux ls` → `tmux kill-session -t <name>`.

## Known Limitations

| Limitation | Detail |
|---|---|
| Model lock | All teammates must use the same Opus model — no mixed-model |
| One team per session | Call TeamDelete before creating a new team |
| No resume | `/resume` and `/rewind` do not restore in-process teammates |
| Task status lag | A teammate may not have updated yet; check manually if in doubt |
| No nested teams | Only the lead manages the team; teammates cannot create sub-teams |
| VSCode unsupported | Agent Teams requires a CLI terminal |

## Token Budget Reference

| Template | Estimated tokens | Notes |
|---|---|---|
| research (3) | ~150K-300K | Read-only, moderate |
| cook (4) | ~400K-800K | Highest — code generation |
| review (3) | ~100K-200K | Read-only, moderate |
| debug (3) | ~200K-400K | Mixed read/execute |

Agent Teams consume more tokens than subagents (every teammate runs Opus).
Use when parallel exploration and real discussion add genuine value. Single task → single subagent is more efficient.

## When to use Agent Teams vs Subagents

| Situation | Subagents | Agent Teams |
|---|---|---|
| Focused task (test, lint, single review) | Preferred | Overkill |
| Sequential pipeline (plan → code → test) | Preferred | No |
| 3+ independent parallel workstreams | Possible | Preferred |
| Adversarial hypothesis debugging | No | Preferred |
| Cross-layer work (FE + BE + test) | Possible | Preferred |
| Workers who need to discuss and challenge each other | No | Preferred |
| Tight token budget | Preferred | No |
