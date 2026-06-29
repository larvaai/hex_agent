---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 3 — Projection (inbox view) + real/recorded adapter triage branch

**Mục tiêu:** fold 4 event mới thành view đọc được; nối nhánh `request:"triage"` cho adapter thật. Vẫn additive.

## Touchpoints

- `drag_from_zero/dragzero/read_model.py` — thêm `reduce_inbox(events)`. KHÔNG sửa `reduce` ([read_model.py:30](../../drag_from_zero/dragzero/read_model.py)).
- `drag_from_zero/dragzero/adapters/llm_local.py` — thêm nhánh triage (OpenAICompatLLM + RecordedLLM dùng chung parse/repair ladder).
- `drag_from_zero/tests/test_triage.py` — thêm test projection.
- `drag_from_zero/tests/test_slice2_adapter.py` — thêm test adapter triage (cùng file slice-2 vì cùng adapter).

## Thiết kế

### `reduce_inbox` ([read_model.py](../../drag_from_zero/dragzero/read_model.py)) — projection riêng, KHÔNG đụng cây
```
@dataclass
class TaskBox:
    goal: Optional[str]
    done_when: list = field(default_factory=list)
    status: str = "materialized"   # "materialized" | "rejected"; "unverified" nếu done_when==[]
    reason: Optional[str] = None   # rejected branch

def reduce_inbox(events) -> dict:
    answers, boxes = [], []
    for e in events:
        if e.type == EventType.ANSWER_PRODUCED:
            answers.append(e.payload.get("text", ""))
        elif e.type == EventType.TASK_BOX_CREATED:
            dw = list(e.payload.get("done_when") or [])
            boxes.append(TaskBox(e.payload.get("goal"), dw,
                                 status="unverified" if not dw else "materialized"))
        elif e.type == EventType.TASK_BOX_REJECTED:
            boxes.append(TaskBox(e.payload.get("goal"), status="rejected", reason=e.payload.get("reason")))
    return {"answers": answers, "task_boxes": boxes}
```
Pure fold y như `reduce`: cùng event → cùng view.

### Adapter triage branch ([llm_local.py](../../drag_from_zero/dragzero/adapters/llm_local.py))
- `OpenAICompatLLM.complete`: khi `ctx.get("request") == "triage"`, dựng prompt triage (phân loại + nếu task thì đề xuất goal + done_when typed-triple `{check, params, artifact}`), gọi endpoint, chạy **đúng parse/repair ladder hiện có**, trả `{"triage": {...}}`. Fallback an toàn khi parse hỏng = `{"triage": {"kind": "answer", "text": <raw>}}` (quan sát qua `_meta`, không crash) — khớp pattern fallback `solo` đã có ([README slice 2](../../drag_from_zero/README.md)).
- `RecordedLLM`: replay canned reply qua *cùng* path → triage tất định không cần weights.

## Tests Before (đỏ trước)
`tests/test_triage.py`:
1. `test_inbox_projection_answers` — log có 2 `ANSWER_PRODUCED` → `reduce_inbox` cho `answers` đúng 2 phần tử.
2. `test_inbox_projection_task_box` — 1 `TASK_BOX_CREATED{goal,done_when}` → 1 `TaskBox(status="materialized")`.
3. `test_inbox_empty_done_when_unverified` — done_when=[] → `status=="unverified"`.
4. `test_inbox_rejected` — `TASK_BOX_REJECTED` → `TaskBox(status="rejected", reason set)`.
5. `test_inbox_pure_fold` — fold cùng events 2 lần → kết quả bằng nhau (purity).

`tests/test_slice2_adapter.py`:
6. `test_recorded_triage_answer` — RecordedLLM canned answer reply → `complete(ctx{request:triage})` cho `{"triage":{"kind":"answer",...}}`.
7. `test_recorded_triage_task_parse` — canned task reply (JSON fenced) → parse ra goal + done_when typed-triple.
8. `test_triage_parse_repair` — reply prose-lẫn-JSON hỏng → repair ladder cứu hoặc fallback answer, KHÔNG raise.

## Implement After
Thêm `reduce_inbox` + `TaskBox` vào read_model; thêm nhánh triage vào adapter. Không sửa `reduce`/`OpenAICompatLLM` path cũ (route theo `request`).

## Tests After / Regression Gate
- `python -m pytest drag_from_zero/tests/test_triage.py drag_from_zero/tests/test_slice2_adapter.py -q` → xanh.
- `python -m pytest drag_from_zero -q` → **toàn suite xanh** (gồm `tests/unit/test_read_model.py` không đổi — `reduce` nguyên vẹn).

## Done-when phase
8 test mới xanh; `reduce_inbox` pure; adapter triage parse + repair + fallback có test; suite cũ nguyên. Slice end-to-end: `submit("câu hỏi")` → answer; `submit("task có tiêu chí")` → task box; projection đọc được cả hai.
