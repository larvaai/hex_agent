---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 4 — decompose() + Gate-2 accept_decomposition + μ + content-addressed transactional cache + detectors

**Mục tiêu:** Node quá-khó tự chẻ thành con nhỏ hơn (μ giảm chặt), qua gate cấu trúc TRƯỚC khi chạm cây, persist content-addressed + two-phase commit (resume idempotent), recurse DFS. Đây là vòng đệ quy thật.

**Files:** `decompose_agent/accept.py`, `store.py`, `solve.py` (decompose path + recurse), `worker.py` (decompose call thật), `tests/test_accept.py`, `test_store.py`, `test_solve_recurse.py`, `test_integration_llm.py` (+1 case).

## Tests Before (đỏ)
- `test_accept.py` — `accept_decomposition(parent, children)` PURE, chạy TRƯỚC mọi mutation, trả `Accept(topo_children)` | `Reject([reasons])`:
  - REJECT singleton `<2` children (D1) "SINGLETON".
  - REJECT `>MAX_FANOUT` (D7) "FANOUT".
  - REJECT child==parent (id trùng hoặc title chuẩn-hóa trùng).
  - REJECT dup id / dup title trong children.
  - REJECT μ không giảm: `len(child.done_when) >= len(parent.done_when)` (D2) "NOT_SMALLER" — **DEC-D1: μ = done_when_count sole measure**.
  - REJECT child done_when rỗng (D11 PROSE_CHILD) / check ∉ CHECK_VOCAB / artifact thiếu/unsafe / có verdict field.
  - REJECT `depends_on` self-dep / trỏ id lạ / tạo cycle.
  - REJECT coverage thiếu (F5, RESOLVED): mỗi parent criterion phải được ≥1 child *kéo theo* (implication theo `check` kind + ngữ nghĩa params), KHÔNG so `artifact-name` (rename hợp lệ không bị UNDERCOVER sai). Check kind chưa định nghĩa quan hệ implication → coi như KHÔNG cover (an toàn về phía chặt) + log.
  - ACCEPT khi sạch: trả children đã topo-sort.
  - Reason chính xác, máy đọc được (để inject lại vào decompose prompt).
- `test_store.py` — content-addressed transactional:
  - `decomp_id = sha256(node_id ‖ canonical_spec(node) ‖ decomposer_version)` ổn định: cùng input → cùng id.
  - Staging file LÀ cache (F4): `cache.get(decomp_id)` đọc thẳng `decompositions/<id>.yaml`. Miss → None; có file → trả children VERBATIM. KHÔNG có cache store thứ hai tách rời staging.
  - Commit nguyên tử MỘT bước (F4): `commit()` gắn children-edges vào tree + set `status=decomposed` trong CÙNG một `os.replace` (write temp tree → fsync → replace). KHÔNG có cửa sổ "đã flip status nhưng chưa gắn con".
  - Mô phỏng crash TRƯỚC `os.replace` → tree cũ nguyên vẹn (node vẫn `active`/`pending`), staging file có thể tồn tại; resume `cache.get` hit staging → KHÔNG re-decompose, KHÔNG re-sample (đóng cửa sổ temp-0 non-determinism).
  - Mô phỏng crash SAU `os.replace` → node `decomposed` + children gắn đầy đủ; resume skip.
  - Resume: node `decomposed` KHÔNG bao giờ re-decompose; cache-hit trả verbatim, KHÔNG re-validate.
- `test_solve_recurse.py` (ScriptedWorker):
  - Node dwc>1 FAIL K lần → `decompose()` → Accept → 2 child trivial (dwc giảm) → mỗi child PASS → recurse xong → parent done iff `all_children_done`.
  - D2: ScriptedWorker đề xuất child μ không giảm → reject → 1 re-decompose (reason injected) → reject lần 2 → BLOCKED(NOT_SMALLER).
  - D4: hai lần decompose chữ ký trùng (`sig = sha256(sorted done_when criteria của children)`) → BLOCKED(STUCK_DECOMP) ngay, không spin.
  - D8: depth > MAX_DEPTH → BLOCKED(MAX_DEPTH).
  - D10: step budget cạn giữa đệ quy → BLOCKED(BUDGET) propagate lên. Mỗi `worker.decompose()` call charge_step (F3): test một decompose-accept-lần-đầu VẪN trừ step (không free).
  - BLOCKED của child propagate lên parent (`CHILD_BLOCKED`).
  - **F1 — vacuous done**: parent ở `decomposed` với 0 children gắn → `all_children_done` FAIL, parent KHÔNG bị mark done.
  - **D12/F2 — COMPOSE_FAIL**: parent có done_when gốc thực-chất (vd metric) tự chẻ; children done HẾT nhưng re-assert done_when gốc của parent FAIL (không ai sinh artifact aggregate vì `reduce` fenced) → BLOCKED(COMPOSE_FAIL), KHÔNG re-decompose. (test: ScriptedWorker cho children done mà parent metric artifact vắng → COMPOSE_FAIL.)
- `test_integration_llm.py` (real 35B, integration, skip-if-unreachable):
  - 1 node thật quá-khó (vd "build retrieval eval harness recall@5≥0.8" rút gọn) → 35B decompose → qua Gate-2 với μ giảm.

## Implement
- `accept.py`: `mu(node) = len(node.done_when)` (DEC-D1, lex thoái hóa thành `<` đơn). `accept_decomposition` port `spec.md:122-150` đủ các D-rule round này (D1/D2/D7/D11 + dup/cycle/vocab/artifact/verdict/coverage). `topo_sort(children)`.
- `store.py` (F4): `decomp_id`, `canonical_spec` (serialize ổn định node spec). `cache.get(decomp_id)` đọc thẳng `decompositions/<id>.yaml` (staging LÀ cache). `commit(node, children)` = write temp tree (children-edges + `status=decomposed`) → fsync → MỘT `os.replace` → đồng thời persist `decompositions/<id>.yaml`. Không có `atomic_flip` tách rời `cache.put`.
- `worker.py`: implement `decompose(node, failure_evidence, reason)` thật — prompt decompose + parse children qua ladder; temp-0.
- `solve.py` decompose path (`spec.md:203-239`): sau khi hết K (dwc>1) → `decomp_id` → `cache.get` (idempotent) → nếu miss: loop { `budget.charge_step()` (F3) → `decompose()` → `accept_decomposition` → check sig vs `decomp_history`(D4) → Accept break | Reject inject reason, `redecomp_count≤R`, lần 2 → block } → `store.commit(node, children)`. Rồi recurse `solve(child, depth+1)` topo-order; child blocked → block parent. **Parent done (DEC-D4): `all_children_done` (len≥1) ∧ re-run done_when GỐC của parent; nếu all_children_done nhưng done_when gốc FAIL → BLOCKED(COMPOSE_FAIL), không re-decompose.**
- Detectors round này: D1,D2,D4,D7,D8,D9,D10,D11,**D12 (tối thiểu)**. (D3 rename/D5 oscillation/D6 coverage-drift-nuance + `reduce` node thật = FENCE, round sau.)

## Tests After
`python -m pytest decompose_agent/tests/test_accept.py decompose_agent/tests/test_store.py decompose_agent/tests/test_solve_recurse.py -q` xanh. Integration khi có 35B.

## Regression Gate
TOÀN BỘ: `python -m pytest decompose_agent/tests -q -m "not integration"` xanh. Property (Hypothesis, derandomize): **μ(child) < μ(parent) đúng cho MỌI accepted decomposition** (proof hội tụ là test, không phải hy vọng). Crash/resume matrix trên `decomp_id` two-phase commit. `python -m decompose_agent .../rag_tree_hard.yaml --root ai.rag` (một leaf cố tình quá-khó) chạy hết: decompose → con done → parent done, với ScriptedWorker.
