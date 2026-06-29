---
title: "Decompose-until-trivial agent — recursion vertical slice (leaf-attempt + decompose + Gate-2, real local 35B)"
slug: decompose-agent-recursion-slice
status: approved   # human-approved 2026-06-26 by uspro
mode: hard
tdd: true
created: 2026-06-26 15:28
owner: uspro
source_spec: plans/260626-1221-recursive-decompose-agent/spec.md
source_report: plans/reports/design-lessons-260626-1528-worth-learning-from-hex-agent-report.md
project: decompose_agent (fresh package, isolated in this repo)
phases: 4
depends_on: []
risk: low — net-new isolated package; touches NO existing file; rollback = delete the dir
standards:
  - docs/code-standards.md   # §3 naming, §4 TDD, §5 add-file traceability ONLY (NOT §1 microkernel invariants — divergent architecture)
  - plans/260626-1221-recursive-decompose-agent/spec.md   # the architecture for this build
  - plans/reports/design-lessons-260626-1528-worth-learning-from-hex-agent-report.md   # what to carry / leave behind
decisions:
  - DEC-D1 (register DEC-9) μ = done_when_count as the SOLE convergence measure (drop scope_token_len tiebreak)
  - DEC-D2 package decompose_agent/ isolated in repo; follows code-standards §3/§4/§5, NOT §1 architecture invariants
  - DEC-D3 Worker LLM uses TEXT-mode JSON (no response_format=json_object); LM Studio rejects it — rely on repair ladder
  - DEC-D4 (register DEC-10) runtime-decomposed parent gate = all_children_done (len≥1) ∧ re-assert original done_when; all-done-but-original-FAIL → BLOCKED(COMPOSE_FAIL), min D12 un-fenced
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Plan — Decompose agent: recursion vertical slice

> hs:cook đọc file này làm hợp đồng. Claim không hiển nhiên có anchor `file:line`; tag `[UNVERIFIED]` nếu thiếu.
> Đây là build MỚI, package `decompose_agent/` cô lập. KHÔNG sửa file nào trong repo cũ.

## Vì sao plan này

Bỏ hex_agent, dựng agent local-35B "decompose-until-trivial" theo `spec.md`. Round này chứng minh **xương sống đệ quy end-to-end**: Navigator (code) lái một cây node trên đĩa, Worker (35B thật) chỉ đề xuất cục bộ, code là trọng tài PASS/FAIL duy nhất, và một node quá-khó tự **decompose** thành con nhỏ hơn (μ giảm chặt) cho tới khi mọi leaf 35B-trivial. Luật nền (`spec.md:13-22`): "task HARD = chưa chẻ đủ nhỏ; chẻ thành GRAPH bước nhỏ dần tới khi 35B giải được; loop free, chỉ ép correctness (gates) + convergence (μ)."

User chốt (interview 2026-06-26): **(1)** package cô lập trong repo này; **(2)** scope = slice leaf-attempt **+ decompose() + Gate-2** (kéo theo quyết định μ); **(3)** nối local 35B thật từ đầu (test spine vẫn tất định bằng ScriptedWorker; 1 integration test gated trên LLM thật).

## Kiến trúc (khác hex_agent có chủ đích)

Navigator = CODE tất định, sở hữu TẤT CẢ global: `tree.yaml` trên đĩa, cursor DFS đơn, mọi gate, mọi budget, decomposition cache, máy trạng thái node. Worker = 35B, proposer cục bộ trên MỘT node, đúng hai call: `propose(4-cell)→action`, `decompose(node,failure)→children`. **Worker không bao giờ ghi verdict, không resolve path, không mutate cây** (`spec.md:44-49`). Đây là ranh giới toàn vẹn DUY NHẤT — threat model có đúng một thành phần không-tin-được (con 35B).

Bài học mang theo từ hex_agent (`source_report`), không phải framework của nó:
- Tách CLAIM khỏi VERDICT — **không tồn tại field verdict/passed/score ở đâu Worker ghi được**; chỉ `gates.run_checks` ghi PASS/FAIL (lift tư tưởng `supervisor/graph.py:231-256`, `discipline/finish_gate.py`).
- Thang sửa JSON deterministic-first, raw-candidate-thắng (lift `discipline/json_gate.py:305-394` + `normalize_action:420-432` + skeleton re-prompt `:483-493`).
- Parse-error budget TÁCH khỏi step budget, gate trên **streak liên tiếp** (lift `discipline/budget.py:11-54`; trùng memory local-model-quirks).
- No-artifact=FAIL: bắt buộc + path-jail + non-empty + **fresh (mtime≥activated_at)** trước khi check chạy (`spec.md:48,110`).
- Validate invariant trong `__post_init__` → node sai cấu trúc không thể tồn tại (lift `control/events.py:134-151`).
- Đĩa là sự thật: decomposition content-addressed + two-phase commit → resume idempotent miễn phí (`spec.md:32,206-225`).
- Exec no-shell argv + path-jail fail-closed (lift `safety/sandbox.py:25-56`, `toolbox/terminal.py:32-43`) — chỉ cần khi thêm `test_passes`/`cmd_*` (FENCE round này).

Bỏ lại (ceremony cho cloud/multi-tenant): toàn bộ `control/` plane, `roles/skills/delegation` như hệ identity, coupling langgraph + `kernel.use(mw)` onion, freeze in-memory/StateStore, mọi lock. (Chi tiết: `source_report` §anti-bài-học.)

## DEC (quyết định chốt round này)

- **DEC-D1 — μ = `done_when_count` là measure DUY NHẤT.** Bỏ tiebreak `scope_token_len` (rủi ro tokenizer drift qua `decomposer_version` phá ngầm proof — `spec.md:343,345`). `(ℕ,<)` well-ordered ⇒ không có descent vô hạn. `accept_decomposition` reject child nếu `len(child.done_when) >= len(parent.done_when)`. **Hệ quả chấp nhận (revalidator A):** strict `<` trên 1 số nguyên cấm chẻ một node `dwc≤2` thành con đa-criterion trung thực → node đó BLOCKED(NOT_SMALLER); step budget KHÔNG cứu (chỉ block, không "lo tie"). `dwc==1` → UNSOLVABLE_LEAF, không chẻ (`spec.md:200`, F8). Giới hạn năng lực có-chủ-đích của slice, surface cho người.
- **DEC-D2 — package `decompose_agent/` cô lập**, own tests subtree. Theo code-standards §3 (snake_case module, PascalCase class, docstring dòng đầu), §4 (TDD red→green, full suite xanh, commit cặp, no-weakening), §5 (add-file traceability). KHÔNG theo §1 (microkernel/langgraph/SQLite invariants — kiến trúc cũ).
- **DEC-D3 — Worker LLM TEXT-mode JSON.** KHÔNG `response_format=json_object` (LM Studio reject — memory `hex-agent-local-model-loop-quirks`). `LocalLLMWorker` PHẢI gọi adapter với `json_mode=False` tường minh (F6: `llm/adapter.py:72` mặc định `True` → set json_object `:81`, chỉ downgrade phản ứng khi 400 → nếu để mặc định sẽ vừa tốn round-trip vừa lệch khỏi ScriptedWorker test). Dựa vào repair ladder + shape-normalizer. Env tái dùng code-standards §6: `LLM_BASE_URL=http://localhost:1234/v1`, `LLM_MODEL=local-model`.
- **DEC-D4 — Gate của parent decompose RUNTIME (đóng F2/COMPOSE_FAIL).** Khi node có done_when thực-chất tự chẻ: gate hiệu dụng = `all_children_done` ∧ **re-assert done_when GỐC của parent**. `all_children_done` PASS iff `len(children)≥1` ∧ mọi child `done` (F1: `all([])` là True — chặn rỗng). Coverage (Gate-2) buộc mỗi criterion gốc parent được ≥1 child *kéo theo*. Children done HẾT mà done_when gốc parent vẫn FAIL → **BLOCKED(COMPOSE_FAIL)** (un-fence D12 tối thiểu), KHÔNG re-decompose — đó là cần `reduce` (round sau), không phải chẻ thêm. Cây hand-baked (pre-decomposed) thì parent done_when = `all_children_done` trực tiếp là đúng (`spec.md:338`).

## Module map (decompose_agent/)

| module | trách nhiệm | nguồn ý tưởng |
|---|---|---|
| `node.py` | `Node` frozen dataclass + done_when triple `{check,params,artifact}`; `__post_init__` reject verdict/passed/score field, bad triple, unsafe artifact | lift `control/events.py:134-151` |
| `tree.py` | tree.yaml loader: referential integrity (`depends_on` tồn tại, acyclic at load) + path-jail; `next_node()` cursor DFS | `spec.md:247,84-85` |
| `json_repair.py` | repair ladder (raw-wins, pure str→str) + `normalize_action` shape + `build_retry_message` skeleton (theo call type) | lift `discipline/json_gate.py:305-394,420-432,483-493` |
| `budget.py` | per-root step budget + consecutive parse-error budget + K attempt | lift `discipline/budget.py:11-67` |
| `gates.py` | CHECK_VOCAB registry + `run_checks` (verdict CODE-written) + artifact assertion (exists/non-empty/jail/fresh); `all_children_done` chặn rỗng (`len≥1`, F1) | `spec.md:89-116` |
| `workspace.py` | per-node artifact dir `var/decompose/<root>/artifacts/<node_id>/`; runner GHI chỉ trong dir của node đang active (F7: chặn worker ghi đè artifact của node khác để gian lận gate) | `spec.md:65` |
| `accept.py` | `accept_decomposition` pure gate + `mu` (=done_when_count) | `spec.md:118-153` |
| `worker.py` | `Worker` Protocol; `LocalLLMWorker` (LM Studio text-mode + ladder); `ScriptedWorker` (test); `assemble_4cell` | `spec.md:38-42`; lift `llm/adapter.py` |
| `store.py` | content-addressed decomp cache: `decomp_id` sha256, temp-0; **staging file = cache** (`cache.get` đọc `decompositions/<id>.yaml`); commit = MỘT `os.replace` nguyên tử gắn children-edges + `status=decomposed` cùng lúc (F4: tránh cửa sổ crash mất con / re-sample) | `spec.md:32,206-225` |
| `journal.py` | append-only JSONL journal per node + frozen verdict record | lift `observability/event_log.py:60-99` |
| `solve.py` | `solve(node,depth,budget)` driver: activate→leaf-attempt-K→decompose→Gate-2→recurse-DFS→mark_done/block; `charge_step()` trên MỌI `worker.decompose()` call (F3); detectors D1/D2/D4/D7/D8/D9/D10/D11/**D12** | `spec.md:180-245` |
| `__main__.py` | `python -m decompose_agent <tree.yaml> --root <id>` | — |
| `tests/` | unit (ScriptedWorker, no LLM) + 1 integration (real 35B, skip-if-unreachable) | code-standards §4 |

## Phases

1. **Skeleton + Node/tree loader + lifted utilities (no LLM).** `node.py`, `tree.py`, `json_repair.py`, `budget.py`. → `phase-1-skeleton-loader.md`
2. **Gate-1 done-gate runner (no LLM).** `gates.py`: CHECK_VOCAB (data checks) + `run_checks` + artifact freshness/jail; verdict code-written. → `phase-2-done-gate.md`
3. **solve() leaf-attempt + Worker port + real 35B + hand-baked tree.** `worker.py`, `journal.py`, `solve.py` (leaf path), `__main__.py`; DFS cursor + `all_children_done` closure. → `phase-3-leaf-attempt-loop.md`
4. **decompose() + Gate-2 + μ + content-addressed transactional cache + detectors.** `accept.py`, `store.py`, `solve.py` (decompose path + recurse). → `phase-4-decompose-recursion.md`

## Scope boundary (OUT round này — FENCE)

Theo staging của spec (`spec.md:341`), KHÔNG làm round này: `inputs`/`outputs` dataflow wiring + `resolve_inputs()`; `kind: reduce` compose node (tự-sinh, worker/code reduce); detectors D3/D5/D6/D7/D11; checks `test_passes`/`cmd_*` (cần whitelist cmd_id + no-shell exec); cross-tree `needs`; human-in-the-loop BLOCKED resolution / degraded auto-mode; UI/observability ngoài JSONL journal. Mỗi cái là một round sau, có caller rõ ràng.
> **D12/COMPOSE_FAIL KHÔNG còn fenced** (DEC-D4): dạng tối thiểu (re-assert done_when gốc của parent sau children-done; FAIL → block, không re-decompose) PHẢI có round này để đóng lỗ false-termination F2. `reduce` node thật vẫn fenced — D12 chỉ *phát hiện* nhu cầu reduce, chưa *giải*.

## Acceptance (toàn plan)

Với ScriptedWorker (tất định, no LLM):
1. **Loader**: tree.yaml hợp lệ load được; unknown check / dangling `depends_on` / verdict-field / unsafe artifact path → reject với message nêu file+field.
2. **Gate-1 trọng tài duy nhất**: verdict chỉ do code ghi; empty file → FAIL `file_exists`; artifact `mtime < activated_at` → auto-FAIL trước khi predicate chạy; metric ngoài range → FAIL; node DONE iff mọi criterion PASS. **F7**: action runner ghi artifact CHỈ trong dir của node đang active; worker không ghi được vào dir node khác để pre-satisfy gate (test: action trỏ path ngoài dir node → reject).
3. **Leaf-attempt + cursor**: trên cây RAG hand-baked (`spec.md:253-315`, decomposition pre-baked), cursor DFS advance leftmost-pending-deps-done; leaf PASS khi propose tốt; forced FAIL retry tới K rồi BLOCKED(UNSOLVABLE_LEAF) cho dwc==1; parse fumble KHÔNG trừ step budget; parent done iff `all_children_done`.
4. **decompose + Gate-2 + μ**: node FAIL K lần (dwc>1) → `decompose()` → `accept_decomposition` reject singleton/non-shrinking-μ/dup-id/unknown-check/verdict-field/cycle với reason chính xác; coverage = mỗi parent criterion được ≥1 child *kéo theo* (implication, KHÔNG name-equality — F5); Accept khi μ(child)<μ(parent) ∀child + coverage; con solve xong → parent done.
5. **Idempotent resume**: `decomp_id` ổn định (cùng input→cùng children); resume `cache.get` đọc staging file → trả children verbatim KHÔNG re-validate; node `decomposed`/`done` bị skip; commit nguyên tử (một `os.replace` gắn children + `status` cùng lúc) → crash mô phỏng không double-decompose, không mất con (F4).
6. **Convergence + no-false-done**: D10 step budget hard-stop (charge trên MỌI worker.decompose — F3); D2 reject child μ không giảm; D4 chặn re-decompose chữ-ký-trùng (STUCK_DECOMP); D8 MAX_DEPTH; D9 unsolvable leaf. **F1**: parent `decomposed` với 0 children → `all_children_done` FAIL (không vacuous-done). **D12/F2**: children done HẾT nhưng done_when GỐC parent FAIL → BLOCKED(COMPOSE_FAIL), không re-decompose.

Integration (real local 35B, `LLM_BASE_URL` reachable, else skip): ≥1 leaf PASS done_when thật; ≥1 node quá-khó decompose qua được Gate-2.

Verify: `python -m pytest decompose_agent/tests -q` xanh (unit). `python -m decompose_agent decompose_agent/tests/fixtures/rag_tree.yaml --root ai.rag` chạy hết với ScriptedWorker.

## Rollback

Package cô lập, KHÔNG sửa file repo cũ. Rollback = `rm -rf decompose_agent/` + gỡ entry pyproject (nếu thêm). Zero blast radius.

## Open risks (chốt trước/trong khi code)

- **μ tiebreak** (revalidator A, đã chốt DEC-D1): done_when_count sole measure TERMINATE (strict `<` trên ℕ). Nhưng hệ quả thật KHÔNG phải "backstop lo tie": node `dwc≤2` cần con đa-criterion trung thực sẽ BLOCKED(NOT_SMALLER) — khớp `spec.md:345` "ties can stall". Chấp nhận cho slice cô lập; nới (vd μ = (dwc, scope_len) với tokenizer pinned, hoặc cho phép child dwc==parent dwc khi coverage chặt) là round sau.
- **`criteria_coverage` semantics** (`spec.md:346`) — RESOLVED: "mỗi parent criterion được ≥1 child *kéo theo*" (implication). Bỏ proxy `(check, artifact-name)` equality (F5: rename artifact hợp lệ sẽ bị UNDERCOVER sai → BLOCKED). Phase 4 dùng implication theo `check` kind + ngữ nghĩa params (không so tên artifact); nếu một check kind chưa có quan hệ implication định nghĩa → coi như KHÔNG cover (an toàn về phía chặt) và ghi log để round sau tinh chỉnh.
- **`decomposer_version` pin**: temp-0 sampling cần model tất định; LM Studio không đảm bảo bit-identical. decomp_id vẫn ổn định vì hash trên INPUT (id‖spec‖version), cache-hit trả verbatim — không re-sample. Risk: lần sample ĐẦU khác máy. Chấp nhận round này (single user, single machine).
- **ScriptedWorker vs 35B drift**: unit test tất định không bắt được hành vi 35B thật. Integration test che một phần; coverage hành vi model là round riêng.
