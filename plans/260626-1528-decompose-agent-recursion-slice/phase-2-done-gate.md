---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 2 — Gate-1 done-gate runner (no LLM)

**Mục tiêu:** Code là trọng tài PASS/FAIL DUY NHẤT. CHECK_VOCAB đóng + `run_checks` ghi verdict + artifact assertion (exists/non-empty/jail/fresh) chạy TRƯỚC predicate. Vẫn KHÔNG LLM.

**Files:** `decompose_agent/gates.py`, `tests/test_gates.py`, fixtures artifact tạm.

## Tests Before (đỏ)
- Vocabulary đóng: `check` không thuộc CHECK_VOCAB → verdict FAIL/error "unknown check '<k>'", KHÔNG raise (anti-gaming: prose không có check key).
- Artifact assertion chạy TRƯỚC predicate:
  - File thiếu → FAIL.
  - File rỗng (size 0) → FAIL `file_exists` (empty = fail, `spec.md:96`).
  - Artifact `mtime < node.activated_at` → auto-FAIL "stale" (đóng đường resume+re-run gaming, `spec.md:48`).
  - Artifact path ngoài jail → FAIL "unsafe".
- Per-check PASS/FAIL đúng (mỗi check một test, dùng artifact tạm trong tmp_path):
  - `file_exists`, `file_nonempty_lines(min)`, `json_field_equals(ptr,value)`, `json_field_in_range(ptr,min,max)` (metric gate), `json_field_exists(ptr)`, `json_len_gte(ptr,n)`, `row_count_gte(n)`, `grep_matches(pattern,min)`, `grep_absent(pattern)`, `all_children_done`.
  - `json_field_in_range` biên: =min PASS, <min FAIL, >max FAIL.
- Node DONE iff MỌI criterion PASS (AND, no partial credit): 1 FAIL → node_verdict FAIL.
- Verdict object CHỈ do code ghi: `run_checks` trả frozen `Verdict{node, results:[{check, ok, artifact, reason}], node_verdict}`; không có đường nào để caller/worker set ok.
- `all_children_done`: PASS iff `len(children)≥1` ∧ mọi child `status==done`; mixed → FAIL; **0 children → FAIL** (F1: `all([])` là True trong Python → phải chặn rỗng tường minh, nếu không một node `decomposed` chưa gắn con sẽ vacuous-done).

## Implement
- `gates.py`: `CHECK_VOCAB: dict[str, Callable]` — mỗi check là pure `(params, artifact_path) → CheckResult(ok, reason)`. `run_checks(node, workspace) → Verdict`:
  1. cho mỗi criterion: resolve artifact path under jail; assert exists ∧ size>0 ∧ `mtime≥node.activated_at`; FAIL sớm nếu vi phạm (artifact mandatory).
  2. nếu `check ∉ CHECK_VOCAB` → FAIL "unknown check".
  3. else gọi check fn; gom result.
  4. `node_verdict = PASS iff all results.ok`.
- JSONPointer helper tối giản cho `ptr` (`/recall_at_5`, `/queries`).
- `all_children_done` đọc `status` children từ Tree (không cần artifact); return FAIL nếu `len(children)==0` TRƯỚC khi `all(...)` (F1).
- Verdict là frozen dataclass; chỉ `run_checks` dựng nó.

## Tests After
`python -m pytest decompose_agent/tests/test_gates.py -q` → xanh.

## Regression Gate
`python -m pytest decompose_agent/tests -q` (Phase 1+2) xanh. Property: fuzz một artifact JSON bất kỳ vào `json_field_in_range` KHÔNG raise (luôn ra PASS|FAIL).
