# E12 — Intent Router & Global Supervisor (PRD, draft)

Phase: P4 · Features: F18

> Lưu ý quan hệ với E10 (v2): E10 nay là **engine TaskLoop động** (Agent O compose team + scoped
> context + AC gate). E12 **không** tự điều phối hội thoại — nó chỉ *phân loại intent* rồi *chọn
> department/workflow template* và giao task cho một TaskLoop của E10. Hai tầng supervisor khác
> nhau: E12 = dispatcher toàn cục (chọn ai làm), E10/Agent O = orchestrator trong một task (làm thế nào).

## Problem
Đa nhiệm: nhiều loại task (hỏi đáp, repo Q&A, code, research, product build). Cần **một router** chọn đúng department/workflow, không hardcode một pipeline.

## Goal
`IntentRouter.classify()` → `RouteDecision`; `GlobalSupervisor.run()` chạy safety gate → chọn department/workflow template → khởi tạo **một TaskLoop (E10)** → final synthesis. Rule-based nhanh + **fallback LLM khi confidence thấp**.

## Scope — In
- `classify(request)` → `{intent, confidence, needs_repo/code/web/memory, execution_mode, steps}`.
- Dispatch: chọn department/workflow template (E11) rồi giao cho **TaskLoop của E10**; mixed → kế hoạch nhiều bước (nhiều TaskLoop).
- Safety gate (E11) trước khi chạy; FinalSynthesis gộp outputs + citations + validation.
- Confidence chuẩn hóa; thấp → hỏi LLM phân loại.

## Scope — Out
- Bản thân các graph/department (E10/E11/E13).

## Dependencies
E10, E11, E13.

## Success metrics / Exit
- Route đúng loại cho tập prompt mẫu; mixed → kế hoạch nhiều bước.
- Confidence thấp → LLM fallback thay vì đoán bừa.

## Open questions
- Hiệu chỉnh confidence thế nào (đừng dùng hằng số cứng như repo cũ)?
