---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 4 — config (lenses.yaml) + adapter `request:"lens"` + determinism

**Mục tiêu:** nối lens với LLM thật + config user-edit; replay tất định bất kể thứ tự lens. Vẫn additive.

## Touchpoints
- `drag_from_zero/dragzero/lens.py` — `load_lenses(dict) -> LensRegistry` (parse catalog/combos/he, validate lúc load).
- `drag_from_zero/dragzero/adapters/llm_local.py` — nhánh `request:"lens"` cho `OpenAICompatLLM` + `RecordedLLM`; `RecordedLLM` thêm chế độ key-by-lens-id.
- `harness/data/lenses.yaml` — MỚI, 1 hệ mẫu **inert**.
- `drag_from_zero/tests/test_lens.py` + `tests/test_slice2_adapter.py` — thêm test.

## Thiết kế

### `load_lenses` (lens.py)
Parse dict (từ YAML/JSON) → LensRegistry. **Validate lúc load** (không lazy runtime): mọi lens id resolve · combo cascade acyclic (đã có ở register_combo) · `he.*.combo` tồn tại · stage.reads ⊆ stage trước. Lỗi → `LensComboError` nêu id sai. Shape khớp [report §2](../reports/brainstorm-260628-0049-multi-lens-advisory-thinking-primitive-report.md):
```
catalog: {risk: {prompt: "..."}, evidence: {prompt: "..."}, synth: {prompt: "..."}}
combos:  {inspect_v1: {stages: [{lens: risk}, {lens: evidence}, {lens: synth, reads: [risk, evidence]}]}}
he:      {thanh_tra: {combo: inspect_v1, enabled: true}}
```

### Adapter `request:"lens"` ([llm_local.py:225](../../drag_from_zero/dragzero/adapters/llm_local.py))
- `OpenAICompatLLM.complete`: khi `ctx["request"]=="lens"` → dựng prompt = lens.prompt + `ctx["input"]` + (nếu cascade) các dòng `ctx["upstream"]` nguyên văn; gọi endpoint; trả **1 dòng đầu non-empty** (lens = prose 1 dòng, KHÔNG cần JSON). Fallback parse hỏng = dòng raw clip. Trả `{"lens": "<line>"}`.
- `RecordedLLM`: thêm chế độ keyed — `RecordedLLM(responses)` (call-order, như cũ) HOẶC `RecordedLLM(by_lens={lens_id: line})`. **[red-team F7] Tie-break rõ:** nhánh `by_lens` CHỈ kích khi `ctx.get("request")=="lens"` VÀ `by_lens` có; mọi call khác (plan/triage/decompose) đi đường `self._i` positional **nguyên vẹn** (llm_local.py:314 không đổi) → test call-order cũ (test_slice2_adapter.py:100,116, đều `lenses=None`) không bị động. Constructor nhận **tối đa 1 mode**; lens ctx khi chỉ có `responses` → tiêu `self._i` như call thường; `by_lens` thiếu lens_id → KeyError loud (không im lặng).

### `harness/data/lenses.yaml`
1 hệ mẫu `thanh_tra`/`inspect_v1` (risk+evidence→synth). **Inert**: không topology/test mặc định tham chiếu → empty-by-default giữ; chỉ là mẫu để user copy.

## Tests Before (đỏ trước)
`tests/test_lens.py`:
1. `test_load_lenses_ok` — load dict mẫu → registry có catalog + combo + hệ; `combo_for_he("thanh_tra")` đúng.
2. `test_load_lenses_invalid` — hệ→combo không tồn tại / lens thiếu / cascade cycle → `LensComboError` lúc LOAD.
3. `test_recorded_lens_by_id` — `RecordedLLM(by_lens={"risk":"r","evidence":"e"})` chạy combo 2 lens → đúng dòng theo lens-id; chạy 2 lần → y hệt.

`tests/test_slice2_adapter.py`:
4. `test_openai_lens_branch` — `OpenAICompatLLM(transport=stub)` ctx request=lens, transport trả prose nhiều dòng → lấy 1 dòng đầu.
5. `test_recorded_lens_cascade_replay` — combo cascade qua RecordedLLM(by_lens) → dòng synth thấy upstream; replay 2 lần bằng nhau.

## Implement After
Thêm `load_lenses` + nhánh adapter lens + `harness/data/lenses.yaml`. Không sửa nhánh `request:"triage"`/`decompose`/plan path cũ (route theo `request`).

## Tests After / Regression Gate
- `python -m pytest drag_from_zero/tests/test_lens.py drag_from_zero/tests/test_slice2_adapter.py -q` → xanh.
- `python -m pytest drag_from_zero -q` → **TOÀN suite xanh** (gồm test_triage/test_decompose/test_disk_truth — nhánh adapter cũ nguyên).

## Done-when phase
5 test xanh; lenses.yaml load+validate; adapter lens parse 1 dòng; RecordedLLM key-by-lens-id replay tất định; suite cũ nguyên. Slice end-to-end: agent hệ X → combo auto + agent thêm lens → tất cả dòng về agent → agent chốt; chạy được trên FakeLLM/Recorded/local.
