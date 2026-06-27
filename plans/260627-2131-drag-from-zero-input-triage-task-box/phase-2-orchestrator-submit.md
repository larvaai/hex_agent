---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 2 — Orchestrator.submit + done_when validation (tim của slice)

**Mục tiêu:** entrypoint mới `submit(raw_input)` chạy triage → emit 4 event → DỪNG. Giữ trọn 3 luật.

## Touchpoints

- `drag_from_zero/dragzero/orchestrator.py` — thêm method `submit`. KHÔNG sửa `start`/`run`/`run_until_idle`/`_solve_gated`.
- `drag_from_zero/tests/test_triage.py` — thêm test orchestrator-level.

## Thiết kế

### `Orchestrator.submit` ([orchestrator.py:136](../../drag_from_zero/dragzero/orchestrator.py), cạnh `start`)
```
def submit(self, raw_input: str, agent: Optional[Agent] = None) -> TriageResult:
    worker = agent or self._route(Task(id="_triage", description=raw_input))  # entry worker
    if worker is None:
        self.log.append(Event(EventType.TASK_FAILED, payload={"error": "no agent available"}))
        return TriageResult(kind="answer", text="")
    result = worker.triage(raw_input)
    self.log.append(Event(EventType.INPUT_CLASSIFIED, agent_id=worker.id,
                          payload={"kind": result.kind, "reasoning": result.reasoning}))
    if result.kind == "task":
        self._materialize_task_box(worker, result)
    else:
        self.log.append(Event(EventType.ANSWER_PRODUCED, agent_id=worker.id,
                              payload={"text": result.text or ""}))
    return result
```

### `_materialize_task_box` — CODE adjudicate done_when (SLICE-D2)
```
def _materialize_task_box(self, worker, result):
    raw = list(result.done_when or [])
    if raw:                                   # rỗng = unverified, cho phép (xem plan §rủi ro)
        try:
            build_done_when(raw)              # forgery/path-jail reject ở đây
        except ValueError as exc:
            self.log.append(Event(EventType.TASK_BOX_REJECTED, agent_id=worker.id,
                                  payload={"reason": str(exc), "goal": result.goal}))
            return
    self.log.append(Event(EventType.TASK_BOX_CREATED, agent_id=worker.id,
                          payload={"goal": result.goal, "done_when": raw}))
    # SLICE-D1: DỪNG. KHÔNG enqueue, KHÔNG _solve_gated.
```
`build_done_when` đã import sẵn ([orchestrator.py:27](../../drag_from_zero/dragzero/orchestrator.py)).

## Tests Before (đỏ trước)
Thêm vào `tests/test_triage.py` (FakeLLM scripted):
1. `test_submit_answer_path` — input câu hỏi → log chứa `INPUT_CLASSIFIED(kind=answer)` + `ANSWER_PRODUCED`, KHÔNG có `TASK_BOX_CREATED`.
2. `test_submit_task_materializes_box` — input task, done_when hợp lệ → `INPUT_CLASSIFIED(kind=task)` + `TASK_BOX_CREATED{goal, done_when}`.
3. `test_submit_task_does_not_execute` (LUẬT 3) — sau submit task, log KHÔNG chứa `LEAF_VERIFIED` / `SUBTASK_SPAWNED` / `DECOMPOSITION_PROPOSED`. Chứng minh dừng ở materialize.
4. `test_submit_forged_done_when_rejected` (LUẬT 1) — worker đề xuất done_when có key `passed` → `TASK_BOX_REJECTED`, KHÔNG có `TASK_BOX_CREATED`.
5. `test_submit_empty_done_when_allowed` — task với `done_when=[]` → `TASK_BOX_CREATED` (status unverified), không reject.
6. `test_submit_no_agent` — roster rỗng → `TASK_FAILED{no agent available}`, không crash.

## Implement After
Thêm `submit` + `_materialize_task_box`. Import `TriageResult` từ contracts.

## Tests After / Regression Gate (LUẬT 2 — additive)
- `python -m pytest drag_from_zero/tests/test_triage.py -q` → tất cả xanh.
- `python -m pytest drag_from_zero -q` → **toàn suite cũ xanh nguyên, 0 file test cũ sửa**. Đây là gate chứng minh `start()`/`run()` không đổi hành vi.

## Done-when phase
6 test mới xanh; luật 1 (forgery→reject), luật 3 (task không execute) có test riêng đỏ-rồi-xanh; suite cũ nguyên vẹn.
