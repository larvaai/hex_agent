# RUN & CONFIGURE — mọi cách chạy và tùy biến agent

> Đối chiếu với source ngày **2026-06-25**. Tài liệu này phân biệt rõ:
>
> - **đã được runtime/UI dùng tự động**;
> - **có API nhưng caller phải tự compose**;
> - **chỉ có thể đổi bằng code**.

## 1. Bản đồ nhanh

| Nhu cầu | Cách nên dùng |
|---|---|
| Chạy agent tương tác | `python -m ui` hoặc `core-agent-ui` |
| Gửi prompt tự động từ script | HTTP `POST /api/runs` khi UI server đang chạy |
| Nhúng agent vào Python | `orchestrator.run()` / `resume()` |
| Chạy multi-agent Supervisor | `supervisor.run_task_loop()` / `resume_task_loop()` |
| Đổi system prompt cho root agent | UI Prompt editor, HTTP body, hoặc `run(system_prompt=...)` |
| Định nghĩa persona/quyền bằng YAML | `roles/library/*.yaml` + skill/lens registries, sau đó **tự inject** prompt/session scope |
| Bật/tắt tool/feature | `config/features.yaml` hoặc custom config truyền vào `create_kernel(path)` |
| Đổi model/endpoint | Biến môi trường `LLM_*` |
| Xem run/log | UI hoặc `python -m observability.inspect ...` |

## 2. Cài đặt

```powershell
cd D:\myagent
python -m pip install -e ".[dev]"
```

Sau editable install, console script `core-agent-ui` có trên PATH. Không cài editable vẫn có thể
dùng mọi lệnh `python -m ...` từ root repo.

Optional Qdrant production backend:

```powershell
python -m pip install -e ".[dev,rag]"
docker compose -f docker-compose.rag.yml up -d
```

## 3. Toàn bộ CLI entrypoint

### 3.1 UI server — ba lệnh tương đương

```powershell
python -m ui
python -m ui.server
core-agent-ui
```

Flags:

```powershell
python -m ui --host 127.0.0.1 --port 8765
python -m ui --help
```

Environment tương đương:

```powershell
$env:AGENT_UI_HOST = "127.0.0.1"
$env:AGENT_UI_PORT = "8765"
python -m ui
```

Mở [http://127.0.0.1:8765](http://127.0.0.1:8765). Mặc định bind loopback. Không nên bind
`0.0.0.0` vì UI chưa có authentication và có API xem file/chạy agent.

### 3.2 Observability CLI

```powershell
# list run, mặc định khi không truyền command
python -m observability.inspect
python -m observability.inspect list
python -m observability.inspect ls

# summary
python -m observability.inspect summary latest
python -m observability.inspect summary <run_id>

# event; --kind là exact event kind
python -m observability.inspect events latest
python -m observability.inspect events latest --kind LLMCallEvent
python -m observability.inspect events <run_id> --kind KernelEvent
```

Event kinds hiện gặp: `StateEvent`, `KernelEvent`, `LLMCallEvent`, `UIEvent`.

### 3.3 Smoke, test và lint

```powershell
python run_smoke.py
python -m pytest
python -m ruff check .
```

`run_smoke.py` offline, không gọi model. Nó kiểm tra bootstrap, session, echo tool, scope block,
JSON repair, finish gate và event summary.

### 3.4 Documentation/tooling scripts

```powershell
# tái sinh MAP.md từ module docstrings
python tools/gen_map.py

# dump cây repo + nội dung text vào project_context.txt
python read_file_and_list.py
```

`read_file_and_list.py` có side effect ghi đè `project_context.txt`.

### 3.5 Những CLI chưa tồn tại

Hiện **không có** các lệnh kiểu:

```text
core-agent run "prompt"
python -m orchestrator "prompt"
python -m supervisor ...
```

Muốn chạy một task không mở browser, dùng HTTP API hoặc Python API ở các mục dưới.

### 3.6 Direct-script equivalents

Các module có `if __name__ == "__main__"` cũng chạy trực tiếp từ repo root:

```powershell
python ui/server.py --host 127.0.0.1 --port 8765
python ui/__main__.py --host 127.0.0.1 --port 8765
python observability/inspect.py summary latest
python run_smoke.py
python tools/gen_map.py
python read_file_and_list.py
```

Nên ưu tiên `python -m ui` và `python -m observability.inspect` vì module execution ổn định hơn
khi package được cài.

## 4. UI: chạy và chỉnh system prompt

### 4.1 Chạy một prompt

1. Mở UI.
2. Nhập task ở ô prompt.
3. Nhấn **Run** hoặc `Ctrl+Enter`.
4. Chọn run ở top bar; xem Conversation, State timeline, Event log và Inspector.

Mỗi run UI tạo kernel/logger/delegation service mới. Thay đổi `config/features.yaml` được đọc ở
**run kế tiếp**, không cần restart server. Biến môi trường của process vẫn cần set trước khi start UI.

### 4.2 System Prompt editor

- Nhấn nút sliders bên trái ô prompt, hoặc tab **Prompt** ở Inspector.
- Sửa prompt: giá trị được lưu trong browser `localStorage` với key
  `core-agent-system-prompt` và áp cho các run sau trong browser profile đó.
- **Mặc định**: trở về `orchestrator.loop.DEFAULT_SYSTEM`.
- **Nạp từ run**: lấy system message đầu tiên trong checkpoint của run đang xem.
- Server giới hạn system prompt ở `40.000` ký tự; task prompt ở `20.000` ký tự.

Lưu ý: khi delegation bật, `orchestrator.run()` tự nối thêm cú pháp `delegate` vào system prompt.
System message đã lưu trong run vì vậy chứa suffix này. Nếu dùng **Nạp từ run**, run sau sẽ nối thêm
suffix lần nữa; nên xóa phần `Delegation targets: ...` cũ trước khi chạy lại.

### 4.3 UI HTTP endpoints

| Method | Endpoint | Vai trò |
|---|---|---|
| `GET` | `/api/bootstrap?scope=workspace` | Default prompt + run/file snapshot đầu tiên |
| `GET` | `/api/runs` | Danh sách tối đa 100 run gần nhất |
| `POST` | `/api/runs` | Tạo run từ `prompt` và optional `system_prompt` |
| `GET` | `/api/snapshot?run_id=...&scope=...` | Run + messages + events + file tree |
| `GET` | `/api/tree?scope=workspace|project` | File tree |
| `GET` | `/api/file?scope=...&path=...` | Preview UTF-8 text file |
| `GET` | `/api/stream?run_id=...&scope=...` | SSE snapshot stream |

## 5. Gửi task qua HTTP, không thao tác UI

Khởi động server trước:

```powershell
python -m ui
```

Từ PowerShell khác:

```powershell
$system = @'
You are a careful code-review agent.
Return exactly one JSON action object and no prose outside JSON.
Tool call: {"action":"tool","tool":"<name>","args":{}}
Finish: {"action":"final","message":"<answer>","finish_reason":"done"}
'@

$body = @{
  prompt = "Review the current workspace and summarize the highest-risk issue."
  system_prompt = $system
} | ConvertTo-Json

$response = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8765/api/runs" `
  -ContentType "application/json" `
  -Body $body

$response.run.run_id
```

Theo dõi bằng UI hoặc:

```powershell
Invoke-RestMethod "http://127.0.0.1:8765/api/snapshot?run_id=$($response.run.run_id)&scope=workspace"
```

POST trả `202 Accepted`; task chạy nền trong `RunController`, không đợi outcome cuối.

## 6. Python API: single-agent mặc định

### 6.1 Chạy đầy đủ với logging và delegation

```python
from core.bootstrap import create_kernel
from delegation.bootstrap import create_delegation_service
from observability import EventLogger, attach_to_bus
from orchestrator import run

task = "Inspect the workspace and report the result."
system = """You are a precise engineering agent.
Return exactly one JSON object.
Tool: {"action":"tool","tool":"<name>","args":{}}
Final: {"action":"final","message":"<answer>","finish_reason":"done"}
"""

kernel = create_kernel()
logger = EventLogger()
attach_to_bus(logger, kernel.events)
delegation = create_delegation_service(kernel)

outcome = run(
    kernel,
    task,
    run_id=logger.run_id,
    system_prompt=system,
    delegation_service=delegation,
    checkpoint=True,
)
logger.finish(outcome["status"], outcome=outcome)
print(outcome)
```

### 6.2 Không lưu SQLite/checkpoint projection

```python
outcome = run(kernel, task, checkpoint=False, system_prompt=system)
```

Event logging là subsystem riêng; nếu bạn đã attach `EventLogger`, nó vẫn có thể ghi event dù graph
checkpoint tắt.

### 6.3 Resume parent LangGraph

```python
from core.bootstrap import create_kernel
from delegation.bootstrap import create_delegation_service
from orchestrator import resume

kernel = create_kernel()
outcome = resume(
    kernel,
    "<run_id>",
    delegation_service=create_delegation_service(kernel),
)
```

Kernel mới phải đăng ký đủ capability đã có trong persisted session scope.

### 6.4 Dùng config file khác

```python
from core.bootstrap import create_kernel

kernel = create_kernel("config/my-agent.yaml")
```

UI CLI hiện không có `--config`; UI luôn gọi `create_kernel()` với
`config/features.yaml`. Muốn UI dùng file khác phải sửa composition code hoặc thay file mặc định.

Config in-memory không cần file:

```python
from core.bootstrap import build_kernel

kernel = build_kernel({
    "features": {
        "llm_chat": {"enabled": True, "module": "features.llm_chat"},
        "toolbox": {"enabled": True, "module": "toolbox.feature"},
    },
    "delegation": {"enabled": False},
})
```

### 6.5 Compatibility runner

```python
from core.bootstrap import build_kernel
from graph.runtime import run_agent

kernel = build_kernel({"features": {"example_echo": {
    "enabled": True,
    "module": "features.example_echo",
}}})

result = run_agent(
    "Say hello",
    kernel=kernel,
    llm_call=lambda messages, model=None: '{"action":"final","message":"hello"}',
)
```

`run_agent()` dùng `COMPAT_SYSTEM_PROMPT` hard-coded và không nhận `system_prompt`. Đây là seam tương
thích/test; code mới nên dùng `orchestrator.run()`.

## 7. Toàn bộ điểm tùy biến system prompt

| Agent/prompt | Cách override runtime | Nguồn mặc định | Tự động dùng role/skill? |
|---|---|---|---|
| Root single-agent qua UI | Prompt editor/localStorage | `DEFAULT_SYSTEM` | Không |
| Root single-agent qua HTTP | `system_prompt` trong POST JSON | `DEFAULT_SYSTEM` | Không |
| Root single-agent qua Python | `run(..., system_prompt="...")` | `DEFAULT_SYSTEM` | Không |
| Root compatibility runner | Không có parameter | `COMPAT_SYSTEM_PROMPT` | Không |
| Delegated child `LangGraphDelegationAgent` | Chưa có parameter/config | `COMPAT_SYSTEM_PROMPT` | Không |
| Role agent prompt | `RoleSpec.system_prompt` + `Agent.build_prompt()` | Role YAML | Có, nhưng caller phải inject |
| Supervisor Agent O compose | Custom `OrchestratorPort` hoặc sửa constant | `COMPOSE_SYSTEM` | Role catalog chỉ là dữ liệu vào |
| Supervisor Agent O decide | Custom `OrchestratorPort` hoặc sửa constant | `DECIDE_SYSTEM` | Không tự enforce role policy |
| Supervisor Context Broker | Custom `BrokerPort` hoặc sửa/subclass | `BROKER_SYSTEM` | Không |

Không có `AGENT_SYSTEM_PROMPT` env var và không có `system_prompt:` trong
`config/features.yaml`. Nếu thêm key đó vào YAML, code hiện tại sẽ không dùng.

### 7.1 Prompt contract bắt buộc của single-agent graph

Model phải trả đúng một JSON object có `action`. Prompt custom tối thiểu nên giữ:

```text
You are <persona and operating rules>.

Reply with exactly ONE JSON object and no markdown/prose outside it.

To call a tool:
{"action":"tool","tool":"<registered capability>","args":{...}}

To finish:
{"action":"final","message":"<answer>","finish_reason":"done"}

If work is blocked:
{"action":"final","message":"<reason>","finish_reason":"blocker"}
```

Khi truyền `delegation_service`, runtime tự nối grammar `delegate`; không cần hard-code target vào
prompt base.

### 7.2 Prompt thay đổi gì và không thay đổi gì

Prompt có thể hướng dẫn persona, workflow, tiêu chuẩn output và khi nào dùng tool. Prompt **không**:

- đăng ký thêm capability;
- mở rộng `KernelSession.allowed_capabilities`;
- thay đổi sandbox/policy;
- tự bật skill/role/lens;
- tự thêm delegation target.

Những phần đó phải cấu hình bằng code/YAML ở các mục sau.

## 8. Skills

Skill library mặc định nằm ở `skills/library/*.md`, nhưng bootstrap/UI **không tự load**.

### 8.1 Định dạng skill

```markdown
---
name: secure_review
description: Review code for correctness and security without modifying files.
triggers: [review, security, audit]
---

## Allowed (tools)
- fs_read
- fs_list

## Forbidden (tools)
- fs_write
- terminal_run

## Steps
1. Inspect the relevant files.
2. Trace data and permission boundaries.
3. Report findings with evidence.

## Report
- verdict
- findings
- missing_tests
```

Parser yêu cầu `name`, `description` và YAML frontmatter. `triggers` chỉ được parse/lưu; chưa có
runtime selector tự động match task → skill.

### 8.2 Load, lint và render

```python
from skills import SkillRegistry

skills = SkillRegistry()
skills.load_dir("skills/library")

print(skills.names())
print(skills.render("code_review", mode="contract"))  # không có Steps/Report
print(skills.render("code_review", mode="full"))      # đầy đủ

unknown = skills.lint(kernel.registry.has_tool)
if unknown:
    raise ValueError(unknown)
```

`contract` phù hợp để nhúng mọi lúc; `full` phù hợp khi skill đã được chọn cho step hiện tại.

## 9. Roles và lenses

### 9.1 Role YAML

```yaml
name: reviewer
role: Senior read-only reviewer
department: engineering
system_prompt: |
  You review changes and report evidence. Do not modify files.
allowed_tools:
  - fs_read
  - fs_list
allowed_skills:
  - code_review
route_permissions:
  may_route_to:
    - code
test_ownership:
  owns_validation: false
  must_handoff_to: test
lenses:
  - correctness
```

Required fields: `name`, `role`, `department`, `system_prompt`.

### 9.2 Lens YAML

```yaml
name: security
purpose: Find trust-boundary, secret-handling, injection, and privilege issues.
allowed_tools:
  - fs_read
forbidden_tools:
  - fs_write
output_schema:
  verdict: string
  findings: list
```

Lens allowed/forbidden hiện được **render thành prompt hint**, chưa tham gia code-side capability
enforcement.

### 9.3 Cách thực sự áp role + skill vào root runtime

```python
from core.bootstrap import create_kernel
from core.session import SessionFactory
from delegation.bootstrap import create_delegation_service
from orchestrator import run
from roles import AgentRegistry, LensRegistry
from skills import SkillRegistry

task = "Review the workspace and report correctness risks."
kernel = create_kernel()

skills = SkillRegistry()
skills.load_dir("skills/library")

lenses = LensRegistry()
lenses.load_dir("roles/library/lenses")

# llm.chat là capability nền graph bắt buộc phải gọi.
roles = AgentRegistry(
    skills=skills,
    lenses=lenses,
    core_tools=frozenset({"llm.chat"}),
)
roles.load_dir("roles/library")

role_agent = roles.build_agent("code")

# build_prompt() gồm role system prompt + lenses + allowed tools + skill contracts.
system_prompt = role_agent.build_prompt()

# Nếu active step cần toàn bộ Steps/Report của skill:
system_prompt += "\n\n" + skills.render("file_edit", mode="full")

# Scope code-side phải được set riêng; prompt không cấp quyền.
session = SessionFactory(kernel=kernel).create_root(
    task,
    agent_id=role_agent.spec.name,
    allowed_capabilities=role_agent.allowed_tools,
)

outcome = run(
    kernel,
    task,
    session=session,
    system_prompt=system_prompt,
    delegation_service=create_delegation_service(kernel),
)
print(outcome)
```

Điểm cần nhớ:

1. `core_tools={"llm.chat"}` là cần thiết cho graph agent gọi model.
2. `Agent.build_prompt()` không tự thay đổi session scope; phải truyền
   `allowed_capabilities=role_agent.allowed_tools`.
3. Default UI không thực hiện composition này.
4. `Agent.guard_tool_call()` và `guard_finish()` chưa được default graph gọi; session scope mới là
   enforcement code-side thực sự trên đường tool.

## 10. Feature config

File mặc định: `config/features.yaml`.

Ví dụ đầy đủ các key bootstrap hiện hiểu:

```yaml
features:
  example_echo:
    enabled: true
    module: features.example_echo

  llm_chat:
    enabled: true
    module: features.llm_chat

  toolbox:
    enabled: true
    module: toolbox.feature

  rag:
    enabled: true
    module: rag.feature

rag:
  backend: memory
  collection: agent_kb
  model: BAAI/bge-small-en-v1.5
  chunk_size: 800
  chunk_overlap: 100
  score_threshold: 0.8
  top_k: 5
  qdrant_url: http://127.0.0.1:6333

middleware:
  timing:
    enabled: true
  policy:
    enabled: true
    deny:
      - terminal_run
  retry:
    enabled: true
    attempts: 2
  condense:
    enabled: true
    max_chars: 2000
    max_list: 10

delegation:
  enabled: true
  default_target: agent:general
```

### 10.1 Feature semantics

- `enabled: false` hoặc thiếu feature → không import/đăng ký capability.
- Mỗi enabled feature phải có `module` và module phải có `install(kernel)`.
- RAG `backend: memory` chạy offline và process-local.
- RAG `backend: qdrant` dùng `QdrantVectorStore` + `FastEmbedEmbedder`; cần extras `[rag]` và
  Qdrant đang chạy (`docker-compose.rag.yml`).
- Tắt `llm_chat` làm default graph không thể gọi `llm.chat` trừ khi caller tự đăng ký adapter khác.
- Tắt toolbox loại bỏ `fs_*`/`terminal_run` khỏi registry và root default scope.

### 10.2 Middleware semantics

Order bootstrap outer → inner:

```text
TimingLog -> PolicyGate -> Retry -> CondenseResult -> executor core
```

`BudgetGuard` không có YAML wiring vì counter phải per-run; shared instance sẽ rò state giữa run.
Single-agent graph đã có step/parse/same-tool budget riêng.

Programmatic middleware phải thêm trước root session đầu tiên:

```python
from middleware import PolicyGate, Retry

kernel.use(PolicyGate(deny={"terminal_run"}))
kernel.use(Retry(attempts=2))
```

Sau `SessionFactory.create_root()`, kernel đã freeze và `kernel.use/register_tool` sẽ raise.

## 11. Tạo custom feature/tool

```python
# features/my_feature.py
from core.schemas import FeatureDescriptor

FEATURE = FeatureDescriptor(
    name="my_feature",
    capabilities=("my.lookup",),
    description="Example custom capability.",
)


class LookupTool:
    name = "my.lookup"

    def execute(self, request):
        query = str(request.args.get("query", ""))
        return {"ok": True, "query": query, "answer": "..."}


def install(kernel):
    kernel.registry.register_feature(FEATURE)
    kernel.registry.register_tool(
        "my.lookup",
        LookupTool(),
        feature_name=FEATURE.name,
        kind="read",
        idempotent=True,
        risk="low",
    )
```

Config:

```yaml
features:
  my_feature:
    enabled: true
    module: features.my_feature
```

Tool phải trả dict có `ok`. Kernel chuẩn hóa raw dict thành `CapabilityResult`.

## 12. Capability scope

Root session mặc định nhận tất cả tool đang đăng ký:

```python
session = SessionFactory(kernel=kernel).create_root(task)
```

Root read-only có scope rõ ràng:

```python
session = SessionFactory(kernel=kernel).create_root(
    task,
    allowed_capabilities=frozenset({"llm.chat", "fs_read", "fs_list"}),
)
```

Tên ngoài registry bị reject khi tạo root. Tool ngoài scope bị kernel trả `scope_block` trước
executor. Không gọi thẳng `kernel.execute_tool()` trong runtime scoped; gọi
`session.execute_tool()` để luôn có lineage và scope.

### 12.1 Inject custom LLM client

Ngoài `LLM_*` environment variables, test/host application có thể đăng ký client OpenAI-compatible
đã khởi tạo:

```python
from core.bootstrap import build_kernel
from features.llm_chat import FEATURE, LLMChatTool

kernel = build_kernel({"features": {}})
kernel.registry.register_feature(FEATURE)
kernel.registry.register_tools(
    FEATURE.capabilities,
    LLMChatTool(client=my_openai_compatible_client),
    feature_name=FEATURE.name,
    kind="model",
    idempotent=True,
)
```

Client cần có shape `client.chat.completions.create(...)`.

## 13. Delegation config và custom target

YAML mặc định chỉ cấu hình được:

```yaml
delegation:
  enabled: true
  default_target: agent:general
```

Nó tạo đúng một `LangGraphDelegationAgent(target)`. Đổi target chỉ đổi identifier model phải dùng;
child vẫn chạy `COMPAT_SYSTEM_PROMPT` và cùng single-agent graph.

Muốn nhiều target/persona khác nhau, tự dựng registry/service:

```python
from adapters.agents import LangGraphDelegationAgent
from core.session import SessionFactory
from delegation import DelegationManager, DelegationRegistry, InMemoryDelegationStore

registry = DelegationRegistry()
registry.register(LangGraphDelegationAgent("agent:research"))

service = DelegationManager(
    registry=registry,
    sessions=SessionFactory(kernel=kernel),
    store=InMemoryDelegationStore(),
)
```

Một registry không thể đăng ký hai handler cùng `.name`. Muốn child có prompt khác, implement custom
`DelegationPort` hoặc mở rộng `LangGraphDelegationAgent`; config hiện không có child system prompt.

## 14. Supervisor TaskLoop

Supervisor là Python library runtime, chưa có CLI/UI route.

```python
from core.bootstrap import create_kernel
from core.session import SessionFactory
from delegation.bootstrap import create_delegation_service
from supervisor import (
    KernelChatLLM,
    LLMBroker,
    LLMOrchestrator,
    SqliteTaskLoopStore,
    run_task_loop,
)

task = "Produce an evidence-backed answer."
kernel = create_kernel()
session = SessionFactory(kernel=kernel).create_root(task)
service = create_delegation_service(kernel)

chat = KernelChatLLM(session)
store = SqliteTaskLoopStore(session.identity.run_id)

result = run_task_loop(
    session,
    task,
    acceptance_criteria=[("ac1", "Answer is backed by a real artifact")],
    delegation_service=service,
    orchestrator=LLMOrchestrator(chat),
    broker=LLMBroker(chat, char_budget=1200),
    max_rounds=5,
    checkpoint_store=store,
)
```

Để chạy đáng tin cậy, Agent O phải chọn target có trong `delegation_service.available_targets()`.
Default service chỉ có target từ `delegation.default_target`.

### 14.1 Tùy biến prompt Agent O/Broker

`LLMOrchestrator` dùng constants `COMPOSE_SYSTEM` và `DECIDE_SYSTEM`; `LLMBroker` dùng
`BROKER_SYSTEM`. Constructor chưa nhận prompt override. Có ba cách:

1. Sửa constants trong code — global, đơn giản nhưng khó cấu hình per-run.
2. Implement `OrchestratorPort`/`BrokerPort` riêng — cách khuyến nghị cho per-run/product behavior.
3. Dùng `ScriptedOrchestrator`/`DeterministicBroker` cho test/offline deterministic flow.

Custom Orchestrator contract:

```python
class MyOrchestrator:
    def compose_team(self, *, task, available_roles) -> str:
        return '{"selected_agents":[{"agent_id":"agent:general","reason":"general task"}]}'

    def decide(self, *, state_view) -> str:
        return '{"decision":"blocked","reason":"custom decision"}'
```

Output phải đúng schema trong `supervisor.contracts.parse_session_plan/parse_decision`.

### 14.2 Role catalog trong Supervisor

Truyền `agent_registry=roles` để Agent O thấy `agent_id/role`. Tuy nhiên caller vẫn phải đảm bảo:

- delegation registry có handler cho các role ID đó;
- assignment scope được intersect với role scope;
- route permissions được enforce.

Code hiện chưa tự enforce ba điều này.

## 15. Toàn bộ environment variables

| Variable | Default | Tác dụng |
|---|---|---|
| `LLM_BASE_URL` | `http://localhost:1234/v1` | OpenAI-compatible endpoint |
| `LLM_API_KEY` | `lm-studio` | API key |
| `LLM_MODEL` | `local-model` | Model mặc định |
| `LLM_MAX_TOKENS` | `2048` | Max completion tokens |
| `LLM_TIMEOUT` | `120` | Client timeout seconds |
| `LLM_MAX_RETRIES` | `2` | Transport retries sau lần đầu |
| `LLM_RETRY_BASE` | `0.5` | Exponential-backoff base seconds |
| `AGENT_UI_HOST` | `127.0.0.1` | UI bind host |
| `AGENT_UI_PORT` | `8765` | UI port |
| `AGENT_WORKSPACE_DIR` | `var/workspace` | Filesystem tool/RAG workspace root |
| `AGENT_RUNS_DIR` | `var/agent_runs` | Events/checkpoints/summaries root |
| `AGENT_EVENT_LOG` | `1` | `0` tắt disk event logging mặc định |
| `AGENT_ALLOW_GIT_MUTATIONS` | false | Truthy (`1/true/yes/on`) cho policy cho phép git mutation |

Integration-test-only: `QDRANT_URL` đổi endpoint mà `tests/test_rag_qdrant.py` probe; production
runtime đọc `rag.qdrant_url` từ YAML, không đọc env này.

PowerShell example:

```powershell
$env:LLM_BASE_URL = "https://api.openai.com/v1"
$env:LLM_API_KEY = "<secret>"
$env:LLM_MODEL = "<model>"
$env:AGENT_WORKSPACE_DIR = "D:\work\agent-sandbox"
$env:AGENT_RUNS_DIR = "D:\work\agent-runs"
python -m ui
```

OpenAI client được lazy-create và cache ở module level. Environment của một process bình thường được
inherit khi process start; đổi `$env:...` ở shell khác không tác động server đang chạy. Sau lần gọi
model đầu tiên, kể cả code đổi `os.environ`, `LLM_BASE_URL`, `LLM_API_KEY` hoặc timeout cũng không
rebuild client; restart process hoặc gọi `llm.adapter.reset_client()`.

## 16. Recipes

### 16.1 Agent read-only

- Giữ `llm.chat`, `fs_read`, `fs_list` trong session scope.
- Loại `fs_write`, `terminal_run`.
- Prompt nói rõ không thay đổi file.
- Không chỉ dựa vào prompt; enforcement phải bằng scope.

### 16.2 Agent code nhưng không terminal

YAML middleware:

```yaml
middleware:
  policy:
    enabled: true
    deny: [terminal_run]
```

Hoặc session scope chỉ gồm `llm.chat`, `fs_read`, `fs_write`, `fs_list`.

### 16.3 Offline deterministic test

- Không dùng `llm_chat` thật.
- Dùng `graph.runtime.run_agent(..., llm_call=scripted_callable)` hoặc inject fake client vào
  `LLMChatTool`.
- Dùng `ScriptedDelegationAgent`, `ScriptedOrchestrator`, `DeterministicBroker`.

### 16.4 Prompt theo role + active skill

```python
prompt = role_agent.build_prompt()
prompt += "\n\n# Active skill\n" + skills.render("code_review", mode="full")
```

Sau đó truyền prompt vào `orchestrator.run()` và tạo session với role scope như mục 9.3.

## 17. Thời điểm config có hiệu lực

| Config | Khi nào đọc | Muốn thay đổi có hiệu lực |
|---|---|---|
| `config/features.yaml` | Mỗi `create_kernel()` | UI: run kế tiếp; Python: kernel mới |
| UI system prompt | Browser localStorage | Run kế tiếp |
| HTTP/Python system prompt | Khi gọi start/run | Chính run đó |
| `LLM_*` client endpoint/key | Lúc lazy-create client đầu tiên | Restart/reset client |
| `LLM_MODEL/MAX_TOKENS/retry` | `_defaults()` mỗi call | Restart process, hoặc code đổi chính `os.environ` của process |
| Skill/role/lens files | Khi caller gọi `load_dir/load_file` | Build registry/Agent mới |
| Middleware/tool registry | Trước root session đầu tiên | Kernel mới; sau freeze không sửa được |

## 18. Safety notes khi cấu hình

1. `terminal_run` chỉ chạy no-shell và đổi cwd; nó chưa phải OS sandbox.
2. Prompt không thay thế capability scope/policy.
3. Event log hiện ghi raw tool args; `llm.chat` args chứa transcript.
4. UI không có auth; giữ bind `127.0.0.1`.
5. Child delegation prompt/persona chưa configurable bằng YAML.
6. Role/lens/skill không tự wire vào default UI.
7. Qdrant backend là optional infrastructure; memory backend vẫn là default self-contained.

Chi tiết finding và remediation: `docs/CODE_REVIEW.md`.

## 19. Checklist xác nhận cấu hình

```powershell
python -m pytest
python -m ruff check .
python run_smoke.py
python -m ui --help
```

Trong Python, kiểm tra registry/scope trước khi chạy:

```python
print(kernel.describe_capabilities())
print(sorted(session.allowed_capabilities))
print(skills.lint(kernel.registry.has_tool))
```
