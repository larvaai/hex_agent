# CATALOG — Mọi occurrence của SRP trong hex_agent

Bảng vét cạn các vị trí trong codebase `hex_agent` thể hiện **Single Responsibility
Principle**. Mỗi dòng đã được mở file kiểm chứng path:line. Root tuyệt đối:
`/Users/uspro/Desktop/namnson/hex_agent/`.

Cột **độ rõ**: mức độ "một-actor, một-lý-do-đổi" lộ rõ tới đâu (high / medium).
Năm dòng đầu (★) là flagship đã được dựng thành case con.

| ★ | path:line | Mô tả (actor + trách nhiệm đơn nhất) | Độ rõ |
|---|-----------|--------------------------------------|-------|
| ★01 | `discipline/json_gate.py:1-494` | Module repair JSON output của model: ~24 hàm top-level thuần `str->str` (26 tính cả 2 def lồng) + thang nến `_candidates` + loader `_load_object`/`parse_action`. Actor: đội Validation/JSON-gate. Không đụng DB/emit/cache. | high |
| ★02 | `discipline/budget.py:1-68` | `@dataclass Budget`: đếm step/parse-error/same-tool và gác ngưỡng. Actor: đội run-orchestration (`orchestrator/loop.py`). Không đụng permission/event/kernel. | high |
| ★03 | `control/redaction.py:1-74` | `Redactor`: che secret đệ quy trước UI/SSE, ghi path đã che, không mutate input. Actor: đội UI/Observability. Không validate/route/store. | high |
| ★04 | `control/event_registry.py:1-100` | `EventTypeRegistry` + `EventTypeSpec`: catalog event type + visibility, `assert_known` gác emitter. Actor: đội control-plane. Pure read-model sau khi nạp. | high |
| ★05 | `control/authz.py:1-50` | Hai predicate thuần: `is_permission_escalating`, `command_needs_human_checkpoint`. Actor: đội security checkpoint (S21.6). Không sửa state/log/emit. | high |
| | `discipline/budget.py:29-35` | `from_env()` đọc `max_steps/max_parse_errors/max_same_tool_calls` từ env với default — điểm tiêm cấu hình test/prod không cần đổi code. | high |
| | `discipline/condense.py:13-24` | `condense(value, max_chars, max_list)` — cắt gọn cấu trúc dữ liệu kết quả tool một cách đệ quy. Actor: đội định dạng output. Thuần biến đổi, không parse/validate/dispatch. | high |
| | `discipline/finish_gate.py:7-22` | `requires_validation`, `has_passing_validation`, `check_finish` — ba predicate gác hành động finish. Actor: đội run-completion/validation. Truy vấn state thuần, không side effect. | high |
| | `control/permission.py:22-53` | `@dataclass Permission` (frozen): cờ `can_*` + `allowed_tools` + `effective_from`; method `allows_tool`/`patched`/`as_dict`/`from_dict`. Actor: đội security quản profile capability. Không orchestrate/route. | high |
| | `control/emitter.py:28-96` | `EventEmitter` điều phối validate (registry.get) + sequencing (SessionSeq) + redact (Redactor) + fan-out (EventSinkPort); `BusEventSink` adapt EventBus. Emitter điều phối, sink thực thi — mỗi sink swap được. | high |
| | `control/commands.py:1-50` | Schema `RuntimeCommand` + `IssuedBy` (attribution-only). Actor: command dispatcher. Không execute, không quyết authz — đẩy payload sang authz predicates. | medium |
| | `adapters/agents/langgraph_agent.py:21-96` | `LangGraphDelegationAgent`: một hiện thực của `DelegationPort`; `can_handle`/`run`. Actor: đội delegation orchestration. Không quản permission, không phải router. | high |
| | `supervisor/llm.py:57-92` | Ba collaborator: `KernelChatLLM` (bridge kernel->model), `LLMOrchestrator` (format prompt quyết định), `LLMBroker` (build briefing packet + guardrails). Mỗi class một concern. | high |
| | `control/event_registry.py:40-62` | Query interface của `EventTypeRegistry`: `__contains__`/`assert_known`/`get`/`visibility`/`types`. Lookup thuần sau khi dựng. Nạp một lần mỗi session. | high |
| | `control/command_registry.py:36-60` | `CommandTypeRegistry` phản chiếu pattern của EventTypeRegistry — dict specs, query API, nạp từ YAML, command lạ ném tại gateway. | high |
| | `control/snapshot.py:36-86` | `AgentView` (frozen) + `TaskLoopSnapshot` (frozen): struct read-model. Actor: đội render UI. Không mutate state, không orchestrate. Data holder thuần với `as_dict`/`from_dict`. | high |
| | `llm/adapter.py:13-120` | Interface gọi LLM: `_defaults`/`_get_client`/phân loại lỗi `_is_transient`/`_is_connection_error`/`_is_response_format_error`/`call_llm` (retry backoff). Actor: đội tích hợp LLM. Không biết về agent loop. | high |
| | `orchestrator/loop.py:40-96` | Facade `run`/`resume` công khai (`_config`/`_outcome`/`_sync_budget`/`_stream`). Orchestrator cho graph execution. Actor: đội run-harness. Không hiện thực agent, không route event. | medium |
| | `graph/nodes.py:40-138` | Năm node LangGraph (`guard_node`/`agent_node`/`tool_node`/`delegation_node` + helper). Mỗi hàm một bước loop. Hàm thuần nhận `AgentState`, `session`. Test cô lập được. | medium |
| | `supervisor/graph.py:34-80` | `SupervisorContext` dataclass giữ runtime deps + wrapper `emit(topic, payload)`. Actor: đội supervisor-loop orchestration. Không hiện thực agent, không phải router. | medium |

> Lưu ý đối chiếu: `control/permission.py` thực tế có **5** cờ boolean `can_*`
> (`can_write_artifacts`, `can_call_other_agents`, `can_execute_shell`, `can_modify_workflow`,
> `can_modify_permissions`) cùng `allowed_tools: tuple` và `effective_from: str` — tổng 7 field
> dữ liệu. (Mô tả gốc trong plan ghi "7 bool fields"; con số 7 đúng cho *tổng field*, không
> phải riêng cờ bool.)
