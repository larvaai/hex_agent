# Class Encyclopedia - core_agent

Pham vi: tat ca `class` trong cac file `*.py` cua project, gom ca fake class trong `tests/`.

Quy uoc:
- "Duoc khoi tao boi class/hàm nào" = noi co loi goi truc tiep dang `ClassName(...)`. Neu constructor duoc goi trong mot method thi ghi ten class chua method do.
- "Xuat hien" = noi class duoc dinh nghia, import/re-export, dung lam annotation, bat exception, hoac duoc goi.
- "Bien/thuoc tinh" = dataclass field, class variable, hoac `self.<attr>` duoc khai bao/doc/ghi trong code.

## class EventBus

- Dinh nghia: `core/events.py:9`
- EventBus duoc khoi tao boi class/hàm nào:
  - Khong co class nao truc tiep khoi tao.
  - `core.bootstrap.build_kernel()` tao `EventBus()` va gan vao `AgentKernel.events`.
- EventBus xuat hien o nhung class/hàm nao:
  - `core.kernel.AgentKernel`: field `events: EventBus`.
  - `core.bootstrap.build_kernel()`: constructor `EventBus()`.
  - `observability.event_log.attach_to_bus(logger, bus)`: parameter `bus: EventBus`.
- Cac bien cua EventBus duoc su dung tai:
  - `_subscribers`: `EventBus.__init__()` khoi tao list; `EventBus.subscribe()` append subscriber; `EventBus.publish()` lap qua subscriber va goi callback.

## class AgentKernel

- Dinh nghia: `core/kernel.py:14`
- AgentKernel duoc khoi tao boi class/hàm nào:
  - Khong co class nao truc tiep khoi tao.
  - `core.bootstrap.build_kernel()` tao `AgentKernel(registry=..., events=..., state=..., config=...)`.
- AgentKernel xuat hien o nhung class/hàm nao:
  - `core.bootstrap.build_kernel()` va `core.bootstrap.create_kernel()` dung return type/constructor.
  - `features.loader.install_configured_features(kernel, config)`.
  - `features.example_echo.install(kernel)`.
  - `toolbox.feature.install(kernel)`.
  - `graph.runtime.run_agent(..., kernel, ...)`.
  - `graph.nodes.tool_node(action, kernel)`.
  - Tests tao kernel qua `build_kernel()`/`create_kernel()` roi goi method cua kernel.
- Cac bien cua AgentKernel duoc su dung tai:
  - `registry`: khai bao field; `AgentKernel.execute_tool()` goi `resolve_tool()`; `AgentKernel.describe_capabilities()` goi `list_features()`/`list_tools()`; `features.example_echo.install()` va `toolbox.feature.install()` goi `kernel.registry.register_*`; tests goi `k.registry.has_tool()`.
  - `events`: khai bao field; `AgentKernel.accept_task()` va `AgentKernel.execute_tool()` goi `publish()`; `graph.runtime.run_agent()` va `run_smoke.main()` truyen `kernel.events` vao `attach_to_bus()`; tests subscribe de kiem tra event.
  - `state`: khai bao field; `AgentKernel.accept_task()` goi `state.set("current_task", task)`.
  - `config`: khai bao field, hien chua co noi doc truc tiep trong code.

## class ToolPort

- Dinh nghia: `core/ports.py:10`
- ToolPort duoc khoi tao boi class/hàm nào:
  - Khong duoc khoi tao. Day la `Protocol` runtime-checkable, dung nhu hop dong kieu.
- ToolPort xuat hien o nhung class/hàm nao:
  - `core.ports.ToolPort`: dinh nghia contract `name` va `execute(request)`.
  - Cac tool thuc te (`NullToolPort`, `EchoTool`, `FsRead`, `FsWrite`, `FsList`, `Terminal`, `SafeToolPort`) lam theo contract nay bang duck typing, khong ke thua truc tiep.
- Cac bien cua ToolPort duoc su dung tai:
  - `name`: khai bao la field contract trong `ToolPort`; kernel doc `getattr(executor, "name", ...)` trong `AgentKernel.execute_tool()`.

## class ToolResolution

- Dinh nghia: `core/registry.py:9`
- ToolResolution duoc khoi tao boi class/hàm nào:
  - `CapabilityRegistry.resolve_tool()` khoi tao `ToolResolution(...)` trong 3 nhanh: exact match, fallback, va null tool.
- ToolResolution xuat hien o nhung class/hàm nao:
  - `core.registry.CapabilityRegistry.resolve_tool()` return annotation va constructor.
  - `core.kernel.AgentKernel.execute_tool()` nhan ket qua `resolution = registry.resolve_tool(...)`.
- Cac bien cua ToolResolution duoc su dung tai:
  - `executor`: `AgentKernel.execute_tool()` goi `resolution.executor.execute(request)` va doc ten executor cho metadata.
  - `feature`: `AgentKernel.execute_tool()` truyen vao `CapabilityResult.from_raw(feature=resolution.feature, ...)`.

## class NullToolPort

- Dinh nghia: `core/registry.py:14`
- NullToolPort duoc khoi tao boi class/hàm nào:
  - `CapabilityRegistry.__init__()` tao `NullToolPort()` neu khong nhan `null_tool`.
- NullToolPort xuat hien o nhung class/hàm nao:
  - `CapabilityRegistry.__init__()` giu instance fallback trong `_null`.
  - `CapabilityRegistry.resolve_tool()` tra `_null` khi khong tim thay tool va khong co fallback.
  - `AgentKernel.execute_tool()` se goi `execute()` cua instance nay thong qua `ToolResolution.executor`.
- Cac bien cua NullToolPort duoc su dung tai:
  - `name`: class variable `"null_tool"`, duoc kernel doc bang `getattr(executor, "name", ...)` khi tao metadata.
  - `request.name`: `NullToolPort.execute()` doc de tra ve loi `missing_capability`.

## class CapabilityRegistry

- Dinh nghia: `core/registry.py:28`
- CapabilityRegistry duoc khoi tao boi class/hàm nào:
  - Khong co class nao truc tiep khoi tao.
  - `core.bootstrap.build_kernel()` tao `CapabilityRegistry()` cho `AgentKernel.registry`.
- CapabilityRegistry xuat hien o nhung class/hàm nao:
  - `core.kernel.AgentKernel`: field `registry: CapabilityRegistry`.
  - `core.bootstrap.build_kernel()`: constructor.
  - `AgentKernel.execute_tool()` goi `registry.resolve_tool()`.
  - `AgentKernel.describe_capabilities()` goi `registry.list_features()` va `registry.list_tools()`.
  - `features.example_echo.install()` va `toolbox.feature.install()` thao tac qua `kernel.registry`.
- Cac bien cua CapabilityRegistry duoc su dung tai:
  - `_tools`: `__init__()` khoi tao; `register_tool()` ghi; `resolve_tool()`, `has_tool()`, `list_tools()` doc.
  - `_features`: `__init__()` khoi tao; `register_feature()` ghi; `list_features()` doc.
  - `_tool_features`: `__init__()` khoi tao; `register_tool()` ghi khi co `feature_name`; `resolve_tool()` va `list_tools()` doc.
  - `_fallback`: `__init__()` khoi tao; `set_fallback_tool_executor()` ghi; `resolve_tool()` doc.
  - `_fallback_feature`: `__init__()` khoi tao; `set_fallback_tool_executor()` ghi; `resolve_tool()` doc.
  - `_null`: `__init__()` khoi tao; `resolve_tool()` tra ve khi khong co tool.

## class TaskEnvelope

- Dinh nghia: `core/schemas.py:12`
- TaskEnvelope duoc khoi tao boi class/hàm nào:
  - `AgentKernel.accept_task()` khoi tao `TaskEnvelope(user_request=..., context=...)`.
- TaskEnvelope xuat hien o nhung class/hàm nao:
  - `core.kernel.AgentKernel.accept_task()` return annotation va constructor.
  - `core.schemas.TaskEnvelope`: dataclass schema.
- Cac bien cua TaskEnvelope duoc su dung tai:
  - `user_request`: dataclass field, duoc truyen khi tao task.
  - `context`: dataclass field, duoc truyen khi tao task.
  - `metadata`: dataclass field, chua co noi doc/ghi ngoai schema.
  - `task_id`: dataclass field auto UUID; `AgentKernel.accept_task()` doc de publish event `task.accepted`.

## class ToolRequest

- Dinh nghia: `core/schemas.py:20`
- ToolRequest duoc khoi tao boi class/hàm nào:
  - `AgentKernel.execute_tool()` khoi tao `ToolRequest(name=tool_name, args=args or {})`.
- ToolRequest xuat hien o nhung class/hàm nao:
  - `core.ports.ToolPort.execute(request)`.
  - `core.registry.NullToolPort.execute(request)`.
  - `features.example_echo.EchoTool.execute(request)`.
  - `safety.policy.SafeToolPort.execute(request)`.
  - `toolbox.filesystem.FsRead/FsWrite/FsList.execute(request)`.
  - `toolbox.terminal.Terminal.execute(request)`.
  - `core.kernel.AgentKernel.execute_tool()`.
- Cac bien cua ToolRequest duoc su dung tai:
  - `name`: `AgentKernel.execute_tool()` publish event/resolve tool/metadata; `NullToolPort.execute()` tao error; `SafeToolPort.execute()` check policy va tao response loi.
  - `args`: `AgentKernel.execute_tool()` publish event; `EchoTool.execute()` echo args; `SafeToolPort.execute()` dua vao policy; `FsRead/FsWrite/FsList.execute()` doc `path`/`content`; `Terminal.execute()` doc `argv`/`timeout`.
  - `request_id`: `AgentKernel.execute_tool()` publish event va ghi metadata.

## class CapabilityResult

- Dinh nghia: `core/schemas.py:31`
- CapabilityResult duoc khoi tao boi class/hàm nào:
  - `AgentKernel.execute_tool()` goi `CapabilityResult.from_raw(...).as_dict()`.
  - Ben trong `CapabilityResult.from_raw()`, classmethod goi `cls(...)` de tao instance envelope.
- CapabilityResult xuat hien o nhung class/hàm nao:
  - `core.kernel.AgentKernel.execute_tool()`: chuan hoa moi raw tool result.
  - `core.schemas.is_capability_result()` va `CapabilityResult.from_raw()`: kiem tra/tao envelope.
- Cac bien cua CapabilityResult duoc su dung tai:
  - `ok`: `as_dict()` xuat ra envelope.
  - `capability`: `as_dict()` xuat ra envelope.
  - `feature`: `as_dict()` xuat ra envelope.
  - `data`: `as_dict()` xuat ra envelope.
  - `error`: `as_dict()` xuat ra envelope.
  - `metadata`: `as_dict()` xuat ra envelope.

## class FeatureDescriptor

- Dinh nghia: `core/schemas.py:82`
- FeatureDescriptor duoc khoi tao boi class/hàm nào:
  - Khong co class nao truc tiep khoi tao.
  - Module top-level `features.example_echo` tao hang `FEATURE = FeatureDescriptor(...)`.
  - Module top-level `toolbox.feature` tao hang `FEATURE = FeatureDescriptor(...)`.
- FeatureDescriptor xuat hien o nhung class/hàm nao:
  - `core.registry.CapabilityRegistry.__init__()`: type cua `_features`.
  - `CapabilityRegistry.register_feature(descriptor)`.
  - `features.example_echo.install()` va `toolbox.feature.install()` truyen `FEATURE` vao registry.
  - `CapabilityRegistry.list_features()` goi `descriptor.as_dict()`.
- Cac bien cua FeatureDescriptor duoc su dung tai:
  - `name`: `CapabilityRegistry.register_feature()` lam key; `as_dict()` xuat; feature install dung lam `feature_name`.
  - `version`: `as_dict()` xuat.
  - `capabilities`: `as_dict()` xuat; `features.example_echo.install()` dung de `register_tools()`.
  - `enabled`: `as_dict()` xuat.
  - `description`: `as_dict()` xuat.

## class StateStore

- Dinh nghia: `core/state.py:7`
- StateStore duoc khoi tao boi class/hàm nào:
  - Khong co class nao truc tiep khoi tao.
  - `core.bootstrap.build_kernel()` tao `StateStore()` cho `AgentKernel.state`.
- StateStore xuat hien o nhung class/hàm nao:
  - `core.kernel.AgentKernel`: field `state: StateStore`.
  - `core.bootstrap.build_kernel()`: constructor.
  - `AgentKernel.accept_task()` goi `state.set(...)`.
- Cac bien cua StateStore duoc su dung tai:
  - `_data`: `StateStore.__init__()` khoi tao dict; `get()` doc; `set()` ghi; `as_dict()` copy ra dict moi.

## class Budget

- Dinh nghia: `discipline/budget.py:9`
- Budget duoc khoi tao boi class/hàm nào:
  - Khong co class nao truc tiep khoi tao.
  - `graph.runtime.run_agent()` tao `Budget(max_steps=max_steps)`.
  - Tests `tests/test_discipline.py` tao `Budget(...)` de kiem tra parse budget va same-tool budget.
- Budget xuat hien o nhung class/hàm nao:
  - `graph.runtime.run_agent()` dung loop budget.
  - `tests.test_discipline.test_budget_parse_does_not_consume_steps()`.
  - `tests.test_discipline.test_budget_same_tool()`.
  - `discipline.__init__` re-export `Budget`.
- Cac bien cua Budget duoc su dung tai:
  - `max_steps`: `step_exceeded()` doc.
  - `max_parse_errors`: `parse_exceeded()` doc.
  - `max_same_tool_calls`: `same_tool_exceeded()` doc.
  - `steps`: `record_step()` tang; `step_exceeded()` va test doc.
  - `parse_errors`: `record_parse_error()` tang; `parse_exceeded()` doc.
  - `_tool_calls`: `record_tool_call()` cap nhat dem theo key; `same_tool_exceeded()` doc.

## class JsonGateError

- Dinh nghia: `discipline/json_gate.py:9`
- JsonGateError duoc khoi tao boi class/hàm nào:
  - Khong co class nao truc tiep khoi tao.
  - `discipline.json_gate.parse_action()` raise `JsonGateError(...)` khi khong parse duoc JSON object hoac thieu field `action`.
- JsonGateError xuat hien o nhung class/hàm nao:
  - `graph.nodes.agent_node()` catch `JsonGateError` va doi thanh action `retry`.
  - `discipline.json_gate.build_retry_message(error)` doc `error.stage`.
  - `tests/test_discipline.py` dung `pytest.raises(JsonGateError)`.
  - `discipline.__init__` re-export `JsonGateError`.
- Cac bien cua JsonGateError duoc su dung tai:
  - `stage`: `JsonGateError.__init__()` ghi; `build_retry_message()` doc; test doc `ei.value.stage`.
  - `candidate`: `JsonGateError.__init__()` ghi de giu output ung vien bi loi; hien chua co noi doc ngoai constructor.

## class EchoTool

- Dinh nghia: `features/example_echo.py:16`
- EchoTool duoc khoi tao boi class/hàm nào:
  - Khong co class nao truc tiep khoi tao.
  - `features.example_echo.install(kernel)` tao `EchoTool()` va dang ky qua `kernel.registry.register_tools(...)`.
- EchoTool xuat hien o nhung class/hàm nao:
  - `features.example_echo.install()`: constructor va dang ky tool.
  - Khi runtime, `AgentKernel.execute_tool()` goi `execute()` cua instance nay sau khi registry resolve tool `echo`.
- Cac bien cua EchoTool duoc su dung tai:
  - `name`: class variable `"echo_tool"`, kernel co the doc de ghi metadata executor.
  - `request.args`: `EchoTool.execute()` doc va tra ve trong response `echo`.

## class AgentState

- Dinh nghia: `graph/state.py:9`
- AgentState duoc khoi tao boi class/hàm nào:
  - Khong co class nao truc tiep khoi tao.
  - `graph.runtime.run_agent()` tao `AgentState(task=task)`.
- AgentState xuat hien o nhung class/hàm nao:
  - `graph.runtime.run_agent()` tao va cap nhat state trong loop.
  - `graph.nodes.agent_node(state, ...)` doc `state.task` va `state.messages`.
  - `graph.__init__` re-export `AgentState`.
- Cac bien cua AgentState duoc su dung tai:
  - `task`: `agent_node()` doc de tao user prompt.
  - `messages`: `agent_node()` doc; `run_agent()` append retry/observation/finish-block message.
  - `step`: `run_agent()` tang, ghi vao event, va tra ve summary.
  - `final`: `run_agent()` set khi ket thuc hoac bi chan budget; doc de tinh status va output.
  - `last_action`: field khai bao, hien chua duoc doc/ghi ngoai schema.
  - `code_changed`: `run_agent()` doc de goi `check_finish(...)`.
  - `validation_passed`: `run_agent()` doc de goi `check_finish(...)`.

## class EventLogger

- Dinh nghia: `observability/event_log.py:35`
- EventLogger duoc khoi tao boi class/hàm nào:
  - Khong co class nao truc tiep khoi tao.
  - `graph.runtime.run_agent()` tao `EventLogger()` neu caller khong truyen logger.
  - `run_smoke.main()` tao `EventLogger()`.
  - `tests/test_observability.py` tao `EventLogger(run_id=...)`.
- EventLogger xuat hien o nhung class/hàm nao:
  - `graph.runtime.run_agent(..., logger: EventLogger | None = None)`.
  - `observability.event_log.attach_to_bus(logger: EventLogger, bus: EventBus)`.
  - `run_smoke.main()`.
  - `tests.test_observability.test_run_writes_events_and_summary()`.
  - `tests.test_observability.test_disabled_logging_writes_nothing()`.
  - `observability.__init__` re-export `EventLogger`.
- Cac bien cua EventLogger duoc su dung tai:
  - `enabled`: `__init__()` tinh tu env/argument; `emit()` va `finish()` doc de quyet dinh co ghi file hay khong.
  - `run_id`: `__init__()` tao/giam giu id; `emit()` ghi vao event; `finish()` ghi vao summary va index.
  - `seq`: `__init__()` khoi tao; `emit()` tang va ghi `sequence`.
  - `metrics`: `__init__()` khoi tao; `count()` cap nhat; `finish()` copy vao summary.
  - `run_dir`: `__init__()` tao path va mkdir; `finish()` ghi `summary.json`.
  - `events_path`: `__init__()` tao path; `emit()` append JSONL vao file nay.
  - Bien local/parameter kieu EventLogger: `logger` trong `run_agent()`, `run_smoke.main()`, `attach_to_bus()`, va tests duoc dung de goi `emit()`, `count()`, `finish()`.

## class PolicyDecision

- Dinh nghia: `safety/policy.py:17`
- PolicyDecision duoc khoi tao boi class/hàm nào:
  - Khong co class nao truc tiep khoi tao.
  - `safety.policy.classify_terminal()` tao `PolicyDecision(...)` trong cac nhanh allow/block.
  - `ToolPolicy.check()` tao `PolicyDecision(...)` cho git mutation va default allow.
- PolicyDecision xuat hien o nhung class/hàm nao:
  - `classify_terminal(argv)` return annotation.
  - `ToolPolicy.check(tool_name, args)` return annotation.
  - `SafeToolPort.execute()` doc object `decision`.
  - `tests/test_safety.py` doc `allowed`/`code`.
  - `safety.__init__` re-export `PolicyDecision`.
- Cac bien cua PolicyDecision duoc su dung tai:
  - `allowed`: `SafeToolPort.execute()` doc de quyet dinh block/delegate; tests kiem tra.
  - `reason`: `SafeToolPort.execute()` dua vao `error`.
  - `code`: `SafeToolPort.execute()` dua vao `policy_code`; tests kiem tra.
  - `risk`: `SafeToolPort.execute()` dua vao `metadata.risk`.

## class ToolPolicy

- Dinh nghia: `safety/policy.py:45`
- ToolPolicy duoc khoi tao boi class/hàm nào:
  - `SafeToolPort.__init__()` tao `ToolPolicy()` neu caller khong truyen policy.
  - `toolbox.feature.install(kernel)` tao mot `policy = ToolPolicy()` dung chung cho cac wrapped tool.
  - `tests/test_safety.py` tao `ToolPolicy()` de kiem tra git mutation.
- ToolPolicy xuat hien o nhung class/hàm nao:
  - `SafeToolPort.__init__(..., policy: ToolPolicy | None = None)`.
  - `SafeToolPort.execute()` goi `self._policy.check(...)`.
  - `toolbox.feature.install()`.
  - `tests.test_safety.test_policy_blocks_git_mutation()`.
  - `safety.__init__` re-export `ToolPolicy`.
- Cac bien cua ToolPolicy duoc su dung tai:
  - ToolPolicy khong co `self.<attr>` rieng.
  - Bien local `policy` trong `toolbox.feature.install()` duoc truyen vao moi `SafeToolPort(...)`.
  - Method `check()` doc `tool_name` va `args`; voi terminal thi goi `classify_terminal(args.get("argv"))`.

## class SafeToolPort

- Dinh nghia: `safety/policy.py:58`
- SafeToolPort duoc khoi tao boi class/hàm nào:
  - Khong co class nao truc tiep khoi tao.
  - `toolbox.feature.install(kernel)` tao `SafeToolPort(tool.name, tool, policy)` cho `FsRead`, `FsWrite`, `FsList`, va `Terminal`.
- SafeToolPort xuat hien o nhung class/hàm nao:
  - `toolbox.feature.install()`: wrapper truoc khi dang ky tool vao registry.
  - `AgentKernel.execute_tool()` goi `execute()` cua instance nay khi registry resolve cac toolbox tool.
  - `safety.__init__` re-export `SafeToolPort`.
- Cac bien cua SafeToolPort duoc su dung tai:
  - `name`: `__init__()` ghi ten wrapper; kernel co the doc de ghi metadata.
  - `_inner`: `__init__()` giu tool goc; `execute()` goi `_inner.execute(request)` neu policy allow.
  - `_policy`: `__init__()` giu policy; `execute()` goi `_policy.check(request.name, request.args)`.

## class SandboxError

- Dinh nghia: `safety/sandbox.py:10`
- SandboxError duoc khoi tao boi class/hàm nào:
  - Khong co class nao truc tiep khoi tao.
  - `safety.sandbox.resolve_in_workspace()` raise `SandboxError(...)` khi path thoat khoi workspace.
- SandboxError xuat hien o nhung class/hàm nao:
  - `toolbox.filesystem.FsRead.execute()`, `FsWrite.execute()`, `FsList.execute()` catch `SandboxError`.
  - `tests.test_safety.test_sandbox_escape_blocked()` dung `pytest.raises(SandboxError)`.
  - `safety.__init__` re-export `SandboxError`.
- Cac bien cua SandboxError duoc su dung tai:
  - Khong co bien/thuoc tinh rieng; message loi duoc doc qua `str(exc)` trong cac filesystem tool.

## class _FakeChoiceMsg

- Dinh nghia: `tests/test_llm_adapter.py:5`
- _FakeChoiceMsg duoc khoi tao boi class/hàm nào:
  - `_FakeClient._Completions.create()` tao `_FakeChoiceMsg(outer.content)`.
- _FakeChoiceMsg xuat hien o nhung class/hàm nao:
  - `tests.test_llm_adapter._FakeClient._Completions.create()`.
  - Dung de fake shape `response.choices[0].message.content` cho `llm.adapter.call_llm()`.
- Cac bien cua _FakeChoiceMsg duoc su dung tai:
  - `message`: `_FakeChoiceMsg.__init__()` gan object dong co field `content`; `llm.adapter.call_llm()` doc gian tiep qua response fake.

## class _FakeClient

- Dinh nghia: `tests/test_llm_adapter.py:10`
- _FakeClient duoc khoi tao boi class/hàm nào:
  - `tests.test_llm_adapter.test_injected_client_json_mode()`.
  - `tests.test_llm_adapter.test_json_mode_off()`.
  - `tests.test_llm_adapter.test_error_returns_structured_final()`.
- _FakeClient xuat hien o nhung class/hàm nao:
  - Cac test tren truyen instance vao `adapter.call_llm(..., client=fake)`.
  - Chua nested class `_Completions` de fake `chat.completions.create(...)`.
- Cac bien cua _FakeClient duoc su dung tai:
  - `content`: `__init__()` ghi; `_Completions.create()` doc qua closure `outer.content`.
  - `boom`: `__init__()` ghi; `_Completions.create()` doc de raise `RuntimeError("boom")` khi can fake error.
  - `kwargs`: `__init__()` khoi tao; `_Completions.create()` ghi kwargs; tests doc `fake.kwargs`.
  - `chat`: `__init__()` gan object fake co `completions`; `llm.adapter.call_llm()` doc `client.chat.completions.create(...)`.

## class _FakeClient._Completions

- Dinh nghia: `tests/test_llm_adapter.py:17`
- _Completions duoc khoi tao boi class/hàm nào:
  - `_FakeClient.__init__()` tao `_Completions()` va gan vao `self.chat.completions`.
- _Completions xuat hien o nhung class/hàm nao:
  - `_FakeClient.__init__()`.
  - `llm.adapter.call_llm()` goi gian tiep `fake.chat.completions.create(...)`.
- Cac bien cua _Completions duoc su dung tai:
  - Khong co `self.<attr>` rieng.
  - Method `create(**kwargs)` ghi/doc cac bien cua outer `_FakeClient`: `outer.kwargs`, `outer.boom`, `outer.content`.

## class FsRead

- Dinh nghia: `toolbox/filesystem.py:10`
- FsRead duoc khoi tao boi class/hàm nào:
  - Khong co class nao truc tiep khoi tao.
  - `toolbox.feature.install(kernel)` tao `FsRead()` trong tuple tool, boc bang `SafeToolPort`, roi dang ky vao registry.
- FsRead xuat hien o nhung class/hàm nao:
  - `toolbox.feature.install()`.
  - Runtime: `AgentKernel.execute_tool("fs_read", ...)` resolve ra `SafeToolPort`, sau do delegate vao `FsRead.execute()`.
  - `tests/test_toolbox.py` goi tool name `"fs_read"` qua kernel.
- Cac bien cua FsRead duoc su dung tai:
  - `name`: class variable `"fs_read"`; `toolbox.feature.install()` doc `tool.name` de dang ky wrapper va registry.
  - `request.args["path"]`: `FsRead.execute()` doc de resolve path trong workspace.

## class FsWrite

- Dinh nghia: `toolbox/filesystem.py:23`
- FsWrite duoc khoi tao boi class/hàm nào:
  - Khong co class nao truc tiep khoi tao.
  - `toolbox.feature.install(kernel)` tao `FsWrite()` trong tuple tool, boc bang `SafeToolPort`, roi dang ky vao registry.
- FsWrite xuat hien o nhung class/hàm nao:
  - `toolbox.feature.install()`.
  - Runtime: `AgentKernel.execute_tool("fs_write", ...)` resolve ra `SafeToolPort`, sau do delegate vao `FsWrite.execute()`.
  - `tests/test_toolbox.py` va `tests/test_graph.py` goi tool name `"fs_write"` qua kernel/agent loop.
- Cac bien cua FsWrite duoc su dung tai:
  - `name`: class variable `"fs_write"`; `toolbox.feature.install()` doc `tool.name`.
  - `request.args["path"]`: `FsWrite.execute()` doc de resolve path trong workspace.
  - `request.args["content"]`: `FsWrite.execute()` doc de ghi file va tinh so byte/ky tu tra ve.

## class FsList

- Dinh nghia: `toolbox/filesystem.py:37`
- FsList duoc khoi tao boi class/hàm nào:
  - Khong co class nao truc tiep khoi tao.
  - `toolbox.feature.install(kernel)` tao `FsList()` trong tuple tool, boc bang `SafeToolPort`, roi dang ky vao registry.
- FsList xuat hien o nhung class/hàm nao:
  - `toolbox.feature.install()`.
  - Runtime: `AgentKernel.execute_tool("fs_list", ...)` resolve ra `SafeToolPort`, sau do delegate vao `FsList.execute()`.
- Cac bien cua FsList duoc su dung tai:
  - `name`: class variable `"fs_list"`; `toolbox.feature.install()` doc `tool.name`.
  - `request.args["path"]`: `FsList.execute()` doc; mac dinh `"."` neu khong truyen path.

## class Terminal

- Dinh nghia: `toolbox/terminal.py:11`
- Terminal duoc khoi tao boi class/hàm nào:
  - Khong co class nao truc tiep khoi tao.
  - `toolbox.feature.install(kernel)` tao `Terminal()` trong tuple tool, boc bang `SafeToolPort`, roi dang ky vao registry.
- Terminal xuat hien o nhung class/hàm nao:
  - `toolbox.feature.install()`.
  - Runtime: `AgentKernel.execute_tool("terminal_run", ...)` resolve ra `SafeToolPort`, policy check truoc, sau do delegate vao `Terminal.execute()`.
  - `tests/test_toolbox.py` goi tool name `"terminal_run"` qua kernel.
- Cac bien cua Terminal duoc su dung tai:
  - `name`: class variable `"terminal_run"`; `toolbox.feature.install()` doc `tool.name`.
  - `request.args["argv"]`: `Terminal.execute()` doc de chay subprocess khong qua shell.
  - `request.args["timeout"]`: `Terminal.execute()` doc va clamp trong khoang 1..30 giay.

---

# Phu luc: y nghia tung thanh phan trong logic toan project

## Logic tong quan de doc project

Project `core_agent` dang giai quyet mot bai toan chinh: tao mot agent co the nhan task, biet danh sach tool dang co, goi tool an toan, chuan hoa ket qua tool, dua ket qua quay lai vong lap agent, ghi log quan sat, roi ket thuc co kiem soat.

Luong tho:

```text
config/features.yaml
  -> load_config()
  -> build_kernel()
       -> CapabilityRegistry: so dang ky feature/tool
       -> EventBus: kenh phat event
       -> StateStore: kho state nho cua kernel
       -> AgentKernel: loi dieu phoi
  -> install_configured_features()
       -> feature.install(kernel)
       -> register FeatureDescriptor
       -> register tool executor
       -> voi toolbox: boc tool bang SafeToolPort + ToolPolicy
  -> run_agent()
       -> AgentState + Budget + EventLogger
       -> accept_task()
       -> agent_node(): goi LLM va parse JSON action
       -> tool_node(): goi kernel.execute_tool()
       -> ToolRequest
       -> CapabilityRegistry.resolve_tool()
       -> ToolResolution(executor, feature)
       -> executor.execute(request)
            -> SafeToolPort.check policy
            -> tool goc execute
       -> CapabilityResult.from_raw().as_dict()
       -> EventBus.publish()
       -> EventLogger.emit/count()
       -> condense(result)
       -> lap lai hoac check_finish()
  -> EventLogger.finish()
```

Noi ngan gon: config tao ra kernel; feature nap tool vao registry; agent loop quyet dinh goi tool nao; kernel bien moi loi goi tool thanh `ToolRequest`, chay executor, chuan hoa thanh `CapabilityResult`, phat event; observability nghe event va ghi log; discipline giu vong lap khong vuot ngan sach va khong ket thuc sai luc.

## Nhom composition: khoi dong va lap rap he thong

- `load_config(config_path)`: doc `config/features.yaml`. Ham nay la cong vao cua cau hinh: feature nao bat/tat, module nao can import. Neu file khong ton tai thi tra ve `{"features": {}}` de kernel van khoi dong duoc.
- `build_kernel(config)`: composition root cua project. No tao `CapabilityRegistry`, `EventBus`, `StateStore`, roi dong goi vao `AgentKernel`. Sau do goi `install_configured_features()` de nap tools. Day la noi tu cac cuc roi rac thanh mot he agent co the chay.
- `create_kernel(config_path)`: shortcut cho runtime/smoke test. No ket hop `load_config()` va `build_kernel()`, nghia la "tao kernel theo config tren dia".
- `install_configured_features(kernel, config)`: doc danh sach feature enabled trong config, import module bang `importlib`, tim ham `install(kernel)`, roi goi ham do. Ham nay la cau noi giua config dang text va code plugin that su.
- Bien `DEFAULT_CONFIG_PATH`: duong dan mac dinh toi `config/features.yaml`; giup `create_kernel()` khong can caller truyen path.
- Bien `PROJECT_DIR`: xac dinh root project tu vi tri file Python; nhieu module dung no de suy ra config, workspace, hoac thu muc run log.

## Nhom core: hop dong va loi dieu phoi

- `AgentKernel`: trung tam thuc thi. Kernel khong biet chi tiet tool nao lam gi; no chi biet registry, events, state va schema. Y nghia cua no la giu loi he thong nho, on dinh: nhan task, resolve tool, chay tool, chuan hoa ket qua, phat event.
- `AgentKernel.accept_task(user_request, context)`: bien yeu cau nguoi dung thanh `TaskEnvelope`, luu vao `StateStore`, va phat event `task.accepted`. Day la diem bat dau logic cua mot task trong kernel.
- `AgentKernel.execute_tool(tool_name, args)`: duong chay quan trong nhat cua tool. Ham nay tao `ToolRequest`, phat `tool.requested`, hoi registry lay executor, goi executor, bat loi neu tool crash, ep ket qua ve dict, boc thanh `CapabilityResult`, phat `tool.completed` hoac `tool.failed`, roi tra ve envelope chuan.
- `AgentKernel.describe_capabilities()`: tra ve danh sach feature va tool dang duoc registry biet. Ham nay la "xem menu nang luc" cua agent.
- `CapabilityRegistry`: so dang ky cua toan bo tool layer. Neu coi project la mot may chay tool, registry la bang tra cuu: tool name nao ung voi executor nao, tool do thuoc feature nao.
- `CapabilityRegistry.register_feature(descriptor)`: ghi nhan feature o muc metadata. No khong chay tool, chi lam cho he thong biet feature ton tai.
- `CapabilityRegistry.register_tool(name, executor, feature_name)`: gan mot ten tool voi object co `.execute()`. Day la luc tool tro thanh goi duoc boi kernel.
- `CapabilityRegistry.register_tools(names, executor, feature_name)`: dang ky nhieu alias/name cho cung mot executor. Vi du `example_echo` dang ky capability `"echo"` cho `EchoTool()`.
- `CapabilityRegistry.set_fallback_tool_executor(executor, feature_name)`: dat executor du phong neu tool name khong match exact. Hien tai logic chinh thuong dung null tool neu khong co fallback.
- `CapabilityRegistry.resolve_tool(name)`: ham quyet dinh executor that su. Thu tu: exact tool -> fallback -> `NullToolPort`. Ket qua luon la `ToolResolution`, giup kernel khong can xu ly `None`.
- `CapabilityRegistry.has_tool(name)`: dung cho test/kiem tra nhanh mot tool da duoc nap chua.
- `CapabilityRegistry.list_tools()` va `list_features()`: bien registry thanh du lieu co the hien thi/inspect.
- `ToolResolution`: cap ket qua resolve gom `executor` va `feature`. No nho nhung quan trong vi kernel can ca object de chay va ten feature de ghi metadata vao envelope.
- `NullToolPort`: executor an toan khi tool khong ton tai. Thay vi crash, no tra ve ket qua `ok=False`, `missing_capability=True`. Day la co che degrade nhe cua kernel.
- `ToolPort`: protocol mo ta contract toi thieu cua moi tool: co `name` va `execute(ToolRequest) -> dict`. Code dung duck typing, nen cac tool khong can ke thua truc tiep, chi can dung hinh dang.
- `EventBus`: kenh pub/sub cuc nho. Kernel publish event, observability subscribe. No giup core khong phu thuoc vao logger cu the.
- `EventBus.subscribe(fn)`: gan listener vao bus. `attach_to_bus()` dung ham nay de noi logger vao kernel events.
- `EventBus.publish(topic, payload)`: phat event cho moi subscriber. Neu observer loi, bus nuot exception de logging khong lam hong runtime.
- `StateStore`: kho key/value in-memory cua kernel. Hien tai nho `current_task`, ve sau co the mo rong de luu run state ma khong can thay doi interface kernel.
- `StateStore.get/set/as_dict()`: API nho cho state. `set()` la cai kernel dang dung trong `accept_task()`.

## Nhom schema: dinh dang du lieu chay qua he thong

- `TaskEnvelope`: goi yeu cau nguoi dung thanh object co `user_request`, `context`, `metadata`, `task_id`. No bien input tu "string roi" thanh mot task co danh tinh.
- `ToolRequest`: goi mot loi goi tool thanh `name`, `args`, `request_id`. Moi tool nhan cung mot dang request, nen kernel/tool layer noi chuyen bang mot hop dong thong nhat.
- `CapabilityResult`: envelope chuan cho moi ket qua tool. Day la cau tra loi cho van de "moi tool tra ve shape khac nhau thi tang tren doc sao?". Kernel dung class nay de ep moi raw result thanh `ok/capability/feature/data/error/metadata`.
- `CapabilityResult.from_raw(...)`: ham chuan hoa. Neu tool da tra envelope chuan thi merge metadata; neu tool tra dict tho thi tach `ok/error/metadata`, phan con lai vao `data`.
- `CapabilityResult.as_dict()`: bien dataclass thanh dict de graph/LLM/log co the serialize va doc de dang.
- `FeatureDescriptor`: mo ta feature/plugin: ten, version, capabilities, enabled, description. No la metadata cua "goi tool".
- `FeatureDescriptor.as_dict()`: chuan hoa feature metadata cho `describe_capabilities()`.
- `is_capability_result(result)`: kiem tra dict da co du bo key envelope chua. Ham nay giup `from_raw()` biet khi nao khong can boc lai tu dau.
- Bien `_ENVELOPE_KEYS`: dinh nghia bo field toi thieu cua ket qua tool chuan. Day la "luat hinh dang" cua tool output.

## Nhom feature va toolbox: danh sach tools -> load tools

- `features.example_echo.FEATURE`: feature mau, khai bao capability `"echo"`. No chung minh pattern plugin: co metadata va ham `install(kernel)`.
- `features.example_echo.install(kernel)`: dang ky feature mau vao registry, roi dang ky `EchoTool()` cho capability `"echo"`.
- `EchoTool`: tool don gian tra lai args. Trong logic toan project, no la tool mau de test duong chay kernel -> registry -> executor -> envelope.
- `EchoTool.execute(request)`: doc `request.args`, tra `{"ok": True, "echo": ...}`. Kernel sau do boc phan `echo` vao `CapabilityResult.data`.
- `toolbox.feature.FEATURE`: metadata cho bo tool that gom `fs_read`, `fs_write`, `fs_list`, `terminal_run`.
- `toolbox.feature.install(kernel)`: tao `ToolPolicy()`, tao cac tool `FsRead/FsWrite/FsList/Terminal`, boc tung tool bang `SafeToolPort`, roi dang ky vao registry. Day la noi "tools duoc load" va cung la noi ap chokepoint an toan cho tool nguy hiem.
- `FsRead`: tool doc file trong workspace. Vai tro cua no la cho agent quan sat noi dung file ma van bi path-jail.
- `FsRead.execute(request)`: doc `path`, goi `resolve_in_workspace()`, check file ton tai, tra ve content.
- `FsWrite`: tool ghi file trong workspace. Vai tro cua no la cho agent thay doi artifact/code trong vung duoc phep.
- `FsWrite.execute(request)`: doc `path` va `content`, resolve path, tao parent directory, ghi text UTF-8, tra ve path va do dai content.
- `FsList`: tool liet ke file/folder trong workspace. Vai tro cua no la cho agent dieu huong filesystem truoc khi doc/ghi.
- `FsList.execute(request)`: resolve path, neu khong ton tai tra list rong, neu file tra ten file, neu folder tra danh sach entry.
- `Terminal`: tool chay command dang argv trong workspace. Vai tro cua no la cung cap kha nang test/build/kiem tra, nhung khong di qua shell.
- `Terminal.execute(request)`: validate `argv`, clamp `timeout`, chay `subprocess.run(..., shell=False)`, tra `returncode/stdout/stderr`.
- Bien `FEATURE`: o moi feature module la "manifest trong code". Registry dung no de biet feature ten gi va co capability nao.
- Bien `name` tren tung tool: ten executor/tool mac dinh. `toolbox.feature.install()` dung `tool.name` khi boc va dang ky; kernel cung doc no lam metadata executor.

## Nhom safety: chay tool nhung khong de tool pha he thong

- `workspace_dir()`: tra ve thu muc workspace duoc phep thao tac, lay tu `AGENT_WORKSPACE_DIR` hoac mac dinh `var/workspace`. Tat ca filesystem/terminal tool dua vao day.
- `resolve_in_workspace(raw_path)`: path-jail. Ham nay bien relative path thanh absolute path trong workspace, roi chan neu path thoat ra ngoai. Day la lop bao ve file system quan trong nhat.
- `SandboxError`: exception rieng cho loi path thoat workspace. `Fs*` catch loi nay va tra ket qua `ok=False`, khong de kernel crash.
- `classify_terminal(argv)`: policy rieng cho terminal command. No chan shell executable, shell token, lenh destructive, git mutation neu chua bat env cho phep.
- `ToolPolicy`: policy object tong quat cho tool. Hien tai no chu yeu quyet dinh terminal/git co duoc chay khong, nhung vi nam rieng mot class nen ve sau them policy moi khong can sua kernel.
- `ToolPolicy.check(tool_name, args)`: nhan tool name va args, tra `PolicyDecision`. Neu la terminal thi goi `classify_terminal()`, neu la git mutation thi block theo env, con lai allow.
- `PolicyDecision`: ket qua cua policy gom `allowed`, `reason`, `code`, `risk`. No bien quyet dinh an toan thanh data ro rang de `SafeToolPort` co the tra ve cho caller/log.
- `SafeToolPort`: wrapper nam giua kernel va tool that. Kernel nghi minh dang goi executor binh thuong, nhung thuc ra moi request di qua policy truoc.
- `SafeToolPort.execute(request)`: goi `_policy.check()`. Neu bi block, tra dict loi co `policy_blocked`; neu duoc allow, delegate sang `_inner.execute(request)`.
- `_truthy(name)`: helper doc env var dang boolean. No giup mo khoa hanh vi nguy hiem co chu y, nhu `AGENT_ALLOW_GIT_MUTATIONS`.
- Bien `SHELL_EXES`, `SHELL_TOKENS`, `DESTRUCTIVE_EXES`, `GIT_MUTATIONS`: danh sach rule cot loi cua policy. Day la tri thuc an toan quan trong nhat cua terminal layer.

## Nhom graph/agent loop: goi LLM -> action -> tool -> observation -> final

- `run_agent(task, kernel, llm_call, model, max_steps, logger)`: vong lap dieu phoi agent. No tao state, logger, budget, accept task, roi lap: goi LLM, parse action, chay tool hoac final, log moi buoc, va dung khi final/budget/tool-loop.
- `AgentState`: state cua mot lan chay agent. No giu `task`, lich su `messages`, so `step`, cau tra loi `final`, va flags ve validation.
- `agent_node(state, llm_call, model)`: node "suy nghi". No build prompt tu system prompt + task + observations, goi `llm_call`, roi dua output qua `parse_action()`. Neu JSON loi thi tra action `retry`.
- `tool_node(action, kernel)`: node "hanh dong". No lay `tool` va `args` tu action, goi `kernel.execute_tool()`, roi `condense()` ket qua truoc khi dua lai vao message cho LLM.
- `SYSTEM_PROMPT`: hop dong output cua LLM. No ep model chi tra mot JSON object co `action=tool` hoac `action=final`, de graph co the parse bang code thay vi doan prose.
- `Budget`: bo chan vong lap. Khong co no, agent co the lap vo han, parse sai mai, hoac goi cung tool qua nhieu lan.
- `Budget.record_step()` va `step_exceeded()`: dem so buoc agent loop.
- `Budget.record_parse_error()` va `parse_exceeded()`: dem so lan output LLM khong parse duoc. Parse error khong tinh la step thanh cong, nhung van co gioi han rieng.
- `Budget.record_tool_call()`, `same_tool_exceeded()`, `tool_key()`: phat hien loop goi lap lai cung tool voi cung args.
- `check_finish(state, finish_reason)`: finish gate. Neu code da thay doi ma chua validation pass, no chan final tru khi caller noi ro la blocker.
- `requires_validation(state)` va `has_passing_validation(state)`: helper tach logic validation thanh hai cau hoi nho.
- `condense(value, max_chars, max_list)`: rut gon ket qua tool truoc khi dua vao LLM. No giai quyet van de output tool qua dai lam tran context.
- `_truncate(text, max_chars)`: helper cat string dai va ghi ro phan bi cat.
- `parse_action(text)`: parser dau vao cua LLM action. No bo markdown fence, sua mot so loi JSON co ban, tim JSON object trong text, va dam bao co field `action`.
- `build_retry_message(error)`: tao message ngan yeu cau LLM tra lai JSON dung format.
- `JsonGateError`: tin hieu loi discipline khi output LLM khong dat hop dong JSON/action.
- `_strip_fences()`, `_repair()`, `_load_object()`: cac helper giup `parse_action()` khoan dung voi loi format pho bien cua model.

## Nhom observability: in log -> summary -> inspect

- `runs_dir()`: thu muc luu run log, lay tu `AGENT_RUNS_DIR` hoac mac dinh `var/agent_runs`.
- `_now()`: tao timestamp UTC ISO cho event log.
- `EventLogger`: logger cua mot run. No ghi event JSONL, dem metrics, va viet summary khi ket thuc.
- `EventLogger.emit(kind, **fields)`: tao mot event co `sequence`, `timestamp`, `run_id`, `kind`, roi append vao `events.jsonl` neu logging bat.
- `EventLogger.count(metric, n)`: tang counter metric. Graph dung de dem steps, llm_calls, tool_calls, parse_errors...
- `EventLogger.finish(status, **extra)`: ghi event `run_finished`, tao `summary.json`, va append run vao `index.jsonl`.
- `attach_to_bus(logger, bus)`: noi `EventBus` voi `EventLogger`. Moi kernel event se thanh `KernelEvent`; tool completed/failed se cap nhat metrics.
- `sink(topic, payload)`: nested subscriber trong `attach_to_bus()`. No la adapter chuyen event bus topic thanh log event.
- `observability.inspect._run_dirs()`: lay danh sach folder run da ghi.
- `observability.inspect._resolve(run_id)`: tim folder run theo id, hoac chon run moi nhat neu caller khong truyen id.
- `observability.inspect.list_runs()`: API doc danh sach run id.
- `observability.inspect.read_summary(run_id)`: doc `summary.json` cua run.
- `observability.inspect.read_events(run_id, kind, topic)`: doc `events.jsonl`, loc theo `kind`/`topic` neu can.
- `observability.inspect.main(argv)`: CLI nho de inspect run logs.
- Bien `_METRICS`: danh sach metric duoc logger dem. No la bo chi so cot loi de doc lai chat luong mot run: steps, llm_calls, tool_calls, failures, parse errors, policy blocks...

## Nhom LLM adapter: bien model thanh ham co the inject

- `_defaults()`: gom cau hinh LLM tu env: base URL, API key, model, max tokens, timeout. Nhờ do code khong hardcode rieng cho mot provider.
- `_get_client()`: lazy init OpenAI-compatible client. Import `openai` chi xay ra khi that su goi model, giup import module/test khong can network/client.
- `reset_client()`: xoa cached client, phuc vu test va thay doi cau hinh.
- `call_llm(messages, model, temperature, json_mode, client)`: ham goi chat completions. Neu `json_mode=True`, no yeu cau response JSON object. Neu loi, no khong raise ma tra ve JSON `final` co `finish_reason="error"`, de agent loop van ket thuc co dinh dang.
- Bien `_client`: cache module-level cho OpenAI client. Day la bien quan trong de tranh tao client moi moi lan goi.
- Cac env `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_MAX_TOKENS`, `LLM_TIMEOUT`: cau hinh runtime cua adapter.

## Nhom script/dev/test: giu project de kiem tra va tai lieu hoa

- `run_smoke.main()`: smoke test xuyen doc: tao kernel, attach logger, accept task, goi echo, goi missing tool, parse JSON co trailing comma, check finish gate, ghi summary. Day la ban chay nhanh de chung minh cac tang core/discipline/observability noi duoc voi nhau.
- `tools.gen_map.first_doc(path)`: lay docstring dong dau cua file de tao map tai lieu.
- `tools.gen_map.packages()`: liet ke package/module can dua vao map.
- `tools.gen_map.main()`: script sinh/kiem tra ban do tai lieu cua project.
- `read_file_and_list.should_exclude_path()`: bo qua file/folder khong nen dua vao context.
- `read_file_and_list.is_probably_text_file()`: phan biet file text de doc an toan.
- `read_file_and_list.safe_read_text()`: doc file text va xu ly loi decode.
- `read_file_and_list.build_tree()` va nested `walk()`: tao cay thu muc de dua vao context.
- `read_file_and_list.collect_files()`: gom file can doc.
- `read_file_and_list.main()`: script gom context project.
- Cac class fake trong `tests/test_llm_adapter.py` (`_FakeClient`, `_FakeChoiceMsg`, `_Completions`): mo phong OpenAI client response de test `call_llm()` ma khong goi network.
- Cac test function trong `tests/`: khong nam tren runtime path cua agent, nhung mo ta bat bien mong muon: kernel execute tool dung, unknown tool khong crash, safety chan path/shell/git, graph lap tool-final dung, observability ghi log dung.

## Bien quan trong nen nho khi doc logic

- `config["features"]`: nguon su that ve feature nao duoc load. Neu feature khong enabled, tool cua feature do khong vao registry.
- `FEATURE`: manifest cua tung feature module. No noi "feature nay ten gi, co capabilities nao".
- `tool.name`: ten executor/wrapper dung khi dang ky tool va ghi metadata.
- `ToolRequest.request_id`: ma truy vet mot loi goi tool tu event requested toi completed/failed.
- `CapabilityResult.metadata`: noi kernel gan thong tin phu nhu `request_id`, executor, raw keys. Rat huu ich khi debug tool output.
- `AgentState.messages`: bo nho hoi thoai ngan cua graph loop. Observation tu tool duoc append vao day de LLM co bang chung cho buoc sau.
- `AgentState.code_changed` va `validation_passed`: hai co dung de `check_finish()` quyet dinh co duoc final khong.
- `Budget._tool_calls`: bo dem chong lap tool. Neu cung tool+cung args lap qua nhieu lan, runtime dung de tranh loop vo ich.
- `EventLogger.metrics`: bang dem run-level. Khi xem summary, day la noi biet run da goi bao nhieu tool, loi bao nhieu, bi policy/finish gate chan bao nhieu.
- `AGENT_WORKSPACE_DIR`: gioi han vung file/terminal duoc thao tac.
- `AGENT_RUNS_DIR`: noi ghi event log va summary.
- `AGENT_EVENT_LOG`: bat/tat ghi file log.
- `AGENT_ALLOW_GIT_MUTATIONS`: co chu y cho phep git mutation; mac dinh policy se chan.

## Cach doc nhanh theo cau hoi "project dang lam gi?"

- "Danh sach tools o dau?" -> `FEATURE.capabilities` trong feature module, va `CapabilityRegistry._tools` sau khi install.
- "Tools duoc load luc nao?" -> `create_kernel()` -> `build_kernel()` -> `install_configured_features()` -> `feature.install(kernel)`.
- "Tool duoc chay luc nao?" -> action LLM `{"action":"tool"}` -> `tool_node()` -> `AgentKernel.execute_tool()`.
- "Ket qua tool duoc chuan hoa o dau?" -> `CapabilityResult.from_raw()` trong `AgentKernel.execute_tool()`.
- "Log duoc in/ghi o dau?" -> `EventBus.publish()` phat kernel events; `attach_to_bus()` dua vao `EventLogger.emit()`; `run_agent()` cung goi `logger.emit/count/finish()` truc tiep.
- "Agent ket thuc o dau?" -> action `final` di qua `check_finish()`; neu pass thi `run_agent()` set `state.final`, goi `EventLogger.finish()`, va tra `{final, steps, run_id}`.
- "An toan nam o dau?" -> filesystem qua `resolve_in_workspace()`; terminal/git qua `ToolPolicy`; tat ca toolbox tool di qua `SafeToolPort`.

## Neu thieu class do thi anh huong the nao?

Phan nay hieu theo nghia: xoa class khoi code hien tai ma chua viet class/logic thay the. Ket qua co the la import fail, runtime crash, mat tool, mat log, hoac chi fail test.

| Class | Neu thieu thi chuong trinh bi anh huong the nao | Output bi anh huong the nao | Ket luan rut ra |
|---|---|---|---|
| `EventBus` | `build_kernel()` khong tao duoc `AgentKernel.events`; `attach_to_bus()` cung khong co bus de subscribe. | Khong co kernel hoan chinh; khong co event `task.accepted`, `tool.requested`, `tool.completed/failed`; log quan sat bi mat. | Day la day tin hieu noi core voi observability. Neu bo, phai thay bang logging truc tiep hoac bus khac. |
| `AgentKernel` | `build_kernel()` khong tao duoc loi agent; graph/toolbox/features khong co doi tuong trung tam de dang ky va chay tool. | Khong co `accept_task()`, `execute_tool()`, `describe_capabilities()`; agent loop khong co ket qua tool de tra ve. | Day la class khong the thieu cua runtime. Moi luong tool deu di qua day. |
| `ToolPort` | Runtime hien tai gan nhu khong vo vi cac tool dung duck typing; chi code import `core.ports`/type check bi anh huong. | Output runtime gan nhu khong doi neu khong ai import `ToolPort`; nhung mat hop dong tai lieu/type cho tool. | Co the rut gon ve mat runtime, nhung khong nen bo neu muon giu contract ro rang cho tool executor. |
| `ToolResolution` | `CapabilityRegistry.resolve_tool()` khong tao duoc object tra ve; kernel khong lay duoc `executor`/`feature`. | Goi tool se crash truoc khi executor chay; khong co envelope `CapabilityResult`. | Day la object nho nhung nam dung tai diem registry -> kernel. Co the thay bang tuple/dict, nhung phai sua kernel. |
| `NullToolPort` | `CapabilityRegistry.__init__()` fail khi khong truyen `null_tool`; fallback cho missing tool bien mat. | Unknown tool thay vi tra `missing_capability=True` se lam build/resolve loi; output khong con graceful. | Day la co che an toan cho tool khong ton tai. |
| `CapabilityRegistry` | `build_kernel()` khong co noi dang ky/resolve feature/tool. | Agent khong biet co tool nao; moi output lien quan tool deu mat. | Day la "danh sach tools" cua project. Khong co registry thi khong co plugin/tool system. |
| `TaskEnvelope` | `AgentKernel.accept_task()` khong goi duoc; import `core.kernel` co the fail. | Khong co `task_id`; event `task.accepted` mat id; state `current_task` khong co object chuan. | Day la schema bien request nguoi dung thanh task co danh tinh. |
| `ToolRequest` | `AgentKernel.execute_tool()` va moi tool import schema nay se fail. | Tool khong nhan duoc `name/args/request_id`; khong co truy vet request; output tool khong sinh ra. | Day la hop dong input cua moi tool. Rat kho bo neu van muon tool layer thong nhat. |
| `CapabilityResult` | Kernel khong chuan hoa raw result; import `core.kernel` co the fail. | Output tool khong con dang chuan `ok/capability/feature/data/error/metadata`; graph/LLM/test phai doan shape rieng tung tool. | Day la lop chuan hoa output quan trong nhat. |
| `FeatureDescriptor` | Feature module va registry khong khai bao duoc metadata; `example_echo`/`toolbox` import fail. | `describe_capabilities()` khong co feature info; feature install co the fail truoc khi tool vao registry. | Day la manifest cua feature. Co the thay bang dict, nhung phai sua registry va feature modules. |
| `StateStore` | `build_kernel()` khong tao duoc `AgentKernel.state`; `accept_task()` khong luu duoc `current_task`. | Runtime co the mat state noi bo; hien tai agent output tool co the thay the bang store khac, nhung code hien tai se fail. | Day la kho state toi thieu. Quan trong cho mo rong ve sau. |
| `Budget` | `run_agent()` khong tao duoc bo dem loop. | Agent co nguy co lap vo han, parse sai qua nhieu lan, hoac goi cung tool mai; output co the treo thay vi final. | Day la guardrail cua graph loop. Kernel rieng van chay, nhung agent runtime mat an toan. |
| `JsonGateError` | `parse_action()` khong raise/catch duoc loi co cau truc; `agent_node()` mat nhanh retry. | Output LLM sai JSON co the lam runtime crash thay vi tao action `retry`; chat loop mat kha nang tu sua. | Day la tin hieu loi cua discipline layer. |
| `EchoTool` | Feature `example_echo.install()` fail hoac capability `"echo"` khong duoc dang ky. | Smoke test va test kernel voi `"echo"` fail; agent khong co tool demo tra echo. | Day la tool mau/test fixture hon la loi bat buoc cho moi runtime. |
| `AgentState` | `run_agent()` khong tao duoc state loop; `agent_node()` khong co state de doc task/messages. | Agent graph khong chay; khong co `final`, `steps`, `messages` output. | Day la state container bat buoc cua graph runtime. |
| `EventLogger` | `run_agent()` va `run_smoke()` khong tao duoc logger; `observability.__init__` fail neu re-export thieu. | Co the khong co `events.jsonl`, `summary.json`, metrics; trong code hien tai run_agent import co the fail. | Day la noi bien runtime thanh log doc lai duoc. Neu bo, can NullLogger hoac logger thay the. |
| `PolicyDecision` | `classify_terminal()`/`ToolPolicy.check()` khong tra duoc ket qua policy co cau truc. | Safety wrapper khong biet allow/block; terminal/git policy co the crash; output policy_blocked mat `code/reason/risk`. | Day la schema output cua safety policy. |
| `ToolPolicy` | `toolbox.feature.install()` va `SafeToolPort.__init__()` khong tao duoc policy. | Toolbox tool khong load duoc hoac chay khong qua gate; output an toan `policy_blocked` khong co. | Day la noi tap trung luat an toan. Khong nen bo neu co terminal/filesystem tool. |
| `SafeToolPort` | `toolbox.feature.install()` khong boc/dang ky duoc toolbox tools. | `fs_read/fs_write/fs_list/terminal_run` co the khong ton tai; neu bypass wrapper thi output tool co nhung mat policy block. | Day la chokepoint an toan giua kernel va tool that. |
| `SandboxError` | `resolve_in_workspace()` va filesystem tools khong co exception rieng de raise/catch. | Path escape co the thanh exception chung/crash; `Fs*` khong tra duoc output loi dep `ok=False`. | Day la tin hieu path-jail. Nho nhung giup filesystem tool fail co kiem soat. |
| `_FakeChoiceMsg` | Test fake OpenAI response khong dung shape `choices[0].message.content`. | Chi output test bi anh huong; runtime that khong doi. | Day la test helper, khong phai runtime dependency. |
| `_FakeClient` | Test `llm.adapter.call_llm()` khong inject duoc fake client. | Chi test LLM adapter fail; runtime voi client that khong doi. | Day la test double de tranh network. |
| `_FakeClient._Completions` | Fake client khong co `chat.completions.create()`. | Chi test LLM adapter fail; runtime that khong doi. | Day la nested test helper mo phong API OpenAI-compatible. |
| `FsRead` | `toolbox.feature.install()` import/constructor fail neu khong sua tuple/import; tool `fs_read` khong duoc dang ky. | Agent khong doc duoc file; observation ve content file khong co; cac workflow can inspect file fail. | Day la tool quan sat filesystem. |
| `FsWrite` | Toolbox install fail hoac tool `fs_write` mat. | Agent khong ghi/sua file; output workflow tao artifact/code khong xay ra. | Day la tool thay doi filesystem. |
| `FsList` | Toolbox install fail hoac tool `fs_list` mat. | Agent kho dieu huong workspace; khong co output danh sach file/folder. | Day la tool kham pha filesystem. |
| `Terminal` | Toolbox install fail hoac tool `terminal_run` mat. | Agent khong chay duoc test/build/command; output `stdout/stderr/returncode` khong co. | Day la tool validation/thuc thi lenh. Can policy bao quanh. |

### Neu can thay the thi thay bang gi?

Bang nay tra loi 2 cau hoi:
- Thay the don gian nhat: neu can lam nhanh de project van chay, dung cach nao it code nhat?
- Thay the phuc tap/chuyen nghiep hon: neu sau nay project lon, can kiem soat chat hon, nen nang len kieu gi?

| Class | Thay the don gian nhat | Thay the phuc tap/chuyen nghiep hon |
|---|---|---|
| `EventBus` | Goi logger/callback truc tiep trong `AgentKernel`, hoac dung mot `NoopEventBus` co `publish()`/`subscribe()` rong. | Dung typed event bus, async queue, pub/sub backend, hoac OpenTelemetry/event pipeline co schema va correlation id. |
| `AgentKernel` | Viet cac ham module-level nhu `accept_task(registry, state, events, ...)` va `execute_tool(registry, tool_name, args)`. | Tach thanh service layer/workflow engine, co dependency injection, middleware, transaction boundary, lifecycle hooks, va observability tich hop. |
| `ToolPort` | Bo Protocol, chi quy uoc moi tool co `.execute(request)` bang duck typing. | Dung `ABC`/interface chinh thuc, generic type, JSON Schema/OpenAPI contract, hoac plugin SDK co validation tu dong. |
| `ToolResolution` | Tra ve tuple `(executor, feature)` hoac dict `{"executor": ..., "feature": ...}`. | Tao resolver object giau metadata: version, priority, permissions, fallback chain, capability negotiation, audit trail. |
| `NullToolPort` | Xu ly missing tool truc tiep trong `AgentKernel.execute_tool()` va return dict loi. | Dung fallback router/capability discovery: suggest tool gan dung, auto-install plugin, hoac route sang remote executor. |
| `CapabilityRegistry` | Mot dict don gian `{tool_name: executor}` va mot dict phu `{tool_name: feature}`. | Plugin manager/DI container/service registry co versioning, dependency graph, hot reload, permission scope, va health check. |
| `TaskEnvelope` | Dung dict `{"user_request": ..., "context": ..., "task_id": ...}`. | Dung Pydantic/dataclass schema co validation, trace context, tenant/user identity, priority, deadline, va audit metadata. |
| `ToolRequest` | Truyen thang `tool_name` va `args` vao executor, hoac dung dict `{"name": ..., "args": ...}`. | Dung RPC request schema co request id, auth scope, timeout, idempotency key, validation schema, va distributed tracing. |
| `CapabilityResult` | Moi tool tu tra dict thoa thuan gom `ok/error/data`; kernel khong boc them. | Dung result protocol typed/Pydantic, error taxonomy, partial result, streaming chunks, retry metadata, va schema registry. |
| `FeatureDescriptor` | Dung dict/hang module-level nhu `FEATURE = {"name": ..., "capabilities": ...}`. | Dung manifest rieng (`plugin.json`/package metadata), semantic versioning, dependency constraints, permissions, changelog, va compatibility check. |
| `StateStore` | Dung dict truc tiep trong kernel: `state = {}`. | Dung persistent store nhu SQLite/Redis/Postgres, event sourcing, snapshot, lock/concurrency control, va state migration. |
| `Budget` | Dung bien dem local trong `run_agent()` nhu `steps`, `parse_errors`, `tool_counts`. | Dung run controller/policy engine co quota theo user/model/tool, timeout wall-clock, cost budget, adaptive throttling, va circuit breaker. |
| `JsonGateError` | Raise `ValueError` chung va return retry message co dinh. | Dung error hierarchy co stage/code/context, parser diagnostics, repair strategy registry, va retry policy theo loai loi. |
| `EchoTool` | Dung lambda/function `echo(args) -> dict` dang ky truc tiep vao registry. | Dung sample plugin dung chuan SDK, co schema input/output, docs, fixtures, va contract tests cho plugin authors. |
| `AgentState` | Dung dict `state = {"task": ..., "messages": [], "step": 0, "final": None}`. | Dung typed state machine model, checkpointable graph state, versioned state schema, multi-agent role state, va resumable execution. |
| `EventLogger` | Dung `print()`/logging stdlib, hoac `NoopLogger` chi co `emit/count/finish` rong. | Dung structured logging + metrics + tracing: OpenTelemetry, log aggregation, dashboard, retention policy, run replay, va alerting. |
| `PolicyDecision` | `ToolPolicy.check()` tra tuple `(allowed, reason)` hoac bool. | Dung policy result typed co severity, remediation, user approval requirement, audit id, va compliance tags. |
| `ToolPolicy` | Viet if/else truc tiep trong `SafeToolPort.execute()` hoac trong `Terminal.execute()`. | Dung policy engine nhu OPA/Rego hoac rule engine rieng, config-driven policy, role-based permissions, approvals, va audit logs. |
| `SafeToolPort` | Goi `policy.check()` ngay trong tung tool, hoac bo wrapper va chi validate trong `Terminal/Fs*`. | Dung middleware pipeline quanh tool execution: auth, policy, rate limit, sandbox, tracing, retry, timeout, va result filtering. |
| `SandboxError` | Raise `ValueError`/`PermissionError` va catch chung trong filesystem tools. | Dung security exception hierarchy co error code, violation type, audit metadata, va mapping sang response chuan. |
| `_FakeChoiceMsg` | Dung `types.SimpleNamespace(message=SimpleNamespace(content=...))` trong test. | Dung fixture/factory typed, response builder, hoac mock OpenAI client library dung contract. |
| `_FakeClient` | Dung `unittest.mock.Mock()` voi nested attributes can thiet. | Dung test double hoan chinh cho LLM provider: scripted responses, failures, latency, token accounting, va contract tests. |
| `_FakeClient._Completions` | Dung mock method `fake.chat.completions.create.return_value = ...`. | Dung fake transport/API simulator co endpoint contract, error injection, va snapshots. |
| `FsRead` | Dung mot function `fs_read(args)` va dang ky function adapter. | Dung filesystem service co ACL, file metadata, streaming read, binary/text mode, cache, va audit. |
| `FsWrite` | Dung function `fs_write(args)` goi `Path.write_text()`. | Dung write service co atomic writes, diff/patch support, backup/rollback, approval gate, va conflict detection. |
| `FsList` | Dung function `fs_list(args)` goi `Path.iterdir()`. | Dung workspace indexer/search service co glob, metadata, ignore rules, pagination, va permission filtering. |
| `Terminal` | Dung function `terminal_run(args)` goi `subprocess.run()` voi argv va timeout. | Dung execution sandbox/container/job runner co resource limits, streaming logs, cancellation, allowlist, secrets isolation, va provenance. |

### Neu thieu method hoac bien cua class thi sao, va thay the the nao?

Phan nay di sau class-level: neu khong mat ca class, ma chi mat mot method/field quan trong, chuong trinh se hong o muc nao va co the thay bang cach gi.

| Thanh phan | Neu thieu thi anh huong/output | Thay the don gian nhat | Thay the phuc tap/chuyen nghiep hon |
|---|---|---|---|
| `EventBus._subscribers` | `subscribe()` khong co noi luu listener; `publish()` khong phat duoc event cho logger. Output log kernel event mat. | Dung list local/global trong module. | Dung subscriber registry co typed topic, priority, filter, va backpressure. |
| `EventBus.__init__()` | Tao bus khong khoi tao `_subscribers`, goi `subscribe/publish` se loi. | Dat `_subscribers = []` la class/default attr hoac lazy init trong `subscribe()`. | Lifecycle-managed event bus co start/stop, resource cleanup, va diagnostics. |
| `EventBus.subscribe(fn)` | `attach_to_bus()` khong noi logger vao bus; kernel van publish nhung khong ai nghe. | Truyen logger truc tiep vao kernel va goi logger trong `execute_tool()`. | Subscription API co unsubscribe, filters, async handlers, va error policy. |
| `EventBus.publish(topic, payload)` | `task.accepted/tool.*` khong duoc phat; observability khong co kernel event. | Goi tung callback/logger truc tiep tai call-site. | Event dispatcher/telemetry pipeline co schema, batching, retry, va tracing. |
| `AgentKernel.registry` | Kernel khong resolve duoc tool; `execute_tool()` dung lai truoc executor. | Truyen registry vao `execute_tool()` nhu parameter. | DI container/service locator co scoped registries va versioned capabilities. |
| `AgentKernel.events` | Kernel khong publish event; log/metrics kernel event mat. | Cho `events` la optional va dung `NoopEventBus`. | Observability middleware tu dong quanh kernel methods. |
| `AgentKernel.state` | `accept_task()` khong luu `current_task`; state noi bo mat. | Dung dict local `self.state = {}`. | Persistent run state store co checkpoint va resume. |
| `AgentKernel.config` | Runtime hien tai it anh huong, nhung kernel mat cau hinh kem theo. | Bo field neu chua can. | Typed runtime config co validation va hot reload. |
| `AgentKernel.accept_task()` | Agent loop khong tao task envelope/log task start; `run_agent()` loi. | Tao task dict va publish event ngay trong `run_agent()`. | Task service rieng co queue, priority, trace, va lifecycle. |
| `AgentKernel.execute_tool()` | Duong chay tool chinh mat; agent khong the tao output tool chuan. | Goi `registry.resolve_tool().executor.execute()` truc tiep trong `tool_node()`. | Tool execution service co middleware, retries, timeout, streaming, policy, audit. |
| `AgentKernel.describe_capabilities()` | Khong inspect duoc feature/tool dang co; test capabilities fail. | Doc truc tiep `registry.list_*()`. | Capability catalog API co search, docs, schema, permission view. |
| `ToolPort.name` | Mat ten executor trong contract; metadata executor trong kernel kem ro. | Dung `executor.__class__.__name__`. | Tool manifest/schema bat buoc co id/name/version. |
| `ToolPort.execute()` | Contract tool mat; type checker khong biet goi tool the nao. Runtime duck typing van co the chay neu tool that co method. | Bo Protocol va ghi convention trong docs. | Abstract base class/generic protocol co input/output schema. |
| `ToolResolution.executor` | Kernel khong biet object nao de `.execute()`. Tool khong chay. | Resolve tra thang executor. | Executor handle co metadata, lifecycle, health, permissions. |
| `ToolResolution.feature` | Envelope mat thong tin tool thuoc feature nao. | Set `feature=None` hoac lookup lai tu registry. | Capability provenance object co feature/package/version/source. |
| `NullToolPort.name` | Metadata executor cho missing tool kem ro, nhung output loi van co the dung. | Dung class name `NullToolPort`. | Missing-tool handler co id rieng va diagnostic code. |
| `NullToolPort.execute()` | Missing tool co the crash thay vi tra `missing_capability=True`. | Xu ly missing tool trong `CapabilityRegistry.resolve_tool()` hoac kernel. | Fallback capability router co suggestion/auto-discovery. |
| `CapabilityRegistry._tools` | Khong co bang tool name -> executor; moi tool deu coi nhu missing. | Dung dict module-level. | Service registry/plugin manager persistent va searchable. |
| `CapabilityRegistry._features` | Mat metadata feature; `list_features()` rong/loi. | Dung list/dict don gian cua feature descriptors. | Feature catalog co versioning/dependencies/compatibility. |
| `CapabilityRegistry._tool_features` | Tool van chay nhung envelope/list tools mat feature mapping. | Bo qua feature metadata. | Capability provenance map voi package/version/permission scope. |
| `CapabilityRegistry._fallback` | Khong co fallback executor; missing tool di thang null. | Luon dung `NullToolPort`. | Fallback chain/routing policy theo capability. |
| `CapabilityRegistry._fallback_feature` | Fallback van chay nhung metadata feature sai/thieu. | Gan `None`. | Fallback provenance typed. |
| `CapabilityRegistry._null` | Unknown tool khong co executor an toan. | Tao `NullToolPort()` ngay trong `resolve_tool()`. | Dedicated missing-capability service. |
| `CapabilityRegistry.__init__()` | Registry khong khoi tao duoc dict/fallback/null. | Khoi tao bang dict literal o call-site. | Registry lifecycle voi config, validation, plugin discovery. |
| `CapabilityRegistry.register_feature()` | Feature metadata khong vao registry; `describe_capabilities()` thieu feature. | Append descriptor vao list/module variable. | Manifest loader co validation. |
| `CapabilityRegistry.register_tool()` | Tool khong vao registry; `execute_tool()` resolve ra null. | Ghi thang `registry._tools[name] = executor`. | Registration API co schema validation, duplicate policy, permissions. |
| `CapabilityRegistry.register_tools()` | Dang ky nhieu alias phai lap tay; `example_echo.install()` loi. | For-loop tai feature install. | Batch registration transaction co rollback khi loi. |
| `CapabilityRegistry.set_fallback_tool_executor()` | Khong cau hinh fallback duoc; missing tool luon null. | Gan `_fallback` truc tiep. | Config-driven fallback/router. |
| `CapabilityRegistry.resolve_tool()` | Kernel khong lay duoc executor; tool path dung lai. | Lookup dict truc tiep trong kernel. | Resolver co priority, compatibility, permissions, caching. |
| `CapabilityRegistry.has_tool()` | Tests/check nhanh fail; runtime chinh it anh huong. | Dung `name in registry._tools`. | Health/capability query API. |
| `CapabilityRegistry.list_tools()` | `describe_capabilities()` mat danh sach tool. | Return sorted keys cua dict. | Capability catalog co pagination/filter/schema. |
| `CapabilityRegistry.list_features()` | `describe_capabilities()` mat danh sach feature. | Return values cua `_features`. | Feature catalog API. |
| `TaskEnvelope.user_request` | Mat noi dung task goc; state/log khong biet user yeu cau gi. | Dung string task rieng. | Typed task payload co multi-modal/input metadata. |
| `TaskEnvelope.context` | Mat context phu khi accept task. | Dung `{}` mac dinh. | Context object co scope, memory refs, user/session info. |
| `TaskEnvelope.metadata` | Mat metadata mo rong; runtime hien tai it anh huong. | Bo field. | Audit/trace/task metadata typed. |
| `TaskEnvelope.task_id` | Event `task.accepted` mat id; truy vet task kem. | Tao `uuid.uuid4().hex` trong `accept_task()`. | Distributed trace/run id integration. |
| `ToolRequest.name` | Tool khong biet dang duoc goi voi ten nao; policy/registry/log loi. | Truyen tool name rieng vao executor. | Request schema voi capability id/version. |
| `ToolRequest.args` | Tool khong co input; `Fs*`, `Terminal`, `EchoTool` khong lam duoc viec. | Truyen dict args rieng. | Validated args schema per tool. |
| `ToolRequest.request_id` | Mat correlation id giua requested/completed. | Tao id trong event metadata rieng. | Trace/span id distributed. |
| `CapabilityResult.ok` | Tang tren khong biet success/fail; topic `tool.completed/failed` kem tin cay. | Suy tu co/khong `error`. | Typed status enum voi partial/retryable state. |
| `CapabilityResult.capability` | Output khong noi ket qua thuoc tool nao. | Giu tool name rieng trong metadata. | Capability identity co namespace/version. |
| `CapabilityResult.feature` | Output mat feature provenance. | Cho `None`. | Provenance object. |
| `CapabilityResult.data` | Raw output khong co noi gom payload; graph/LLM phai doc key lung tung. | De raw dict nguyen ven. | Typed payload schema theo capability. |
| `CapabilityResult.error` | Fail output khong co thong diep loi chuan. | Dung `data["error"]`. | Error taxonomy co code/detail/remediation. |
| `CapabilityResult.metadata` | Mat request id/executor/raw keys; debug kho hon. | Bo qua metadata. | Structured trace/audit metadata. |
| `CapabilityResult.from_raw()` | Kernel khong boc raw tool result; output shape khong on dinh. | Moi tool tu tra envelope chuan. | Result normalization pipeline co schema registry. |
| `CapabilityResult.as_dict()` | Graph/log khong serialize dataclass de dang. | Dung `dataclasses.asdict()`. | Serializer co redaction/versioning. |
| `FeatureDescriptor.name` | Registry khong co key feature; feature_name khi dang ky tool thieu. | Dung module path lam ten. | Feature id namespace/version. |
| `FeatureDescriptor.version` | Mat version feature; runtime hien tai it anh huong. | Hardcode `"0.1"` trong `as_dict()`. | Semantic version/compat matrix. |
| `FeatureDescriptor.capabilities` | Loader/registry khong biet feature cung cap tool nao. | Dang ky tool name truc tiep trong install. | Capability schema/manifest declarative. |
| `FeatureDescriptor.enabled` | Metadata khong noi feature bat/tat; config van quyet dinh enabled. | Bo field. | Runtime feature flag service. |
| `FeatureDescriptor.description` | Mat mo ta feature. | Bo field. | Docs/catalog generator. |
| `FeatureDescriptor.as_dict()` | `list_features()` khong xuat dict duoc. | Dung `dataclasses.asdict()`. | Manifest serializer/validator. |
| `StateStore._data` | `get/set/as_dict` khong co storage; state fail. | Dung dict public `state.data`. | Persistent state backend. |
| `StateStore.__init__()` | `_data` khong khoi tao; method loi. | Lazy init `_data` trong `get/set`. | Managed store lifecycle. |
| `StateStore.get()` | Khong doc state duoc; hien runtime it dung doc. | Dung `state._data.get`. | Query API co default/schema. |
| `StateStore.set()` | `accept_task()` khong luu current task. | Ghi dict truc tiep. | Transactional state update. |
| `StateStore.as_dict()` | Khong snapshot/debug state duoc. | Dung `dict(state._data)`. | Snapshot/export co redaction. |
| `Budget.max_steps` | Khong gioi han step; agent co the lap lau. | Hardcode max trong `run_agent()`. | Policy quota theo run/user. |
| `Budget.max_parse_errors` | Output LLM sai JSON co the retry qua nhieu. | Hardcode threshold. | Retry policy theo loai parser/model. |
| `Budget.max_same_tool_calls` | Same-tool loop khong bi chan. | Hardcode threshold trong runtime. | Loop detector/circuit breaker. |
| `Budget.steps` | Khong dem buoc; output `steps`/budget sai. | Local variable `steps`. | Run metrics state. |
| `Budget.parse_errors` | Khong dem parse error; retry budget sai. | Local variable `parse_errors`. | Error budget tracker. |
| `Budget._tool_calls` | Khong phat hien lap cung tool+args. | Dict local trong `run_agent()`. | Loop analysis/cache keyed by action. |
| `Budget.record_step()` | Step counter khong tang. | `budget.steps += 1`. | Instrumented counter middleware. |
| `Budget.step_exceeded()` | Khong check duoc step budget. | `steps > max_steps`. | Runtime quota engine. |
| `Budget.record_parse_error()` | Parse error counter khong tang. | `parse_errors += 1`. | Parser retry tracker. |
| `Budget.parse_exceeded()` | Khong dung sau qua nhieu parse error. | `parse_errors >= max_parse_errors`. | Retry/circuit policy. |
| `Budget.record_tool_call()` | Same-tool dem sai. | `tool_counts[key] += 1`. | Action dedupe/loop detector. |
| `Budget.same_tool_exceeded()` | Same-tool loop khong bi chan. | `tool_counts[key] > limit`. | Loop breaker co decay/window. |
| `Budget.tool_key()` | Khong co key on dinh cho tool+args. | `tool_name + str(args)`. | Canonical action fingerprint/hash. |
| `JsonGateError.stage` | Retry message/test khong biet loi parse hay schema. | Dung string message don gian. | Error code enum. |
| `JsonGateError.candidate` | Mat mau output loi de debug. | Log raw text rieng. | Parser diagnostic object. |
| `JsonGateError.__init__()` | Khong gan stage/candidate; error kem thong tin. | Raise `ValueError(message)`. | Structured exception hierarchy. |
| `EchoTool.name` | Metadata executor kem ro; install hien dung `register_tools(FEATURE.capabilities, EchoTool())` nen runtime chinh it anh huong. | Dung class name. | Tool manifest id. |
| `EchoTool.execute()` | Tool echo khong tra ket qua; tests/smoke fail. | Function `echo(args)`. | Plugin executor co schema. |
| `AgentState.task` | `agent_node()` khong tao prompt user dung. | Truyen task rieng vao `agent_node()`. | State model co task object. |
| `AgentState.messages` | LLM khong nhan observation/retry history; agent khong hoc tu tool output. | List local trong `run_agent()`. | Conversation/memory store. |
| `AgentState.step` | Output steps va event step sai. | Local `step`. | Run progress tracker. |
| `AgentState.final` | Runtime khong luu cau tra loi cuoi; output `{final: ...}` fail. | Local `final`. | Final result object co status/artifacts. |
| `AgentState.last_action` | Hien chua dung; mat khong anh huong runtime. | Bo field. | Action history/audit. |
| `AgentState.code_changed` | Finish gate khong biet co can validation khong. | Truyen dict validation rieng. | Change tracking service. |
| `AgentState.validation_passed` | Finish gate khong biet validation da pass chua. | Truyen flag rieng. | Validation result registry. |
| `EventLogger.enabled` | Khong tat/bat logging duoc; disabled test fail. | Luon ghi log hoac luon noop. | Logging config service. |
| `EventLogger.run_id` | Events/summary khong co id; inspect run kho. | Tao id local trong `run_agent()`. | Trace/run id service. |
| `EventLogger.seq` | Event khong co sequence tang dan. | Bo sequence hoac dung timestamp. | Ordered event stream. |
| `EventLogger.metrics` | Summary khong co counters. | Dict local trong `run_agent()`. | Metrics backend. |
| `EventLogger.run_dir` | Khong biet ghi files vao dau. | Tinh path trong `emit/finish`. | Run artifact store. |
| `EventLogger.events_path` | `emit()` khong co file JSONL dich. | Tinh path moi lan emit. | Log sink abstraction. |
| `EventLogger.__init__()` | Logger khong khoi tao dir/metrics/run id; emit/finish loi. | NoopLogger hoac init bang dict. | Managed logger lifecycle. |
| `EventLogger.emit()` | Khong ghi event chi tiet; debug run kho. | `print(json.dumps(event))`. | Structured event writer/tracer. |
| `EventLogger.count()` | Metrics khong tang; summary thieu so lieu. | Tang dict truc tiep. | Metrics client/counter API. |
| `EventLogger.finish()` | Khong ghi summary/index; run_agent khong co `run_id` tu summary. | Return `{"run_id": logger.run_id, "status": status}`. | Run finalizer co artifact upload/retention. |
| `PolicyDecision.allowed` | `SafeToolPort` khong biet cho chay hay block. | Return bool truc tiep. | Policy verdict enum. |
| `PolicyDecision.reason` | Output block khong co ly do. | Message string rieng. | Remediation message/catalog. |
| `PolicyDecision.code` | Output/test khong co ma loi policy. | Hardcode code trong response. | Policy code taxonomy. |
| `PolicyDecision.risk` | Metadata khong noi muc rui ro. | Bo risk. | Risk scoring/compliance tags. |
| `ToolPolicy.check()` | SafeToolPort khong co gate; tool nguy hiem co the chay hoac runtime loi. | If/else ngay trong wrapper/tool. | External policy engine. |
| `SafeToolPort.name` | Metadata wrapper kem ro; registry van co key tool name rieng. | Dung inner.name. | Middleware identity. |
| `SafeToolPort._inner` | Wrapper khong co tool goc de delegate; tool khong chay. | Truyen function executor truc tiep. | Execution chain context. |
| `SafeToolPort._policy` | Wrapper khong co policy; an toan mat hoac loi. | Tao policy local trong `execute()`. | Policy middleware dependency. |
| `SafeToolPort.__init__()` | Khong boc duoc tool voi inner/policy. | Function factory `make_safe(tool, policy)`. | Middleware builder/container. |
| `SafeToolPort.execute()` | Policy khong duoc ap va tool khong delegate; toolbox fail. | Goi policy + inner trong feature/kernel. | Middleware pipeline. |
| `_FakeChoiceMsg.message` | Fake response khong giong OpenAI shape; test adapter fail. | `SimpleNamespace(content=content)`. | Typed fake response builder. |
| `_FakeChoiceMsg.__init__()` | Khong tao fake message content. | Inline namespace trong test. | Fixture factory. |
| `_FakeClient.content` | Fake khong biet noi dung can tra. | Hardcode response trong mock. | Scripted response queue. |
| `_FakeClient.boom` | Khong test duoc error path. | Mock side_effect exception. | Failure injection framework. |
| `_FakeClient.kwargs` | Khong assert duoc adapter gui `model/response_format`. | Spy mock call args. | Contract test recorder. |
| `_FakeClient.chat` | `call_llm()` khong goi duoc `client.chat.completions.create`. | Mock nested attribute. | Fake API client. |
| `_FakeClient.__init__()` | Fake client khong cau hinh duoc content/error/chat. | Mock object tai tung test. | Test double builder. |
| `_FakeClient._Completions.create()` | Adapter khong nhan fake response; tests fail. | Mock return value cua create. | Fake transport endpoint. |
| `FsRead.name` | Tool install khong lay duoc ten `fs_read` trong tuple hiện tại; dang ky fail neu khong sua. | Dang ky string `"fs_read"` truc tiep. | Tool manifest. |
| `FsRead.execute()` | Khong doc file duoc; output content mat. | Function `fs_read(args)`. | File read service. |
| `FsWrite.name` | Dang ky `fs_write` fail neu install con doc `tool.name`. | Dang ky string truc tiep. | Tool manifest. |
| `FsWrite.execute()` | Khong ghi file duoc; workflow sua artifact fail. | Function `fs_write(args)`. | Atomic write/patch service. |
| `FsList.name` | Dang ky `fs_list` fail neu install con doc `tool.name`. | Dang ky string truc tiep. | Tool manifest. |
| `FsList.execute()` | Khong liet ke workspace duoc; agent kem kha nang kham pha. | Function `fs_list(args)`. | Workspace index/search service. |
| `Terminal.name` | Dang ky `terminal_run` fail neu install con doc `tool.name`. | Dang ky string truc tiep. | Tool manifest. |
| `Terminal.execute()` | Khong chay command/test/build duoc. | Function `terminal_run(args)`. | Job runner/sandbox service. |
| `Terminal request.args["argv"]` | Khong co command de chay; output loi `argv must be...`. | Truyen argv la parameter rieng. | Command schema co allowlist/validation. |
| `Terminal request.args["timeout"]` | Command co the timeout mac dinh 10s; mat kha nang tuy chinh. | Dung default co dinh. | Deadline/resource policy. |

### Ket luan co the rut ra

- Nhom "khong the thieu neu muon runtime chay": `AgentKernel`, `CapabilityRegistry`, `ToolRequest`, `CapabilityResult`, `TaskEnvelope`, `StateStore`.
- Nhom "khong the thieu neu muon graph agent chay": `AgentState`, `Budget`, `JsonGateError`, `EventLogger`.
- Nhom "khong the thieu neu muon tool an toan": `SafeToolPort`, `ToolPolicy`, `PolicyDecision`, `SandboxError`.
- Nhom "thieu thi mat mot nang luc tool cu the": `EchoTool`, `FsRead`, `FsWrite`, `FsList`, `Terminal`.
- Nhom "co the bo ma runtime chinh van co the chay neu khong import": `ToolPort` va cac fake class trong tests. Doi lai se mat type contract hoac mat test coverage.
- Mau thiet ke rut ra duoc: class nao tao schema/registry/kernel/logger la class "xương sống"; class nao nam trong `toolbox` la capability; class nao nam trong `tests` la test double; class nao nam trong `safety` la guardrail.
