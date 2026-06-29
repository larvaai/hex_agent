---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 1 — Triage seam (events + contract + agent method + FakeLLM branch)

**Mục tiêu:** dựng seam phân loại tất định trên FakeLLM. Chưa chạm orchestrator.

## Touchpoints

- `drag_from_zero/dragzero/events.py` — thêm 4 `EventType`.
- `drag_from_zero/dragzero/contracts.py` — thêm `TriageResult` dataclass + `from_dict`.
- `drag_from_zero/dragzero/agent.py` — thêm `Agent.triage(raw_input) -> TriageResult`.
- `drag_from_zero/tests/test_triage.py` — MỚI.

## Thiết kế

### EventType mới ([events.py:12](../../drag_from_zero/dragzero/events.py))
```
INPUT_CLASSIFIED  = "input_classified"   # payload {kind: "answer"|"task", reasoning}
ANSWER_PRODUCED   = "answer_produced"    # payload {text}
TASK_BOX_CREATED  = "task_box_created"   # payload {goal, done_when}
TASK_BOX_REJECTED = "task_box_rejected"  # payload {reason, goal}
```

### `TriageResult` ([contracts.py](../../drag_from_zero/dragzero/contracts.py))
```
@dataclass
class TriageResult:
    kind: str                       # "answer" | "task"
    text: Optional[str] = None      # answer branch
    goal: Optional[str] = None      # task branch
    done_when: list = field(default_factory=list)
    reasoning: str = ""
    @classmethod
    def from_dict(cls, d): ...       # tolerant: kind defaults "answer"; missing keys → safe defaults
```
Mẫu theo `DelegationDecision.from_dict` ([contracts.py:74](../../drag_from_zero/dragzero/contracts.py)).

### `Agent.triage` ([agent.py:60](../../drag_from_zero/dragzero/agent.py), cạnh `decompose`)
```
def triage(self, raw_input: str) -> TriageResult:
    ctx = {"agent_id": self.id, "role": self.role,
           "input": raw_input, "request": "triage"}
    resp = self.llm.complete(ctx)
    return TriageResult.from_dict(resp.get("triage") if isinstance(resp, dict) and "triage" in resp else (resp or {}))
```
Branch trên `ctx["request"]` y như `decompose` đã làm ([agent.py:69](../../drag_from_zero/dragzero/agent.py)). KHÔNG validate done_when ở đây — đó là việc CODE ở phase 2 (giữ split: agent propose, code adjudicate).

## Tests Before (đỏ trước)
`tests/test_triage.py`:
1. `test_triage_answer` — FakeLLM responder trả `{"triage":{"kind":"answer","text":"42"}}` → `triage()` cho `TriageResult(kind="answer", text="42")`.
2. `test_triage_task` — trả `{"triage":{"kind":"task","goal":"fix login","done_when":[{...}]}}` → kind=="task", goal set, done_when truyền nguyên.
3. `test_triage_tolerant_default` — resp rỗng `{}` → `kind=="answer"` (fallback an toàn, không crash).
4. `test_triage_missing_keys` — `{"triage":{"kind":"task"}}` (thiếu goal/done_when) → goal=None, done_when=[].

## Implement After
Thêm 4 EventType, `TriageResult`, `Agent.triage`. Không sửa method cũ.

## Tests After / Regression Gate
- `python -m pytest drag_from_zero/tests/test_triage.py -q` → 4 xanh.
- `python -m pytest drag_from_zero -q` → suite cũ xanh nguyên (chỉ thêm test/EventType, không đổi đường cũ).

## Done-when phase
4 test mới xanh; toàn suite xanh; `Agent.triage` trả `TriageResult` đúng cả 2 nhánh; không file cũ nào đổi logic.
