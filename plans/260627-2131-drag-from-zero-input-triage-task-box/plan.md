---
title: "drag_from_zero re-build slice 1 — input triage + task-box materialization (worker phân loại hỏi-vs-task)"
slug: drag-from-zero-input-triage-task-box
status: approved   # human-approved 2026-06-27 by uspro
mode: hard
tdd: true
created: 2026-06-27 21:31
owner: uspro
source_report: plans/reports/brainstorm-260627-2131-drag-from-zero-rebuild-from-user-report.md
project: drag_from_zero/dragzero (additive; touches no existing execution path)
phases: 3
depends_on: []
risk: low — additive new entrypoint + new event types; existing start()/run()/_solve_gated untouched → all current suites pass byte-identical
standards:
  - drag_from_zero/README.md   # quy ước drag_from_zero: event-log-là-truth, port qua Protocol, empty-by-default, additive
  - docs/code-standards.md      # §3 naming, §4 TDD, §5 add-file traceability ONLY (KHÔNG áp §1 microkernel — drag_from_zero là kiến trúc divergent)
decisions:
  - DEC-16 — supervisor LLM là trọng tài verdict tối cao, phán trên artifact thật + code gate; context tách rời worker, cùng 35B (docs/decisions.md)
  - SLICE-D1 — slice này DỪNG ở materialize: task → emit TASK_BOX_CREATED rồi dừng, KHÔNG gọi _solve_gated/verify/decompose (user chốt 2026-06-27)
  - SLICE-D2 — worker PROPOSE done_when; CODE validate qua build_done_when (forgery/path-jail → TASK_BOX_REJECTED). Luật "worker không forge verdict" giữ nguyên
  - SLICE-D3 — UI defer: chỉ event + projection (read-model), KHÔNG sửa ui/Agent IDE.dc.html (user chốt 2026-06-27)
phases_list:
  - phase-1-triage-seam.md
  - phase-2-orchestrator-submit.md
  - phase-3-projection-and-adapter.md
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Plan — drag_from_zero re-build slice 1: input triage + task-box

> hs:cook đọc file này làm hợp đồng. Claim không hiển nhiên có anchor `file:line`; tag `[UNVERIFIED]` nếu thiếu.
> Additive: KHÔNG sửa `start()` / `run()` / `_solve_gated`. Test cũ phải xanh nguyên.

## Vì sao plan này

Bản re-build bắt đầu từ **điểm vào của user** ([report](../reports/brainstorm-260627-2131-drag-from-zero-rebuild-from-user-report.md)): màn hình mở ra là **1 worker mặc định**, user gõ input, worker **tự phân loại** — câu hỏi thường thì nhả text xong; phát hiện là task thì đính một **ô vuông task** = `{mục tiêu, tiêu chí done}`. Đây là slice nhỏ nhất chạm đúng điểm vào đó. Supervisor, decompose/DAG, đổi-vai-code-gate là slice sau (deferred).

Hiện tại `drag_from_zero` không có bước phân loại: input vào `start(description, agent, done_when)` — `done_when` do **author** truyền vào ([orchestrator.py:137](../../drag_from_zero/dragzero/orchestrator.py)), không phải worker đề xuất; và mọi input đều bị coi là task. Slice này thêm **một entrypoint mới** đứng trước: worker đọc input thô, phân loại, và (nếu task) tự đề xuất ô vuông.

## Kiến trúc slice (theo quy ước drag_from_zero, không áp microkernel cũ)

```
raw_input
   │
   ▼
Orchestrator.submit(raw_input)          ← entrypoint MỚI (start()/run() không đổi)
   │  route → entry worker (roster.first / rules.route)
   ▼
Agent.triage(raw_input) -> TriageResult ← seam MỚI; llm.complete(ctx{request:"triage"})
   │
   ├── kind == "answer" → emit INPUT_CLASSIFIED(answer) + ANSWER_PRODUCED{text}  → DỪNG
   │
   └── kind == "task"   → build_done_when(proposed)   ← CODE validate (Gate giữ luật)
            ├── hợp lệ  → emit INPUT_CLASSIFIED(task) + TASK_BOX_CREATED{goal, done_when} → DỪNG (SLICE-D1)
            └── forged  → emit INPUT_CLASSIFIED(task) + TASK_BOX_REJECTED{reason}        → DỪNG
```

Event log vẫn là nguồn sự thật duy nhất. Projection (`read_model`) fold 4 event mới thành view `{answers, task_boxes}` cho test/UI-sau đọc.

## Luật phải giữ (đừng phá)

1. **Worker không forge verdict.** done_when worker đề xuất đi qua `build_done_when` ([verifier.py](../../drag_from_zero/dragzero/verifier.py)) — key dạng verdict (`passed`/`status`/`score`/…) hoặc path-escape bị reject ngay khi dựng → `TASK_BOX_REJECTED`, không bao giờ thành ô vuông hợp lệ. (SLICE-D2)
2. **Additive.** Không một event mới nào xuất hiện trên đường `start()`/`run()` cũ. Một run cũ phải cho event stream y hệt. Kiểm: chạy lại toàn bộ `tests/` hiện có, không sửa.
3. **Slice dừng ở materialize.** Nhánh task KHÔNG gọi `_solve_gated` → không có `LEAF_VERIFIED`/`DECOMPOSITION_*` event trong slice này. (SLICE-D1)

## Rủi ro đã biết (deferred, KHÔNG sửa slice này)

- **Worker khai man "đây là câu hỏi" để né gate.** Không có supervisor kiểm tra phân loại ở slice này → nhận classification của worker ở mức face-value. Đây chính là việc supervisor (DEC-16) sẽ soát ở slice sau. Ghi nhận, không vá.
- **done_when "rỗng nhưng hợp lệ".** Worker đề xuất task nhưng `done_when=[]`. Quyết định: ô vuông với done_when rỗng = `unverified` (cho phép tạo, projection đánh dấu) — KHÔNG reject. Khớp luật hiện tại "node không có criteria là unverified, không phải faked pass".

## Acceptance (toàn slice)

- Input câu-hỏi → log có `INPUT_CLASSIFIED(answer)` + `ANSWER_PRODUCED{text}`, KHÔNG có `TASK_BOX_CREATED`.
- Input task → log có `INPUT_CLASSIFIED(task)` + `TASK_BOX_CREATED{goal, done_when}`, KHÔNG có `LEAF_VERIFIED` (chứng minh không chạy).
- Input task với done_when forged (verdict key) → `TASK_BOX_REJECTED`, KHÔNG có `TASK_BOX_CREATED`.
- Projection `reduce(events)` lộ ra `{answers:[…], task_boxes:[{goal, done_when, status}]}`.
- Real/Recorded adapter có nhánh `request:"triage"` parse được qua repair ladder; RecordedLLM replay tất định.
- **Toàn bộ suite cũ xanh nguyên** (`python -m pytest drag_from_zero -q`), 0 thay đổi file test cũ.

## Rollback

Xóa entrypoint `submit` + 4 EventType mới + `TriageResult` + nhánh triage trong adapter + test mới. Không file cũ nào bị sửa logic ⇒ revert = drop các hunk additive.

## Phases

1. [phase-1-triage-seam.md](phase-1-triage-seam.md) — EventType mới + `TriageResult` contract + `Agent.triage` + FakeLLM triage branch.
2. [phase-2-orchestrator-submit.md](phase-2-orchestrator-submit.md) — `Orchestrator.submit` + done_when validation + 4 event, law-preserving. Tim của slice.
3. [phase-3-projection-and-adapter.md](phase-3-projection-and-adapter.md) — projection fold trong read_model + nhánh triage cho OpenAICompatLLM/RecordedLLM.

## Câu hỏi mở

- Tên event: `TASK_BOX_CREATED` vs `TASK_DETECTED` — chốt ở phase 1, thêm vào GLOSSARY.
- `submit` trả gì cho caller (TriageResult? task_id? None)? Đề xuất: trả `TriageResult` để caller/test đọc thẳng; event log vẫn là truth.
