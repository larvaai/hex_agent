# CATALOG — Repository / Factory / Specification trong hex_agent

Vét cạn mọi occurrence của 3 pattern (Repository / Factory / Specification) trong codebase
`hex_agent`. Path tương đối so với root `/Users/uspro/Desktop/namnson/hex_agent/`.
Mọi `path:line` đã được mở và đối chiếu lại với file thật.

| # | path:line | Vai trò pattern + mô tả | Độ rõ |
|---|-----------|-------------------------|-------|
| 1 | `core/session.py:104-203` | **Factory (FLAGSHIP 01).** `SessionFactory` — constructor duy nhất cho session. `create_root` (139-146) + `create_child` (148-186) enforce invariant, sinh ID, `kernel.freeze()`, publish `task.accepted`. `restore` (188-203) rebuild từ state dict, KHÔNG re-validate, KHÔNG emit event. `create_child` ép scope con ⊆ scope cha (PermissionError). Textbook 2-path factory. | high |
| 2 | `decompose_agent/node.py:102-176` | **Factory + Specification (FLAGSHIP 02).** `Node.from_dict` (143-158) là factory entry; `__post_init__` (122-140) enforce id/kind/status/depends_on/done_when/max_attempts. `DoneWhen.from_dict` (71-91) từ chối FORBIDDEN_VERDICT_KEYS (spec chống forgery). `assert_safe_relpath` (33-47) path-jail (predicate kiểu spec). `as_dict` (160-176) reverse cho persistence. | high |
| 3 | `supervisor/checkpoint.py:22-49` | **Repository.** `SqliteTaskLoopStore` — repo trên SQLite. `save(state)` (36-43) encode TaskLoopState→JSON, upsert vào bảng `taskloop`. `load()` (45-48) decode lại. Concrete impl theo style port. 1 store / run_id. | high |
| 4 | `delegation/store.py:9-56` | **Repository.** `InMemoryDelegationStore` implement `DelegationStorePort`. `start/append_progress/finish` + query `progress/result`. Thread-safe (`RLock`), enforce sequence + idempotency (event_id trùng → no-op; result khác → ValueError). | high |
| 5 | `rag/stores.py:24-56` | **Repository.** `InMemoryVectorStore` — repo trên collection Chunk. `upsert/delete_by_source/search`. `search` (47-56) trả `Hit` (domain object), không lộ `list[Chunk]` nội bộ; vector + score_threshold là một predicate ngầm (implicit specification). | medium |
| 6 | `rag/ports.py:24-37` | **Repository (port).** `VectorStorePort` — Protocol `@runtime_checkable` định nghĩa contract: `health/delete_by_source/upsert/search`. Concrete impls (InMemory, Qdrant) ẩn sau port. Đúng cấu trúc repository-port của DDD/Hex. | high |
| 7 | `core/ports.py:48-62` | **Repository (port).** `DelegationStorePort` — Protocol định nghĩa lifecycle delegation: `start/append_progress/finish/progress/result`. `InMemoryDelegationStore` implement. Ports/adapters style (Hexagonal). | high |
| 8 | `supervisor/state.py:28-49` | **Specification.** `AcceptanceCheck.is_satisfied` (35-37): `status=='passed' AND bool(evidence_ids)`. Predicate đơn (chưa composite). Dùng trong `TaskLoopState.all_accepted()` (102-103). | medium |
| 9 | `supervisor/state.py:114-145` | **Factory (reconstitute path).** `encode_taskloop_state` (114-128) + `decode_taskloop_state` (131-145) — round-trip serialize/reconstitute. `decode` rebuild AcceptanceCheck/AgentTurn từ dict đã persist. Không tách create vs reconstitute riêng nhưng có from_dict/as_dict pattern. | medium |
| 10 | `control/commands.py:33-106` | **Factory (value object).** `IssuedBy` (33-58) + `RuntimeCommand` (61-106) với `from_dict/as_dict`. `__post_init__` enforce: `IssuedBy.type ∈ ISSUER_TYPES`, human cần user_id, agent cần agent_id (39-47); RuntimeCommand các field bắt buộc non-empty (72-81). Enforcement tại construct qua `__post_init__`. | high |
| 11 | `control/event_registry.py:40-93` | **Factory + Specification.** `EventTypeRegistry` (40-61). `parse_event_registry` (64-93) tạo `EventTypeSpec`, validate event_type phải dotted (73-76) + visibility ∈ VISIBILITY_LEVELS (81-85) — spec-like checks. Factory với validation. | medium |
| 12 | `decompose_agent/store.py:53-93` | **Repository.** `DecompCache` — repo trên cây decomposition persist bằng YAML. `get` (62-66) load YAML verbatim (no re-validate), `stage` (68-72) ghi atomic (tmp+os.replace), `commit` (74-77) phối hợp stage+mutate+persist. Content-addressing qua decomp_id = sha256. Transactional semantics. | high |
| 13 | `decompose_agent/tree.py:99-127` | **Factory + Specification.** `load_tree(path)` — factory dựng Tree từ YAML. Validate: duplicate id (105-106), referential integrity parent + depends_on (109-115), acyclicity (`_assert_depends_on_acyclic`, 121). 3 validation specs nhúng trong factory. | high |
| 14 | `core/state.py:8-27` | **Repository (đơn giản).** `StateStore` — repo trên dict in-memory. `get/set/as_dict/snapshot/restore`. `snapshot` (21-23) deepcopy detached; `restore` (25-27) replace wholesale (dùng khi resume). Collection-like API session-scoped. | medium |
| 15 | `supervisor/graph.py:77-79` | **Repository (DI).** `SupervisorContext.save(state)` gọi callback `checkpoint` nếu wired (78-79). `checkpoint` truyền từ ngoài (field 47). Dependency injection của repository (production: `SqliteTaskLoopStore.save`). Repository abstraction qua callback. | medium |
| 16 | `decompose_agent/worker.py:110-177` | **Factory + Specification.** `assemble_4cell` (110-121) — factory dựng FourCell từ Node + tree + journal. `satisfying_files(done_when)` (139-177) — hàm spec-like: cho tập DoneWhen, sinh nội dung artifact thỏa mãn (file_exists, json_field_*, row_count_gte, ...). Factory mang domain knowledge. | medium |

---

## Tổng kết theo pattern

- **Repository** (collection-like over persistence, return AR, ẩn sau port):
  rows 3, 4, 5, 6, 7, 12, 14, 15.
- **Factory** (2 path create/reconstitute, enforce-at-construct):
  rows 1, 2, 9, 10, 11, 13, 16.
- **Specification** (predicate business rule, validation/query/construction guidance):
  rows 2 (DoneWhen), 8 (AcceptanceCheck), 11 (visibility), 13 (referential+acyclic), 16 (satisfying_files).

Nhiều file đóng nhiều vai (vd `node.py` vừa Factory vừa Specification; `tree.py` vừa Factory vừa Specification)
— đúng tinh thần "3 supporting pattern hợp tác quanh aggregate".
