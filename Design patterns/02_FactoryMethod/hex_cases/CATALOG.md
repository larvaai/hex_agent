# CATALOG — Mọi chỗ mang dáng dấp Factory trong `hex_agent`

Bảng vét cạn các occurrence của họ "factory" (Factory Method GoF, Simple Factory, factory function, classmethod-deserializer, plugin/registry factory, projection factory). Các flagship đã có case riêng được đánh dấu ở cột cuối. Mọi `path:line` đã được mở và xác nhận tại thời điểm soạn tài liệu.

| path:line | Mô tả | Độ rõ | Case |
|-----------|-------|:-----:|:----:|
| `core/session.py:119-146` | `SessionFactory.create_root` — factory method tạo phiên gốc: validate phạm vi capability, freeze kernel, dựng identity/state, phát `task.accepted`. | cao | 01 |
| `core/session.py:148-186` | `SessionFactory.create_child` — factory method tạo phiên con cho delegation; ép scope con ⊆ scope cha (chống nâng quyền). | cao | 01 |
| `core/session.py:188-203` | `SessionFactory.restore` — factory method thứ ba: dựng lại `KernelSession` từ identity/state đã lưu, validate capability theo runtime hiện tại. | cao | 01 |
| `roles/registry.py:60-66` | `AgentRegistry.build_agent(name) -> Agent` — tra `RoleSpec` theo tên, dựng `Agent`, tiêm `skills`/`lenses`/`core_tools`. | cao | 02 |
| `roles/spec.py:53-63` | `RoleSpec.allowed_tools` — suy allowlist runtime (role ∪ skill ∪ core − forbidden). Logic "tạo gì" mà factory dựa vào. | cao | 02 |
| `rag/feature.py:27-42` | `build_service(config) -> RagService` — Simple Factory if-elif chọn backend `memory`/`qdrant`; import lười Qdrant; `else: ValueError`. | cao | 03 |
| `rag/feature.py:109-121` | `install(kernel)` của RAG — factory orchestrator: build service rồi tạo & đăng ký 3 tool (`RagHealthTool`/`RagIngestTool`/`RagSearchTool`). Nested factory. | cao | 04 |
| `core/bootstrap.py:56-66` | `build_kernel(config)` — dựng `AgentKernel` rồi gọi `install_configured_features` + `_install_middleware`. | cao | 04 |
| `features/loader.py:10-25` | `install_configured_features` — dispatcher: import động module feature (`spec['module']`) và gọi `install(kernel)`. Plugin factory. | cao | 04 |
| `core/bootstrap.py:28-53` | `_install_middleware` — factory orchestrator bật/tắt `TimingLog`/`PolicyGate`/`Retry`/`CondenseResult` theo `config['middleware']`. | trung bình | 04 |
| `roles/registry.py:69-76` | `AgentRegistry.role_view(name) -> RoleView` — factory dạng projection: chiếu `RoleSpec` thành `RoleView` cho orchestrator E10. | cao | 05 |
| `roles/registry.py:78-79` | `AgentRegistry.list_roles` — dựng `tuple[RoleView]` cho mọi role (gọi `role_view` lặp). | cao | 05 |
| `control/event_registry.py:64-93` | `parse_event_registry(data)` — factory function dựng `EventTypeRegistry` từ config dict; validate cấu trúc, tạo `EventTypeSpec`. | trung bình | — |
| `control/command_registry.py:63-89` | `parse_command_registry(data)` — song song với event registry; dựng `CommandTypeRegistry` từ YAML. | trung bình | — |
| `roles/spec.py:90-114` | `parse_role(data) -> RoleSpec` — factory function deserialize role từ dict YAML; raise ValueError nêu rõ file + field. | trung bình | — |
| `roles/spec.py:117-120` | `load_role_file(path)` — đọc YAML rồi `parse_role`. Cascading factory (file → parse → spec). | trung bình | — |
| `skills/registry.py:28-37` | `SkillRegistry.load_text/load_file/load_dir` — factory methods parse `SkillSpec` từ markdown/file rồi register. Cascading factory. | trung bình | — |
| `graph/runtime.py:31-66` | `build_agent_graph(session,...)` — factory function dựng `StateGraph` cấu hình theo session (node/edge). Factory ở tầng orchestration. | trung bình | — |
| `rag/stores.py:24` | `InMemoryVectorStore` — concrete product do `build_service` tạo cho backend `memory`. | trung bình | 03 |
| `rag/stores_qdrant.py:32` | `QdrantVectorStore` — concrete product cho backend `qdrant`; chỉ import khi cần (import lười). | trung bình | 03 |
| `core/bootstrap.py:17-25` | `load_config(path)` — factory function nạp YAML cấu hình → dict (default `{"features": {}}`). | trung bình | — |
| `core/bootstrap.py:69-70` | `create_kernel(path)` — tiện ích: `load_config` rồi `build_kernel`. | trung bình | 04 |
| `orchestrator/checkpoint.py:138` | `load_checkpoint(run_id) -> Checkpoint | None` — factory dựng `Checkpoint` từ JSON đã lưu (xử lý `legacy-json` vs `langgraph`). | trung bình | — |
| `core/schemas.py:22-23` | `TaskEnvelope.from_dict` — classmethod factory deserialize task từ dict. | trung bình | — |
| `core/schemas.py:74-75` | `CapabilityResult.from_raw` — classmethod factory dựng kết quả capability từ dict thô. | trung bình | — |
| `core/schemas.py:140-141` | `DelegationSpec.from_dict` — classmethod factory deserialize spec uỷ thác. | thấp | — |
| `core/schemas.py:164-165` | `DelegationPolicy.from_dict` — classmethod factory deserialize chính sách uỷ thác (chấp nhận `None`). | thấp | — |
| `core/session.py:36-46` | `SessionIdentity.from_dict` — classmethod factory dựng identity từ dict đã lưu. | trung bình | 01 |
| `tests/test_roles.py:39-44` | `test_build_agent_from_config` — gọi `build_agent("code")`, kiểm tra allowlist suy đúng từ role+skill. Xác nhận factory bằng test. | cao | 02 |
| `tests/test_rag.py:146-150` | `test_build_service_rejects_unknown_backend` — kiểm tra `build_service` reject backend lạ bằng `ValueError`. | cao | 03 |
| `tests/test_lifecycle.py:12` | `SessionFactory(kernel=k).create_root("x")` — dùng factory trong test lifecycle. | cao | 01 |
| `tests/test_delegation.py:46` | `create_root(...)` rồi `create_child(...)` — dùng factory trong test delegation. | cao | 01 |

**Độ rõ**: *cao* = vai trò factory rõ ràng, đã mở file xác nhận trực tiếp; *trung bình* = là factory function/classmethod nhưng nhẹ hoặc phụ; *thấp* = classmethod deserializer suy ra từ mẫu lặp trong codebase, vai trò factory mờ hơn.
