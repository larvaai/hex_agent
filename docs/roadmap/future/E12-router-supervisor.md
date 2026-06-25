# E12 — IntentRouter / GlobalSupervisor · `park-with-trigger`

> Living note (roadmap "kho lạnh có nhãn-ngưỡng"). Nguồn: report `roadmap-living-notes` §E12 (bám code thật). Đọc cùng [README.md](../README.md) + [dependency-map.md](../dependency-map.md). PRD gốc giữ nguyên ở §"Spec gốc (PRD draft)" bên dưới.
>
> ⚠ `supervisor/` HIỆN TẠI là **E10** (TaskLoop, Agent O), KHÔNG phải E12.

## 1. problem_solved
Dispatcher toàn cục cho nhiều LOẠI request: `classify(request) → RouteDecision → safety gate → chọn template (E11) → giao 1 task cho TaskLoop E10` (`supervisor/loop.py:70`); request "mixed" → plan nhiều bước. Tách vai rõ với Agent O: **E12 quyết "ai làm", O quyết "làm thế nào"**. Entrypoint thôi giả định mọi prompt cùng loại.

## 2. why_not_now
Cổng 🔴 chặn cứng bởi E11 ⬜ + E13 ⬜ (`../dependency-map.md`, `PRD.md` mục Dependencies). E12 là vỏ "chọn rồi giao": cần tập template (E11 chưa có) + spec→handoff (E13 chưa có). Với 4 role / 2 dept / 1 entrypoint, một if/heuristic 5 dòng còn rẻ hơn IntentRouter có confidence + LLM fallback.

## 3. current_anchors (verbatim)
- `roles/spec.py:45` — `department` parse-rồi-bỏ.
- `roles/spec.py:49` — `may_route_to` khai báo nhưng chưa engine đọc.
- `supervisor/loop.py:70` — `run_task_loop`, seam E12 sẽ gọi, chưa ai gọi từ tầng trên.
- KHÔNG có symbol intent/router/classify/RouteDecision nào trong app.

## 4. wiring_threshold (đồng thời)
1. E11 ship — ≥2 template chọn-được-bằng-code (nay **0**).
2. ≥3 loại task phân biệt ở `ui/server.py`.
3. ≥1 request "mixed" cần ≥2 TaskLoop (cần E13).
Phụ: >8 role qua ≥4 dept khiến bảng route phẳng sai-route đủ thường.

## 5. wiring_sketch (seam file:line)
Package mới `router/` (KHÔNG động supervisor/): `IntentRouter.classify → RouteDecision` rule-based + LLM fallback khi confidence thấp; `GlobalSupervisor.run` chạy safety gate → đọc `department`+`may_route_to` chọn template → gọi `run_task_loop` (`supervisor/loop.py:70`). Đấu vào `ui/server.py` (~238/271). Emit RouteDecision qua `control/emitter.py:53` cho Control Tower E21.

## 6. dependencies (cổng)
Gate-in 🔴 chờ E11 + E13 (điểm hội tụ, cuối critical path `E10→E13→E12`). **Ranh giới E12↔E13**: *multi-step trong-1-task = E13 · dispatch nhiều-task = E12*.

## 7. critique (YAGNI · risks-built · risks-skipped)
Dạng đầy đủ PRD = over-design. Cần sớm chỉ là seam "một-cửa nhận request" trong GlobalSupervisor; hoãn confidence calibration tới khi có dữ liệu route-sai.
- **Build sớm** khi E11 chưa có template = route vào hư-không, mock đông cứng thành interface sai.
- **Bỏ hẳn** = khoá vào 1 loại task, `may_route_to` chết vĩnh viễn.

## 8. verdict
`park-with-trigger`. Tầng rã đông: **3 (hội tụ)** — GlobalSupervisor rule-based khi đồng thời E11 có ≥2 template + ≥3 loại task + ≥1 mixed. Hoãn IntentRouter+LLM tới khi có dữ liệu route-sai.

---

## Spec gốc (PRD draft)

### E12 — Intent Router & Global Supervisor (PRD, draft)

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
