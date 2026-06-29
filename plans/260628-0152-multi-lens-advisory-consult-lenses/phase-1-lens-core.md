---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 1 — Lens core (events + lens.py + run_lenses), FakeLLM

**Mục tiêu:** dựng lens-runner thuần tất định trên FakeLLM. Chứng minh no-forge (output không verdict) + cascade-feeds-all-raw. Chưa chạm orchestrator.

## Touchpoints
- `drag_from_zero/dragzero/events.py` — +2 `EventType`.
- `drag_from_zero/dragzero/lens.py` — MỚI.
- `drag_from_zero/dragzero/__init__.py` — export `Lens, ComboSpec, LensRegistry`.
- `drag_from_zero/tests/test_lens.py` — MỚI.

## Thiết kế

### EventType ([events.py:33](../../drag_from_zero/dragzero/events.py))
```
LENS_QUERIED  = "lens_queried"    # payload {lens_id, source: combo|adhoc, reads: [ids]}
LENS_RETURNED = "lens_returned"   # payload {lens_id, line}   ← KHÔNG field verdict (no-forge)
```

### `lens.py`
```
@dataclass(frozen=True)
class Lens:           id: str; prompt: str        # 1 câu hỏi 35B-trivial → 1 dòng

@dataclass(frozen=True)
class ComboStage:     lens: str; reads: tuple = ()  # reads = upstream lens ids (cascade); () = độc lập

@dataclass(frozen=True)
class ComboSpec:      id: str; stages: tuple        # thứ tự stage = list-order; reads chỉ ref stage TRƯỚC

class LensRegistry:                                  # empty-by-default (như ToolRegistry)
    register_lens(Lens); register_combo(ComboSpec); get_lens(id); get_combo(id); lens_names()
    # register_combo VALIDATE acyclic: mọi reads phải là lens xuất hiện ở stage trước (Kahn/back-ref);
    # self-ref / forward-ref / unknown-ref → raise LensComboError NGAY lúc register.

def run_lenses(stages, base_ctx, llm, log, *, agent_id, source) -> list[str]:
    lines = {}                                        # lens_id -> line, theo thứ tự stage
    for st in stages:                                 # stages đã topo-hợp-lệ
        upstream = {r: lines[r] for r in st.reads}    # CODE dựng ctx cascade từ dòng đã có
        ctx = {"agent_id": agent_id, "role": "lens", "request": "lens",
               "lens_id": st.lens, "prompt": <lens.prompt>, "input": base_ctx, "upstream": upstream}
        log.append(Event(LENS_QUERIED, agent_id=agent_id, payload={"lens_id": st.lens, "source": source, "reads": list(st.reads)}))
        resp = llm.complete(ctx)
        line = _one_line(resp)                         # FakeLLM trả {"lens": "<dòng>"} hoặc dict→lấy 'lens'/str
        log.append(Event(LENS_RETURNED, agent_id=agent_id, payload={"lens_id": st.lens, "line": line}))
        lines[st.lens] = line
    return list(lines.values())                        # TẤT CẢ dòng (raw + tổng-hợp), thứ tự stage
```
Lens-runner **không cầm ToolRegistry** → lens không thể dispatch tool/consult (structural, Luật 2). `_one_line` chỉ lấy text 1 dòng; KHÔNG parse field verdict — output luôn là dòng thường.

## Tests Before (đỏ trước) — `tests/test_lens.py`
1. `test_registry_resolve` — register 2 lens + 1 combo → `get_combo` trả stages đúng; `get_lens` unknown → None.
2. `test_run_lenses_independent` — combo 2 lens độc lập, FakeLLM responder theo `ctx["lens_id"]` → 2 dòng; log có 2 LENS_QUERIED + 2 LENS_RETURNED.
3. `test_run_lenses_cascade` — combo A,B→C(reads A,B); responder kiểm `ctx["upstream"]` chứa dòng A,B; trả 3 dòng (A,B AND C); thứ tự: C sau A,B.
4. `test_lens_output_no_verdict` (LUẬT 1) — LENS_RETURNED payload chỉ `{lens_id, line}`; assert không key nào trong `{verdict,route,mode,passed,status,score}`.
5. `test_cascade_acyclic` — `register_combo` với stage C reads C (self) HOẶC reads lens ở stage SAU → `LensComboError` ngay lúc register.

> **[red-team F4]** FakeLLM responder trong các test này phải branch `ctx.get("request")=="lens"` TRƯỚC khi chạm key khác (lens ctx không có `observations`). `_one_line` chấp nhận `{"lens": str}` hoặc `str`.
> **[red-team F8]** LENS_QUERIED/RETURNED cố ý KHÔNG vào `reduce()` (read_model.py:80) — bảo vệ L1 (dòng lens không thành node verdict). Test assert trên `log.of_type(LENS_RETURNED)`, KHÔNG trên cây reduce.

## Implement After
Thêm 2 EventType + `lens.py` + export. Không sửa method cũ.

## Tests After / Regression Gate
- `python -m pytest drag_from_zero/tests/test_lens.py -q` → 5 xanh.
- `python -m pytest drag_from_zero -q` → suite cũ xanh nguyên (chỉ thêm EventType + module mới, 0 đường cũ chạm).

## Done-when phase
5 test xanh; `run_lenses` trả TẤT CẢ dòng (raw+cascade); LENS_RETURNED không verdict; combo cycle reject lúc build; lens-runner không truy cập tool; toàn suite xanh.
