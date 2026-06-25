# E18 — Acceptance Criteria (draft)

## S18.1 run list
- Given ≥1 run, When the dashboard loads, Then runs are listed newest-first with status.

## S18.2 event browse
- Given a selected run, When viewing events, Then events can be filtered by kind and tool.

## S18.3 summary
- Given a finished run, When viewed, Then summary metrics (steps, parse_errors, tool_calls, ...) are shown.

## S18.4 refresh
- Given an active run, When the operator reloads, Then newly written events appear.

## S18.5 gate surface
- Given a pending review (E16), When opened in the dashboard, Then the reviewer can approve/deny/annotate from the UI.
