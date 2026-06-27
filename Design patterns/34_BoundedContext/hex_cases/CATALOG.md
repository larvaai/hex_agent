# CATALOG — mọi occurrence của Bounded Context trong hex_agent

> Bảng vét cạn các điểm trong codebase thật `hex_agent` thể hiện ranh giới Bounded Context:
> ngôn ngữ chung riêng (ubiquitous language), model độc lập, và giao tiếp qua hợp đồng explicit
> (DTO / port / event) thay vì cross-import model. Mỗi `path:line` đã được mở file kiểm chứng.
>
> Hai dòng **flagship** được dựng thành case chạy được (`01_*`, `02_*`); phần còn lại là catalog
> tham chiếu. `path` tương đối so với root `hex_agent/`.

| path:line | Mô tả (ngôn ngữ chung + ranh giới) | Độ rõ |
|---|---|---|
| `supervisor/graph.py:175-179` ⭐ | **Flagship 01.** "Scope comes ONLY from O's assignment" (dòng 175). Dựng `DelegationPolicy` từ `assignment.allowed_capabilities` rồi `delegate(...)`. Customer-Supplier: upstream O cấp scope, downstream worker tôn trọng. Bất biến S10.14. | cao |
| `supervisor/contracts.py:59-73` ⭐ | **Flagship 01.** `ContextPacket` cố ý KHÔNG có trường scope (dòng 59); `to_spec()` (67-73) loại scope khỏi `DelegationSpec`. Anti-Corruption boundary: Broker nắn info, không cấp quyền. | cao |
| `delegation/manager.py:63-80` ⭐ | **Flagship 01.** `DelegationManager.delegate()` nhận `DelegationPolicy` (scope từ upstream O); dòng 80 validate & áp policy. `allowed_capabilities` là lối DUY NHẤT scope vào Delegation context. | cao |
| `control/events.py:113-151` ⭐ | **Flagship 02.** `RuntimeEvent` là hợp đồng Published: frozen dataclass, `schema_version`, tách `payload`/`ui_payload` + `RedactionInfo`. Mọi supervisor event phải ánh xạ vào envelope này (OHS). | cao |
| `supervisor/graph.py:56-76` ⭐ | **Flagship 02.** `SupervisorContext.emit()` route event QUA `RuntimeEvent` envelope (60-72) HOẶC raw dict legacy (73-75). Có emitter → topic như `loop.team_composed` đi qua control với redaction. | cao |
| `control/redaction.py:37-73` ⭐ | **Flagship 02.** `Redactor` dịch payload `RuntimeEvent` qua luật redaction; secret bị che trước khi tới UI. Chứng minh hai context không truy cập secret của nhau trực tiếp — adapter dựng sẵn. | cao |
| `rag/service.py:22-113` | RAG context: `health()` trả dict `{collection, count}`; `search()` trả `Hit{source, chunk_index, text, score}`; `ingest()` thao tác trên `Chunk`. Không cross-import model RAG ngoài ports. `VectorStorePort` là tường cô lập context. | cao |
| `rag/ports.py:8-36` | Bounded Context RAG định nghĩa qua ports: value object `Chunk`/`Hit` + protocol `VectorStorePort`/`EmbedderPort`. Hệ ngoài chỉ nói qua các DTO này, không bao giờ chạm model native Qdrant. Ranh giới protocol = ranh giới context. | cao |
| `safety/policy.py:41-102` | Safety context: `PolicyDecision`, `ToolPolicy`, `classify_terminal()`. "policy" ở đây = luật an toàn (permission allowed/blocked), KHÁC `DelegationPolicy` (scope/capability) ở context delegation. Cùng từ "policy", hai nghĩa. | cao |
| `safety/sandbox.py:46-56` | `SandboxError`, `workspace_dir()`, `resolve_in_workspace()` — ngôn ngữ chung của safety về ranh giới workspace. RAG dùng qua lời gọi `resolve_in_workspace()` (rag/service.py:47), KHÔNG import model sandbox vào RAG. | trung bình |
| `control/commands.py:33-93` | Control context định nghĩa `IssuedBy` (33-58), `RuntimeCommand` (61-93), `ACCEPT_STATUSES` (24). "Agent" trong control = `IssuedBy(type='agent')` (commands.py:46). Khác `AgentAssignment` (supervisor) hay `Agent` (roles). Dùng qua port, không cross-import. | cao |
| `delegation/store.py:9-56` | `InMemoryDelegationStore` hiện thực port store. Delegation context không lộ model store ra ngoài — chỉ DTO `DelegationRequest`/`DelegationResult` vượt biên. Store là adapter, không nằm trong logic core. | trung bình |
| `roles/agent.py:20-69` | Roles context: class `Agent` bọc `RoleSpec`, enforce allowlist qua `guard_tool_call()`/`guard_finish()`. "Agent" ở đây = enforcer skill-scoped — khác hẳn supervisor/control. Không import thẳng vào logic supervisor. | cao |
| `roles/registry.py:60-79` | `AgentRegistry.list_roles()` trả projection `RoleView` (slim). Supervisor chỉ dùng cho `role_catalog()` (supervisor/graph.py:51-54) qua interface, không phụ thuộc trực tiếp model. | trung bình |
| `supervisor/state.py:52-77` | Supervisor context định nghĩa `AgentTurn` (52-77), `AcceptanceCheck`, `TaskLoopState`. "Agent" ở đây = chuỗi `agent_id` trong `AgentTurn` — artifact nhẹ trên Blackboard, không phải model giàu. | cao |
| `core/schemas.py:132-178` | Hợp đồng core dùng chung: `DelegationSpec` (132-155), `DelegationPolicy` (158-178). Là DTO giữa các context, cố ý tối giản. Core tránh domain model — chỉ envelope và giá trị policy. | cao |
| `docs/GLOSSARY.md:5-18` | Ngôn ngữ chung documented theo context: `chokepoint` (core), `roster-growth`/`department alias`/`safe checkpoint`/`trust-O` (supervisor), `attribution≠authz` (control). Mỗi context có thuật ngữ riêng, gom một chỗ. | cao |

⭐ = được dựng thành case chạy được trong thư mục này.
