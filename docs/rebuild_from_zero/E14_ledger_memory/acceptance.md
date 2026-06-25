# E14 — Acceptance Criteria (draft)

## S14.1 append
- Given an entry, When `ledger_append`, Then it is written as one JSONL line with type/title/data/tags/timestamp/id.

## S14.2 search
- Given entries with tags, When `ledger_search(tag="rag")`, Then only matching entries return.

## S14.3 append-only + durable
- Given existing entries, When new ones are appended and the process restarts, Then old entries are unchanged and still readable.

## S14.4 get + stats
- Given an entry id, When `ledger_get`, Then that entry returns; And `ledger_stats` reports counts by type.

## S14.5 RAG embed (optional)
- Given embedding enabled, When a lesson is appended, Then it becomes searchable via experience RAG.
