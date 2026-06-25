# E14 — Ledger & Memory · `park-with-trigger`

> Living note (roadmap "kho lạnh có nhãn-ngưỡng"). Nguồn: report `roadmap-living-notes` §E14 (bám code thật). Đọc cùng [README.md](../README.md) + [dependency-map.md](../dependency-map.md). `deps 🟢` = *được phép* ≠ *nên*.

## 1. problem_solved
1 lớp lưu bền vững xuyên-run cho (1) "work ledger" truy-vấn-được (agent đã làm gì qua các run) thay cho đống file rời `var/agent_runs/<run_id>/`; (2) "long-term memory" để agent recall run TRƯỚC khi xử task MỚI (episodic, khác KB tĩnh E08). Cho resume/audit cross-run, dedup việc lặp, để E12 quyết dựa lịch sử.

## 2. why_not_now
Chưa có consumer đọc lịch sử cross-run. Resume/recall đang CỐ Ý tắt: `orchestrator/checkpoint.py:26` ("not used to resume a graph"), `:139` ("Resume intentionally does not call this"). SQLite truth per-run (`:31-32`). Index toàn cục `observability/event_log.py:95-98` chỉ ghi `{run_id, status}`. RAG = KB tĩnh: collection cố định "agent_kb" (`rag/ports.py:42`), default backend "memory" reset mỗi process (`rag/stores.py:30`, `rag/feature.py:32`). Consumer tự nhiên (E12) chưa bắt đầu.

## 3. current_anchors (verbatim)
- `orchestrator/checkpoint.py:31-32,26,139` — per-run, recall tắt.
- `observability/event_log.py:95-98` — index chỉ status.
- `rag/ports.py:42` — agent_kb tĩnh · `rag/stores.py:30` — ephemeral.
- grep "ledger|episodic|cross-run" non-test = **0**.

## 4. wiring_threshold (đo được)
- (a) E12 in-progress VÀ logic route cần đọc ≥1 run trước.
- (b) run trong `var/agent_runs/` >500 + nhu cầu "agent đã làm task X chưa?" — đếm: `ls var/agent_runs/ 2>/dev/null | wc -l` (nay **0**).
- (c) ≥1 call-site `load_checkpoint()` để RESUME (nay **0**, `checkpoint.py:139`) — đếm: `grep -rn 'load_checkpoint(' --include=*.py | grep -v def`.
- (d) yêu cầu "nhớ giữa phiên".
Tóm: consumer-cross-run >0 HOẶC run >500 HOẶC resume-call-site >0.

## 5. wiring_sketch (seam file:line)
1. **ledger ghi** — bám `attach_to_bus()` (`observability/event_log.py:102`) thêm subscriber ghi SQLite global (`runs_dir()/ledger.sqlite`), tái dùng `open_checkpointer` pattern.
2. **memory đọc** — mở rộng `VectorStorePort` (`rag/ports.py:31-36`) namespace per-agent, write-back sau `finish()` (`event_log.py:80`).
3. `LedgerPort`/`MemoryPort` cho graph node query trước khi xử task. Port-first. Altitude rẻ nhất: chỉ **B1** — đổi index.jsonl → SQLite global query-được (1 ngày, không phải epic).

## 6. dependencies (cổng)
Gate-in 🟢 E06/E08 done · gate-out 🔴 chờ E12. Không trên critical path; chạm ngưỡng SAU khi E12 sinh workload. Tách trục với E15: governance-evidence per-AC (E15/E21) ≠ cross-run work-ledger (E14) — đừng để E15 score ghi vào ledger E14 trước khi E14 tồn tại.

## 7. critique (YAGNI · risks-built · risks-skipped)
YAGNI ở quy mô hiện tại. 80% giá trị "ledger" đã có qua `var/agent_runs/<run_id>/` + CLI `inspect.py`; "memory" tĩnh đã có qua RAG. Rẻ hơn (90% mục tiêu): chỉ làm **B1** SQLite global query-được.
- **Build sớm** = lock-in schema sai + 3 nguồn truth lệch (langgraph.sqlite + taskloop.sqlite + ledger.sqlite).
- **Bỏ hẳn** = agent vô-trí-nhớ cross-run, chặn trần năng lực "multi-agent durable".

## 8. verdict
`park-with-trigger`. Tầng rã đông: **4** — B1 (index.jsonl → SQLite global), kích khi E12 sinh workload hoặc run >500.
