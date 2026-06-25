# E03 — LLM Adapter (PRD, draft)

Phase: P0 · Features: F05 (kết hợp E02)

## Problem
Repo cũ: client OpenAI **khởi tạo lúc import** (kẹt proxy, khó test) và **không bật JSON-mode** → model hỏng JSON 33% ở bước final.

## Goal
Một adapter OpenAI-compatible: **JSON-mode/grammar**, **lazy-init**, timeout, retry, model override — là tuyến phòng thủ đầu cho output discipline.

## Scope — In
- `call_llm(messages, *, model=None, temperature=0.2, response_format=...)`.
- Lazy client (tạo lần gọi đầu, không phải lúc import).
- `response_format={"type":"json_object"}` hoặc nạp GBNF grammar khi backend hỗ trợ.
- Env: `LLM_BASE_URL/API_KEY/MODEL/TIMEOUT/MAX_TOKENS`; lỗi LLM → message có cấu trúc.

## Scope — Out
- Repair/parse (E02).

## Dependencies
Không cứng. Dùng bởi E02/E05/E10.

## Success metrics / Exit
- Bật JSON-mode → tỉ lệ JSON invalid ở bước tool ≈ 0; bước final giảm mạnh.
- `import llm` KHÔNG tạo kết nối/clien​t (lazy verified).
- Timeout & retry hoạt động; đổi model qua tham số/env.

## Open questions
- json_object vs grammar tùy backend (LM Studio hỗ trợ cả hai?) — chọn theo model.
