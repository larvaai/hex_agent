# Case 04 — OrchestratorPort & BrokerPort: bản Scripted vs LLM-backed thay thế cho nhau

> LSP khi có cả thành phần *không tất định* (LLM): biến thể Scripted (S1, offline) và biến thể
> LLM-backed (S2, gọi model thật) cùng giữ postcondition. Đỉnh cao của case này: `LLMBroker`
> **dùng CODE để thực thi invariant `source_ids ⊆ slice thật`**, từ chối làm yếu hợp đồng dù
> LLM có thể hallucinate id.

---

## 1. Bối cảnh trong hex_agent

Supervisor (E10) có hai "agent mô hình":

- **Agent O (Orchestrator)** — `OrchestratorPort` (`supervisor/orchestrator.py:15-18`): `compose_team()`
  và `decide()` đều trả **chuỗi JSON** để json-gate parse. S1 dùng `ScriptedOrchestrator`
  (`orchestrator.py:21-39`, JSON canned); S2 dùng `LLMOrchestrator` (`supervisor/llm.py:71-91`).
- **Context Broker** — `BrokerPort` (`supervisor/broker.py:17-21`): `write_packet()` trả `ContextPacket`.
  S1 dùng `DeterministicBroker` (`broker.py:24-55`); S2 dùng `LLMBroker` (`supervisor/llm.py:94-137`).

Vì cả S1 và S2 cùng postcondition (orchestrator trả JSON parse được; broker trả `ContextPacket` có
`briefing` + `source_ids ⊆ slice`, KHÔNG có field scope), `TaskLoop` parse JSON / đọc packet *giống hệt*
bất kể nguồn. Mấu chốt: LLM có thể bịa id, nhưng `LLMBroker` **giao `source_ids` LLM trả với id slice
thật** tại `supervisor/llm.py:127-128` — bất biến được giữ BẰNG CODE, không tin LLM. Nếu để LLM phá
postcondition này, `TaskLoop` sẽ phải `if isinstance(broker, LLMBroker): kiểm tra thêm` → OCP sụp.

---

## 2. Trích đoạn code thật

Hai abstraction (`supervisor/orchestrator.py:15-18`, `supervisor/broker.py:17-21`):

```python
@runtime_checkable
class OrchestratorPort(Protocol):
    def compose_team(self, *, task: str, available_roles: tuple[dict[str, Any], ...]) -> str: ...
    def decide(self, *, state_view: dict[str, Any]) -> str: ...

@runtime_checkable
class BrokerPort(Protocol):
    def write_packet(self, *, assignment: AgentAssignment,
                     store_slice: list[dict[str, Any]]) -> ContextPacket: ...
```

Invariant thực thi bằng code, bất chấp LLM hallucinate (`supervisor/llm.py:127-128`):

```python
# Provenance guardrail: keep only ids that really exist in the slice.
source_ids = tuple(s for s in cited if s in slice_ids)
```

Và `LLMOrchestrator` giữ cùng postcondition JSON như `ScriptedOrchestrator` (`supervisor/llm.py:85-91`):

```python
def decide(self, *, state_view: dict[str, Any]) -> str:
    return self._llm.complete([
        {"role": "system", "content": DECIDE_SYSTEM},
        {"role": "user", "content": json.dumps(state_view)},
    ])  # vẫn là str JSON -> cùng json-gate như Scripted
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò LSP | Thành phần trong hex_agent | File:line |
|---|---|---|
| Abstraction `T₁` (orchestrator) | `OrchestratorPort` | `supervisor/orchestrator.py:15-18` |
| Subtype `S₁` (offline) | `ScriptedOrchestrator` | `supervisor/orchestrator.py:21-39` |
| Subtype `S₂` (LLM) | `LLMOrchestrator` | `supervisor/llm.py:71-91` |
| Abstraction `T₂` (broker) | `BrokerPort` | `supervisor/broker.py:17-21` |
| Subtype `S₁` (offline) | `DeterministicBroker` | `supervisor/broker.py:24-55` |
| Subtype `S₂` (LLM) | `LLMBroker` | `supervisor/llm.py:94-137` |
| Abstraction phụ (model seam) | `ChatLLM` Protocol | `supervisor/llm.py:52-54` |
| Postcondition (JSON parse được) | cùng json-gate cho mọi nguồn | `supervisor/orchestrator.py:5-7` (docstring) |
| Invariant (`source_ids ⊆ slice`) | giao id LLM với id slice thật | `supervisor/llm.py:127-128` |
| Invariant (không nới quyền) | `ContextPacket` không có field scope | `supervisor/llm.py:13-14` |

---

## 4. Bản rút gọn chạy được

File: [`orchestrator_broker_lsp.py`](./orchestrator_broker_lsp.py) — `python3 orchestrator_broker_lsp.py` (exit 0).

**Mô phỏng đúng:** ba Protocol (`OrchestratorPort`, `BrokerPort`, `ChatLLM`); `ScriptedOrchestrator` +
`DeterministicBroker` (S1); `LLMOrchestrator` + `LLMBroker` (S2) qua một `FakeLLM` stdlib *cố ý
hallucinate* id `'ghost'`; `LLMBroker` giao `source_ids` với slice thật (guardrail bằng code);
`TaskLoop` parse JSON + kiểm bất biến `source_ids ⊆ slice` và "không field scope", giống hệt cho S1/S2.

**Lược bỏ:** `KernelChatLLM`/`execute_tool` thật (thay bằng `FakeLLM`), `discipline.parse_json_object`
(thay bằng `json.loads`), `supervisor/contracts` thật, vòng lặp dialogue đầy đủ.

**Đối chứng:** `NaiveBroker` tin LLM tuyệt đối, nhét thẳng `('doc1','ghost')` vào packet (làm yếu
postcondition `source_ids ⊆ slice`) → `TaskLoop` bắt vi phạm invariant bằng `assert` → minh họa: subtype
làm yếu postcondition = vi phạm LSP; còn `LLMBroker` thật thì KHÔNG yếu hợp đồng dù LLM bịa.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Chi phí**: phải *không bao giờ tin output LLM* cho các bất biến an toàn — mọi guardrail (provenance,
  size cap, scope) phải nằm trong CODE, lặp ở cả S1 và S2. Tốn công viết và test kép.
- **Cạm bẫy**: nếu một guardrail bị quên ở biến thể LLM (vd: quên giao `source_ids`), `isinstance` vẫn
  pass, json-gate vẫn parse được, nhưng invariant an toàn bị phá ngầm — vi phạm LSP nguy hiểm vì khó thấy.
- Khi hệ thống chưa cần biến thể LLM (chỉ chạy offline mãi mãi), dựng sẵn hai biến thể là over-engineering;
  thêm khi thực sự cần S2.

## 6. Câu hỏi tự kiểm tra

1. Vì sao `LLMBroker` phải giao `source_ids` với id slice thật ngay trong code thay vì tin LLM trả đúng?
   Liên hệ "subclass không được làm yếu postcondition".
2. Cả `ScriptedOrchestrator` và `LLMOrchestrator` đều trả *chuỗi JSON*. Nếu `LLMOrchestrator` trả một
   `dict` đã parse sẵn (thay vì `str`) thì vi phạm điều gì, và `TaskLoop` (json-gate) hỏng ra sao?
3. `ContextPacket` cố tình KHÔNG có field `scope`. Đây là cách dùng kiểu dữ liệu để *cưỡng chế* một
   invariant LSP nào? (Gợi ý: Broker không bao giờ được nới quyền worker.)
