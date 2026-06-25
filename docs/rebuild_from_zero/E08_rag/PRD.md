# E08 — RAG (PRD, draft)

Phase: P2 · Features: F12

## Problem
Cần trí nhớ/tra cứu ngoài prompt để giảm context rác và trả lời dựa tài liệu.

## Goal
RAG local: Qdrant + fastembed, luồng `health → ingest → search`, sandbox workspace, lọc theo score threshold.

## Scope — In
- `rag_health` (kiểm Qdrant + collection) — **gate** trước search.
- `rag_ingest(path)`: collect `.md/.txt/.py` trong workspace → chunk → embed → **xóa chunk cũ theo source** → upsert.
- `rag_search(query, top_k, score_threshold)`: embed → query → lọc ngưỡng → trả hits có `source`+`chunk_index`.
- Đăng ký như một feature/tool sau kernel (E06 pattern).

## Scope — Out
- Bộ nhớ kinh nghiệm/ledger-RAG (E14); reranker/metadata filter (sau).

## Dependencies
E06 (tool boundary), Qdrant (docker).

## Success metrics / Exit
- `rag_health` fail → agent dừng, phân loại dependency failure.
- Re-ingest cùng source thay dữ liệu cũ; search lọc đúng theo threshold.

## Open questions
- Thêm reranker / metadata filter / source line-ranges ở phase sau?
