---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 1 — Skeleton + Node/tree loader + lifted utilities (no LLM)

**Mục tiêu:** Dựng bộ khung `decompose_agent/` + record bất biến (node không thể sai cấu trúc) + ba tiện ích nền lift từ hex_agent (JSON repair, budget). KHÔNG LLM, KHÔNG gate logic.

**Files:** `decompose_agent/__init__.py`, `node.py`, `tree.py`, `json_repair.py`, `budget.py`, `tests/conftest.py`, `tests/fixtures/rag_tree.yaml`.

## Tests Before (đỏ)
- `tests/test_node.py`:
  - `Node` từ dict hợp lệ dựng được; `as_dict` round-trip.
  - `__post_init__` REJECT khi done_when criterion có key `verdict`/`passed`/`status`/`score` → ValueError nêu field (bài học no-verdict-field, lift `control/events.py:134-151`).
  - REJECT criterion không phải triple `{check, params, artifact}` (thiếu `check` hoặc `artifact`).
  - REJECT `artifact` path không an toàn (`..`, abs) — path-jail tại construction.
  - `status` chỉ nhận `pending|active|decomposed|done|blocked`; giá trị khác → ValueError.
- `tests/test_tree.py`:
  - Load `fixtures/rag_tree.yaml` OK; `next_node()` trả leftmost `pending` có mọi `depends_on` đã `done`, sort theo `(depth, order)`.
  - REJECT `depends_on` trỏ id không tồn tại (referential integrity) → ValueError nêu node+dep.
  - REJECT cycle trong `depends_on` at load (topo-sort fail) → ValueError.
- `tests/test_json_repair.py` (property + ví dụ):
  - JSON hợp lệ → candidate #1 (raw) thắng, KHÔNG bị mutate.
  - Hỏng phổ biến phục hồi được: fenced ```json, prose-wrapped, `True/False/None`, unquoted keys, single-quote dict, truncation cuối.
  - `normalize_action`: params phẳng ở top-level → gom vào `args`; tool-name-as-verb; args-as-string → parse. Coercion set NHỎ, chỉ các breakage này.
  - `build_retry_message(call_type)` nhúng skeleton literal theo `propose` vs `decompose`, KHÔNG re-dump context.
  - Total over bytes: fuzz chuỗi tùy ý KHÔNG raise (mỗi rung nuốt exception của chính nó).
- `tests/test_budget.py`:
  - step budget tăng theo `record_step`, `step_exceeded` tại `max_steps`.
  - parse-error budget gate trên **streak liên tiếp**: `record_step`/good-parse reset streak; `parse_exceeded` chỉ true khi `consecutive >= max_parse` (lift `discipline/budget.py:11-54`, trùng memory local-model-quirks).
  - parse error KHÔNG advance step budget.
  - K attempt budget per-node độc lập step budget.

## Implement
- `node.py`: `@dataclass(frozen=True) Node` (id, parent, kind∈{work}, status, order, depends_on, done_when, attempts, max_attempts/K, depth, notes, activated_at). `DoneWhen` frozen `{check:str, params:dict, artifact:str}`; `__post_init__` enforce no-verdict-field + triple shape + safe artifact (reuse path-jail helper). `FORBIDDEN_VERDICT_KEYS = {"verdict","passed","status","score","done"}`.
- `tree.py`: `load_tree(path)→Tree` (yaml.safe_load, build id→Node, validate referential integrity + acyclic via topo-sort, path-jail every artifact). `Tree.next_node()` cursor.
- `json_repair.py`: port `_candidates`/`light_json_repair`/`_load_object` (raw-first, dedup, json.loads→ast.literal_eval) + `normalize_action` + `build_retry_message`. Adapt: hai call type (`propose`→action, `decompose`→children list).
- `budget.py`: `RootBudget(max_steps)` + `ParseBudget(max_parse, consecutive)` + per-node `attempts/K`. `tool_key`-style canonical key NOT needed yet.
- `fixtures/rag_tree.yaml`: cây RAG 2-tầng hand-baked theo `spec.md:253-315` (ai.rag + 4 leaf + sẽ thêm _reduce ở round sau — round này bỏ _reduce, parent done_when = `all_children_done`).

## Tests After
`python -m pytest decompose_agent/tests/test_node.py decompose_agent/tests/test_tree.py decompose_agent/tests/test_json_repair.py decompose_agent/tests/test_budget.py -q` → xanh.

## Regression Gate
Package mới, không file cũ bị đụng. `python -m pytest -q` (repo) vẫn xanh (sanity: import decompose_agent không vỡ collection).
