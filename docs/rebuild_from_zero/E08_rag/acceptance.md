# E08 — Acceptance Criteria (draft)

## S08.1 health gate
- Given Qdrant is down, When `rag_health` runs, Then `ok=false`; And search/ingest are not attempted (classified as dependency failure).

## S08.2 ingest
- Given a workspace folder, When `rag_ingest` runs, Then `.md/.txt/.py` files are chunked, embedded, and upserted; other extensions are skipped.

## S08.3 re-ingest replace
- Given a source already ingested, When re-ingested, Then its previous chunks are deleted before upsert (count stable, no dupes).

## S08.4 search threshold
- Given `score_threshold=0.8`, When searching, Then only hits ≥ 0.8 are returned, each with `source` and `chunk_index`.

## S08.5 sandbox
- Given a path outside the workspace, When ingest/search is called, Then it is rejected.
