# CATALOG — Mọi occurrence của Flyweight (và dấu vết của nó) trong `hex_agent`

Bảng vét cạn từ bước discover, **đã mở lại từng file để xác minh `path:line`**. Một vài
entry trong plan gốc lệch tên/dòng so với code thật; những chỗ đó đã được **sửa cho khớp**
và ghi chú trong cột mô tả (đánh dấu *(đã hiệu chỉnh)*).

Quy ước độ rõ: **cao** = vai trò Flyweight rất rõ; **trung bình** = mang dấu vết
(frozen/pool/`__slots__`) nhưng intent chính có thể khác.

| path:line | Mô tả | Độ rõ |
|-----------|-------|-------|
| `core/kernel.py:14-22` | `_deep_freeze()` — biến mọi cấu trúc mutable thành proxy bất biến (`MappingProxyType` cho dict, `frozenset` cho set, `tuple` cho list). Immutability guard cốt lõi của Flyweight. | cao |
| `core/kernel.py:24-46` | `_LatchedNext` dùng `__slots__` (dòng 29) — one-shot proxy chạy inner handler tối đa một lần, replay kết quả/exception ở lần sau. `__slots__` là kỹ thuật tiết kiệm bộ nhớ khi có nhiều instance. | trung bình |
| `core/kernel.py:49-73` | `_wrap()` — bind middleware quanh `nxt`; fail-open middleware latch `nxt` (one-shot qua `_LatchedNext`) để chuỗi middleware dùng lại không chạy tool hai lần. | trung bình |
| `core/kernel.py:76-98` | `AgentKernel` — Flyweight Factory + Shared Intrinsic Pool; `freeze()` (91-97) deep-freeze config một lần. N session dùng chung. | cao |
| `core/registry.py:10-20` | `ToolDescriptor` `@dataclass(frozen=True)` + `DEFAULT_DESCRIPTOR` (dòng 20) — constant singleton dùng chung cho mọi tool không có descriptor riêng. Intrinsic state điển hình. | cao |
| `core/registry.py:43-121` | `CapabilityRegistry` — `_tools/_features/_descriptors` là pool; `resolve_tool()` (103-112) trả `ToolResolution` từ cache theo tên, không tạo instance mới. Flyweight cache thuần. | cao |
| `core/schemas.py:11-26` | `TaskEnvelope` `@dataclass(frozen=True)` — value type bất biến, chia sẻ qua request/response. | cao |
| `core/schemas.py:28-34` | `ToolRequest` frozen — value type nhẹ, bất biến, hashable. | cao |
| `core/schemas.py:36-46` | `ToolCallContext` frozen — lineage + scope bất biến của session. | cao |
| `core/schemas.py:63-101` | `CapabilityResult` frozen — envelope đồng nhất mọi tool call trả về. | cao |
| `core/schemas.py:114-130` | `FeatureDescriptor` frozen — intrinsic identity của 1 feature (name, version, capabilities...). | cao |
| `core/schemas.py:132-156` | `DelegationSpec` frozen — spec ủy thác bất biến. | cao |
| `core/schemas.py:158-179` | `DelegationPolicy` frozen — policy ủy thác (max_steps/depth + `allowed_capabilities` frozenset). | cao |
| `core/schemas.py:181-198` | `DelegationRequest` frozen — yêu cầu ủy thác bất biến. | cao |
| `core/schemas.py:201-214` | `ArtifactEnvelope` frozen — vỏ artifact bất biến. | cao |
| `core/schemas.py:217-232` | `DelegationProgress` frozen — bản ghi tiến độ bất biến. | cao |
| `core/schemas.py:235-252` | `DelegationResult` frozen — kết quả ủy thác bất biến. | cao |
| `core/session.py:15-23` | `SessionIdentity` `@dataclass(frozen=True)` — identity bất biến, chia sẻ tham chiếu ổn định. | cao |
| `core/session.py:49-85` | `KernelSession` — Context giữ extrinsic per-task, trỏ tới kernel dùng chung. | cao |
| `core/session.py:104-146` | `SessionFactory` — Client lắp ráp session; `kernel.freeze()` (141) trước session đầu; không nhân bản kernel. | cao |
| `core/bootstrap.py:56-66` | `build_kernel()` — tạo MỘT `AgentKernel` với `CapabilityRegistry` + `EventBus` dùng chung; kernel được freeze (`core/session.py:141`) thành shared immutable pool. | cao |
| `features/example_echo.py:9-13` | `FEATURE = FeatureDescriptor(...)` — constant module-level; `install()` tái dùng đúng instance, không tạo mới mỗi lần. | cao |
| `features/example_echo.py:16-25` | `EchoTool` tạo một lần và đăng ký toàn cục; cùng `FEATURE` được tái dùng cho mọi session. | cao |
| `decompose_agent/store.py:27-37` | `canonical_spec` (27-32) + `decomp_id` (35-37) — trích intrinsic spec rồi hash thành khóa content-addressed. | cao |
| `decompose_agent/store.py:53-92` | `DecompCache` — Flyweight Factory content-addressed; `get` (62-66) đọc verbatim không re-validate; `commit/_attach` (74-85) chuyển trạng thái node frozen qua `replace`. | cao |
| `decompose_agent/node.py:20` | `FORBIDDEN_VERDICT_KEYS = frozenset({...})` — chặn forge verdict ngay lúc construct criterion. | cao |
| `decompose_agent/node.py:50-99` | `DoneWhen` `@dataclass(frozen=True)` (decorator 50, class 51) — một acceptance criterion bất biến, hashable, an toàn cache. | cao |
| `decompose_agent/node.py:102-140` | `Node` `@dataclass(frozen=True)` (decorator 102, class 103) — đơn vị công việc bất biến; chuyển trạng thái qua `dataclasses.replace`. | cao |
| `decompose_agent/gates.py:31-53` | `CheckResult` (decorator 31, class 32), `CriterionVerdict` (decorator 37, class 38), `Verdict` (decorator 45, class 46) — đều `@dataclass(frozen=True)`, bất biến, an toàn cache/chia sẻ qua các lần đánh giá gate. *(plan ghi "Criterion, Verdict, GateResult" 31-52; tên thật là CheckResult/CriterionVerdict/Verdict — đã hiệu chỉnh)* | cao |
| `decompose_agent/accept.py:56-72` | `Accept` (decorator 56, class 57) và `Reject` (decorator 65, class 66) là frozen dataclass — verdict bất biến về việc chấp nhận phân rã. *(plan ghi 32-48; tên thật Accept/Reject; dòng 32 là `_scope_tokens`, không phải dataclass — đã hiệu chỉnh)* | trung bình |
| `decompose_agent/worker.py:69-86` | `FourCell` `@dataclass(frozen=True)` — context 4-cell bất biến truyền cho worker; worker không sửa được. *(plan ghi "WorkerRequest" 69-90; class thật là FourCell 69-86 — đã hiệu chỉnh)* | cao |
| `control/events.py:32-130` | `Actor` (33), `TraceContext` (54), `RedactionInfo` (86), `RuntimeEvent` (114) — đều `@dataclass(frozen=True)`, bản ghi event bất biến, chia sẻ cho subscriber, không sửa sau khi tạo. *(plan ghi TaskStarted/TaskFailed... — tên thật như trên, đã hiệu chỉnh)* | cao |
| `control/commands.py:33-150` | `IssuedBy` (34), `RuntimeCommand` (62), `CommandAck` (110) — frozen command/ack payload bất biến; nhiều consumer dùng chung không mutate. *(plan ghi Command/DelegateCommand — tên thật như trên, đã hiệu chỉnh)* | cao |
| `control/checkpoint.py:27-60` | `RuntimeCheckpoint` (28) `@dataclass(frozen=True)` — snapshot trạng thái run bất biến, an toàn cache/serialize/chia sẻ khi restore. *(plan ghi Checkpoint/CheckpointState — tên thật RuntimeCheckpoint, đã hiệu chỉnh)* | cao |
| `roles/spec.py:22-70` | `TestOwnership` (23), `RoleView` (32), `RoleSpec` (42) — frozen dataclass; mỗi role có một spec bất biến chia sẻ qua nhiều lần khởi tạo session. *(plan ghi RoleSpec/RoleIdentity/RoleDescriptor — tên thật như trên, đã hiệu chỉnh)* | cao |
| `rag/ports.py:8-50` | `Chunk` (9), `Hit` (17), `RagConfig` (40) — frozen dataclass; bất biến, hashable, an toàn đẩy qua pipeline async + cache. *(plan ghi RAGRequest/RAGResult/RAGMetadata — tên thật như trên, đã hiệu chỉnh)* | cao |
| `safety/policy.py:41-90` | `PolicyDecision` (42) `@dataclass(frozen=True)` — quyết định policy bất biến; một khi tạo không sửa được, giữ tính toàn vẹn audit. *(plan ghi PolicyViolation — tên thật PolicyDecision, đã hiệu chỉnh)* | trung bình |
| `skills/spec.py:26-80` | `SkillSpec` `@dataclass(frozen=True)` — spec skill bất biến, chia sẻ qua mọi lần gọi skill. | cao |
| `drag_from_zero/dragzero/events.py:37-75` | `Event` (38) `@dataclass(frozen=True)` — bản ghi event bất biến, an toàn chia sẻ/replay qua các lần chạy mô phỏng. *(plan ghi EventRecord — tên thật Event, đã hiệu chỉnh)* | trung bình |
| `drag_from_zero/dragzero/capability.py:24-60` | `Capability` (25) `@dataclass(frozen=True)` — nhiều task tham chiếu cùng một capability spec mà không tạo instance mới. | trung bình |
| `supervisor/contracts.py:21-95` | `AgentSelection` (22), `SessionPlan` (28), `AgentAssignment` (40), `OrchestratorDecision` (48), `ContextPacket` (60) — frozen contract dataclass; spec ủy thác bất biến chia sẻ suốt vòng đời supervisor. *(plan ghi DelegationContract — tên thật như trên, đã hiệu chỉnh)* | trung bình |
| `tests_audit/test_core_edges_rigor.py:326-363` | Test pin contract immutability của Flyweight: `test_deep_freeze_of_set_becomes_frozenset_recursively` (326), `test_deep_freeze_idempotent_and_value_passthrough` (336), `test_kernel_freeze_deep_freezes_set_valued_config_through_session_start` (346), `test_kernel_freeze_is_idempotent` (363). | cao |
