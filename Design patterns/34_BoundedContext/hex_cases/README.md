# hex_cases — Bounded Context (DDD) trong hex_agent

> Bộ case dạy học cho **Lesson 34 — Strategic DDD: Bounded Context**, nhưng lấy ví dụ
> từ codebase thật `hex_agent` (một orchestration multi-agent), thay vì domain Ellumm
> Quiz trong bài gốc. Mỗi case là một bản **distill trung thực** (chỉ stdlib, chạy được)
> của code thật, kèm `path:line` đã mở file kiểm chứng.

---

## Bounded Context xuất hiện ở đâu trong hex_agent?

`hex_agent` không phải một monolith model. Nó được chia thành 5-6 **bounded context** lớn, mỗi cái
có *ngôn ngữ chung riêng*, *model độc lập*, và *giao tiếp qua hợp đồng explicit* (DTO / port / event)
chứ không cross-import model nội bộ của nhau:

| Bounded Context | Ngôn ngữ chung (vài term) | Ranh giới (port/contract) |
|---|---|---|
| **RAG** | `Chunk`, `Hit`, `health()`, `ingest`, `search` | `VectorStorePort`, `EmbedderPort` (`rag/ports.py`) |
| **Safety** | `PolicyDecision`, `ToolPolicy`, `classify_terminal`, `workspace_dir` | `SafeToolPort` (`safety/policy.py`) |
| **Delegation** | `target`, `DelegationPolicy`, `DelegationResult` | `DelegationStorePort`, `DelegationPort` |
| **Control** | `RuntimeEvent`, `RuntimeCommand`, `Actor`, `RedactionInfo`, `visibility` | `EventSinkPort`, `EventEmitter` |
| **Supervisor** | `AgentAssignment`, `ContextPacket`, `AgentTurn`, `Blackboard` | `BrokerPort`, `OrchestratorPort` |
| **Roles** | `Agent`, `RoleSpec`, `guard_tool_call`, allowlist | `AgentRegistry` projection (`RoleView`) |

**Bằng chứng đắt nhất là term "Agent" mang nghĩa khác nhau ở mỗi context** — đúng tinh thần
"cùng từ, khác schema" của Bounded Context (so với "Customer" trong Sales/Billing/Support ở bài gốc):

- **Supervisor**: `AgentAssignment` = một *quyết định điều phối* (orchestration decision) — `supervisor/contracts.py:39-45`.
- **Roles**: `Agent` = một *enforcer skill-scoped* bọc `RoleSpec` — `roles/agent.py:20-69`.
- **Delegation**: `target`/`agent_id` = một *target thực thi* (execution target) — `delegation/manager.py:63`.
- **Control**: `Actor(type='agent')` = *ai gây ra event* (attribution) — `control/events.py:32-50`.
- **Supervisor.state**: `AgentTurn.agent_id` = một *chuỗi id* trên Blackboard, artifact nhẹ — `supervisor/state.py:52-77`.

Việc tích hợp giữa các context dùng đúng các **mẫu Context Map** của bài gốc:

- **Customer-Supplier**: Supervisor → Delegation qua `DelegationPolicy` (case 01).
- **OHS + Published Language**: Control phát `RuntimeEvent`, Supervisor tiêu thụ (case 02).
- **Anti-Corruption Layer**: `ContextPacket` (không scope) + `Redactor` (che secret) — cô lập quyền & secret giữa context.

---

## Các case con

| # | Case | Mẫu Context Map | File chạy |
|---|---|---|---|
| 01 | [Supervisor ↔ Delegation](./01_supervisor_delegation_customer_supplier/) | Customer-Supplier (+ ACL qua `ContextPacket`) | `supervisor_delegation_customer_supplier.py` |
| 02 | [Control ↔ Supervisor](./02_control_supervisor_ohs_published_language/) | OHS + Published Language (+ ACL qua `Redactor`) | `control_supervisor_ohs_published_language.py` |

Bảng vét cạn mọi occurrence: xem [`CATALOG.md`](./CATALOG.md).

---

## Cách chạy

```bash
# Case 01
python3 01_supervisor_delegation_customer_supplier/supervisor_delegation_customer_supplier.py

# Case 02
python3 02_control_supervisor_ohs_published_language/control_supervisor_ohs_published_language.py
```

Mỗi file chỉ dùng thư viện chuẩn Python 3.14, in narration tiếng Việt từng bước, có `assert`
chứng minh bất biến của pattern, và có ÍT NHẤT một đối chứng "khi KHÔNG dùng pattern thì hỏng thế nào".
Không import gì từ `hex_agent` hay thư viện bên thứ ba.

---

## Liên hệ với bài gốc (Lesson 34)

| Khái niệm trong `34_BoundedContext.md` | Hiện thực trong hex_agent |
|---|---|
| "cùng từ, khác schema" (Customer 3 nghĩa) | "Agent" 5 nghĩa qua 5 context (xem bảng trên) |
| Customer-Supplier (arcuate fasciculus) | Supervisor cấp scope → Delegation enforce (case 01) |
| OHS + Published Language (thalamic relay) | Control phát `RuntimeEvent` chuẩn → Supervisor consume (case 02) |
| Anti-Corruption Layer (cerebellum re-encode) | `ContextPacket` không-scope + `Redactor` che secret |
| "Cross-context phải qua protocol explicit, không cross-import" | Mọi context giao tiếp qua port/DTO/event |
| Ubiquitous Language documented (glossary) | `docs/GLOSSARY.md` |
