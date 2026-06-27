# Case 01 — Customer-Supplier: Supervisor ↔ Delegation (qua `DelegationPolicy`)

> Flagship của Lesson 34 (Bounded Context) trong codebase thật `hex_agent`.
> Đây là ví dụ rõ nhất của 3 thứ cùng lúc: **term tách nghĩa qua context**, **Customer-Supplier**,
> và **Anti-Corruption boundary** giữ cho quyền (scope) không rò qua đường nắn thông tin.

---

## 1. Bối cảnh trong hex_agent — vấn đề thật

Trong vòng lặp multi-agent (Epic E10), có ba vai tách bạch:

- **Agent O** (orchestrator) — *quyết định ai làm gì và được dùng capability nào*.
- **Context Broker** — *nắn ngữ cảnh* (briefing) cho worker, dựa trên store slice.
- **Worker** (một role/agent) — *thực thi* trong phạm vi capability được cấp.

Vấn đề kiến trúc: nếu để Broker (kẻ chỉ nên lo thông tin) có khả năng đặt scope, thì một
briefing "tiện tay" có thể leo thang quyền của worker — vượt mặt quyết định authorization của O.
hex_agent giải bằng đúng tinh thần Bounded Context: **Supervisor là upstream supplier cấp scope;
Delegation là downstream customer nhận và bắt buộc tôn trọng scope; còn `ContextPacket` (do Broker
viết) CỐ Ý không có trường scope** — một bức tường chống rò quyền.

Bằng chứng file:line (đã mở kiểm chứng):

- `supervisor/graph.py:175` — comment "Scope comes ONLY from O's assignment — never from the Broker (S10.14)."
- `supervisor/graph.py:176-179` — dựng `DelegationPolicy` **chỉ từ** `assignment.allowed_capabilities`, rồi gọi `delegation_service.delegate(...)`.
- `supervisor/graph.py:158-162` — Broker không được đổi target turn sang agent khác (`PermissionError`).
- `supervisor/contracts.py:59-65` — `ContextPacket` không khai trường scope nào.
- `supervisor/contracts.py:67-73` — `to_spec()` ánh xạ packet → `DelegationSpec`, comment dòng 68: *"Scope is NOT here — O/policy owns it."*
- `delegation/manager.py:63-80` — `DelegationManager.delegate(...)` nhận `DelegationPolicy`, validate qua engine.
- `delegation/policy.py:25-27` — bất biến scope con ⊆ scope cha (`PermissionError` nếu vượt).
- `roles/agent.py:42-54` — worker enforce allowlist qua `guard_tool_call()`.

---

## 2. Trích đoạn code thật

Đường đi Customer-Supplier trong `run_round` (`supervisor/graph.py:155-179`):

```python
store_slice = ctx.store_slice_provider(assignment, state)
packet = ctx.broker.write_packet(assignment=assignment, store_slice=store_slice)
# The Broker shapes context only; it can never redirect a turn to another agent.
if packet.target_agent_id != assignment.agent_id:
    raise PermissionError(
        f"Broker packet target '{packet.target_agent_id}' does not match "
        f"assigned agent '{assignment.agent_id}'."
    )
...
# Scope comes ONLY from O's assignment — never from the Broker (S10.14).
policy = DelegationPolicy(allowed_capabilities=frozenset(assignment.allowed_capabilities))
result = ctx.delegation_service.delegate(
    ctx.supervisor_session, assignment.agent_id, packet.to_spec(), policy
)
```

`ContextPacket` cố ý không mang scope (`supervisor/contracts.py:59-73`):

```python
@dataclass(frozen=True)
class ContextPacket:
    target_agent_id: str
    objective: str
    briefing: str                       # the Broker writes this
    source_ids: tuple[str, ...]         # provenance into the store slice
    expected_output_schema: dict[str, Any] = field(default_factory=dict)

    def to_spec(self) -> DelegationSpec:
        """Map the packet onto a DelegationSpec. Scope is NOT here — O/policy owns it."""
        return DelegationSpec(
            objective=self.objective,
            input_context={"briefing": self.briefing, "source_ids": list(self.source_ids)},
            expected_output_schema=dict(self.expected_output_schema),
        )
```

Bất biến scope con ⊆ scope cha (`delegation/policy.py:25-27`):

```python
scope = policy.allowed_capabilities or parent.allowed_capabilities
if not scope <= parent.allowed_capabilities:
    raise PermissionError("Delegation capability scope exceeds the parent scope.")
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò trong Context Map | Thành phần code thật (hex_agent) |
|---|---|
| **Upstream Supplier** (cấp scope) | Agent O / `AgentAssignment.allowed_capabilities` — `supervisor/contracts.py:39-45` |
| **Downstream Customer** (nhận & enforce) | `DelegationManager.delegate` — `delegation/manager.py:63-80` |
| **Published contract giữa 2 context** | `DelegationPolicy` — `core/schemas.py:158-178` |
| **Anti-Corruption boundary** (info ≠ quyền) | `ContextPacket` (không scope) + `to_spec()` — `supervisor/contracts.py:59-73` |
| **DTO chỉ-thông-tin qua biên giới** | `DelegationSpec` — `core/schemas.py:132-155` |
| **Bất biến scope con ⊆ cha** | `DelegationPolicyEngine.validate` — `delegation/policy.py:13-32` |
| **Enforcer allowlist phía worker** | `Agent.guard_tool_call` — `roles/agent.py:42-54` |
| **Term "Agent" nghĩa khác nhau** | Supervisor: quyết định điều phối · Delegation: target thực thi · Roles: enforcer skill-scoped |

---

## 4. Bản rút gọn chạy được

File: [`supervisor_delegation_customer_supplier.py`](./supervisor_delegation_customer_supplier.py) — chỉ stdlib, chạy:

```bash
python3 supervisor_delegation_customer_supplier.py
```

Nó **mô phỏng**:

- `AgentAssignment` / `ContextPacket` / `DelegationSpec` / `DelegationPolicy` đúng cấu trúc thật (đặc biệt: packet & spec **không** có trường scope).
- `run_round`: O quyết scope → Broker nắn info → policy dựng **chỉ từ** assignment → `delegate(...)`.
- `DelegationPolicyEngine.validate`: bất biến scope con ⊆ cha.
- Worker enforce allowlist: `fs_read`, `fs_write` chạy được; `terminal_run` (ngoài scope) bị chặn.
- **Đối chứng** `no_boundary_anti_pattern()`: một `GodAgent` gánh cả info lẫn quyền → Broker vô tình leo thang scope worker.

Nó **lược bỏ**: LLM thật (O/Broker là hàm xác định), `KernelSession`/child session/SQLite, `DelegationStore`,
event bus, và cơ chế tạo `delegation_id`/`uuid` — vì chúng là hạ tầng, không phải bản chất của pattern.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Cái giá**: phải duy trì 3 hợp đồng (`AgentAssignment`, `ContextPacket`, `DelegationPolicy`) + một engine validate. Với một worker duy nhất, một tham số `scope` truyền thẳng là đủ — tách 3 lớp là thừa.
- **Khi KHÔNG nên**: hệ một-agent, không có khái niệm "ai cấp quyền cho ai"; hoặc prototype mà mọi tool đều được phép. Khi đó Anti-Corruption boundary chỉ thêm chỉ-lệ (ceremony) mà không bảo vệ gì.
- **Dấu hiệu lạm dụng**: nếu Broker/packet bắt đầu cần biết về scope để "tối ưu briefing", đó là mùi rò ranh giới — đúng ra packet phải mù về scope.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `ContextPacket` cố ý **không** có trường scope, trong khi nó vẫn được phép viết `briefing` tuỳ ý? Điều gì hỏng nếu thêm `allowed_capabilities` vào packet?
2. Trong ba context (Supervisor / Delegation / Roles), từ "agent" mang ba nghĩa nào? Cho ví dụ một field/đối tượng đại diện mỗi nghĩa.
3. `DelegationPolicyEngine.validate` bảo đảm `scope ⊆ parent_scope`. Nếu O cấp một capability mà chính nó không có, kết quả `delegate(...)` là gì và tại sao đó là hành vi đúng?
