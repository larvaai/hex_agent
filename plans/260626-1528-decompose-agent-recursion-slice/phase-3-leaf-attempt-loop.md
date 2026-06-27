---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 3 — solve() leaf-attempt + Worker port + real 35B + hand-baked tree

**Mục tiêu:** Vòng đời end-to-end KHÔNG decompose: activate → propose (35B) → run action → run_checks → DONE | retry-K | BLOCKED. DFS cursor + `all_children_done` closure trên cây hand-baked. Nối local 35B thật; test spine bằng ScriptedWorker.

**Files:** `decompose_agent/worker.py`, `journal.py`, `solve.py` (leaf path), `__main__.py`, `tests/test_worker.py`, `test_solve_leaf.py`, `test_integration_llm.py`.

## Tests Before (đỏ)
- `test_worker.py`:
  - `assemble_4cell(node, tree)` trả ĐÚNG 4 cell: IDENTITY (preamble cố định) / breadcrumb root→node / NODE (title+done_when+resolved-paths+notes) / journal tail (1-3 dòng cuối CỦA node này). KHÔNG lộ graph (`spec.md:42`).
  - `ScriptedWorker` trả action theo kịch bản; `propose` parse qua repair ladder.
  - `LocalLLMWorker`: gọi adapter với `json_mode=False` TƯỜNG MINH (F6 — assert request KHÔNG có `response_format`); output đi qua `json_repair` + `normalize_action`. (test bằng fake client, không gọi mạng.)
  - **F7 — action runner ép target**: action ghi artifact CHỈ được vào dir của node đang active (`var/decompose/<root>/artifacts/<node_id>/`); action trỏ path ngoài dir node (kể cả trong jail tổng) → reject, KHÔNG ghi. Worker không thể pre-satisfy gate của node khác.
- `test_solve_leaf.py` (ScriptedWorker, tất định):
  - Leaf propose tốt (ghi artifact đúng) → run_checks PASS → `mark_done` → cursor advance.
  - Leaf FAIL: propose ghi artifact sai → retry tới K → BLOCKED(UNSOLVABLE_LEAF) cho dwc==1.
  - Parse fumble (ScriptedWorker trả JSON hỏng) → ParseBudget streak++, KHÔNG record_step; recover khi parse tốt.
  - `activate(node)` stamp `activated_at`; artifact ghi sau đó mới fresh (kết nối Phase 2 freshness).
  - Cursor DFS: trên cây RAG hand-baked, đi leftmost-pending-deps-done; parent `ai.rag` chỉ done khi `all_children_done`.
  - D10: step budget hard-stop giữa chừng → BLOCKED(BUDGET) tại active node.
  - Journal append mỗi attempt: `{node, action, verdict}` JSONL, đọc lại được, tail-corruption tolerant.
- `test_integration_llm.py` (real 35B; `pytest.mark.integration`; SKIP nếu `LLM_BASE_URL` unreachable):
  - Cây 1-leaf trivial ("ghi `out.json` có field `ok=true`"); 35B propose → leaf PASS done_when thật.

## Implement
- `worker.py`: `Worker` Protocol (`propose(ctx)->dict`, `decompose(node,failure)->dict` — decompose stub ở phase này, raise NotImplemented). `assemble_4cell`. `LocalLLMWorker` (lift `llm/adapter.py` call shape, **`json_mode=False` tường minh** — DEC-D3/F6, ladder). `ScriptedWorker(script)`.
- `workspace.py`: `node_dir(root, node_id)` → `var/decompose/<root>/artifacts/<node_id>/`; `write_artifact(node, rel_path, data)` resolve dưới `node_dir` + reject escape (F7). done_when artifact path là relative tới node_dir của chính node đó.
- `journal.py`: `append(node_id, record)` JSONL dưới `var/decompose/<root>/<node>.jsonl`; `tail(node_id, n)`; reader skip dòng cụt/non-dict.
- `solve.py` (leaf path only): `solve(node, depth, budget)` theo `spec.md:180-201` — circuit breakers (budget/depth) → activate → (resolve_inputs SKIP round này) → while attempts<K: record_step, propose, run action (ghi artifact qua jailed fs helper), run_checks, journal; PASS→mark_done(advance cursor); hết K + dwc==1 → block(UNSOLVABLE_LEAF). `mark_done` advance cursor DFS; parent done khi `all_children_done`.
- `run action`: round này action = ghi artifact qua `workspace.write_artifact(active_node, ...)` — target BỊ ÉP vào dir của node đang active, KHÔNG đọc path tùy ý từ worker args (F7). KHÔNG có tool registry phức tạp (YAGNI) — chỉ đủ để leaf tạo artifact cho gate chấm.
- `__main__.py`: load tree, chọn root, chạy `solve` với ScriptedWorker mặc định hoặc LocalLLMWorker nếu `--llm`.

## Tests After
`python -m pytest decompose_agent/tests/test_worker.py decompose_agent/tests/test_solve_leaf.py -q` xanh. Integration chạy khi có 35B: `python -m pytest decompose_agent/tests/test_integration_llm.py -q -m integration`.

## Regression Gate
`python -m pytest decompose_agent/tests -q -m "not integration"` (Phase 1-3) xanh. `python -m decompose_agent decompose_agent/tests/fixtures/rag_tree.yaml --root ai.rag` chạy hết với ScriptedWorker (cursor walk + leaves done).
