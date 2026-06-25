# ONBOARDING & CONTRIBUTING — hướng dẫn cho thành viên mới

> Mục tiêu: trong buổi đầu tiên, một contributor mới có thể dựng môi trường, chạy baseline, hiểu
> runtime boundary, chọn đúng nơi để sửa, viết test và gửi một change nhỏ mà không phá invariant.

## 1. Project này là gì?

`core_agent` là một agent runtime Python theo hướng hexagonal/microkernel:

- shared `AgentKernel` quản lý capability registry, events và tool chokepoint;
- per-run `KernelSession` quản lý identity, mutable state, capability scope và lifecycle;
- single-agent orchestration dùng compiled LangGraph + SQLite checkpoint/resume;
- LLM được đăng ký như capability `llm.chat`, đi cùng đường với mọi tool;
- delegation là application boundary riêng, tạo child session cô lập;
- skills, roles, lenses, RAG và Supervisor là các subsystem mở rộng;
- local UI hiển thị run, prompt, checkpoint, events và workspace files.

Đọc implementation hiện tại, không suy đoán từ roadmap:

- `docs/RUNTIME_FLOW.md` — task chạy thật như thế nào;
- `docs/CLASS_ENCYCLOPEDIA.md` — ownership và dependency của toàn bộ class;
- `docs/CODE_REVIEW.md` — finding/rủi ro hiện biết;
- `docs/rebuild_from_zero/` — PRD, stories, acceptance và roadmap theo Epic.

## 2. Setup môi trường

### 2.1 Yêu cầu

- Python 3.11+;
- Git;
- PowerShell trên Windows hoặc shell tương đương;
- LLM server/API chỉ cần khi chạy agent thật, **không cần cho test**.

### 2.2 Clone, virtualenv và editable install

Windows PowerShell:

```powershell
git clone <repository-url>
cd myagent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Linux/macOS:

```bash
git clone <repository-url>
cd myagent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Editable install giúp source thay đổi có hiệu lực ngay và cài console script `core-agent-ui`.

### 2.3 Baseline bắt buộc

Chạy trước khi sửa để biết lỗi nào đã tồn tại:

```powershell
python -m pytest
python -m ruff check .
python run_smoke.py
```

Expected tại thời điểm viết guide:

```text
<N> passed, optional Qdrant integration skipped khi service không chạy
All checks passed!
CORE_AGENT_SMOKE_OK run_id=...
```

Số test có thể tăng. Qdrant integration tests được skip khi dependency/server không sẵn sàng; điều
quan trọng là không có failure ngoài skip có chủ đích.

Optional production RAG/Qdrant setup:

```powershell
python -m pip install -e ".[dev,rag]"
docker compose -f docker-compose.rag.yml up -d
python -m pytest tests/test_rag_qdrant.py
```

### 2.4 Chạy UI khi cần hiểu runtime

```powershell
python -m ui
```

Mở [http://127.0.0.1:8765](http://127.0.0.1:8765). Cấu hình endpoint/model nằm trong
`docs/RUN_AND_CONFIGURE.md`.

## 3. Lộ trình đọc trong 60 phút

### 0–10 phút: biết cách chạy

1. `README.md`;
2. `docs/RUN_AND_CONFIGURE.md`;
3. `config/features.yaml`.

Kết quả cần nắm: entrypoint nào chạy UI/task, feature nào bật mặc định, config nào là env/YAML/API.

### 10–25 phút: hiểu runtime

1. `docs/RUNTIME_FLOW.md`;
2. `docs/class_dependency.mermaid`;
3. `orchestrator/loop.py`;
4. `graph/runtime.py` và `graph/nodes.py`.

Kết quả cần nắm: topology `guard → agent → tool/delegate/finish`, checkpoint và resume.

### 25–40 phút: hiểu boundary lõi

1. `core/session.py`;
2. `core/kernel.py`;
3. `core/registry.py`;
4. `core/schemas.py`;
5. `core/ports.py`.

Kết quả cần nắm: kernel shared, session per-run, scope nằm trong `ToolCallContext`, envelope chuẩn.

### 40–50 phút: hiểu hợp đồng sống

Đọc test gần vùng muốn sửa. Ví dụ:

- kernel/session: `test_kernel.py`, `test_session.py`, `test_trace_ids.py`;
- graph/resume: `test_orchestrator.py`, `test_resume.py`, `test_checkpoint.py`;
- delegation: `test_delegation.py`;
- Supervisor: `test_supervisor_*.py`, `test_context_broker.py`, `test_acceptance_gate.py`;
- roles/skills: `test_roles.py`, `test_skills.py`;
- RAG: `test_rag.py`;
- safety/toolbox: `test_safety.py`, `test_toolbox.py`;
- UI: `test_ui_server.py`.

### 50–60 phút: đọc ý định và rủi ro

1. Epic tương ứng trong `docs/rebuild_from_zero/E##_*/`;
2. `acceptance.md` trước, rồi `stories.md`/`PRD.md`;
3. `docs/KNOWN_RISKS.md`;
4. `docs/CODE_REVIEW.md`.

## 4. Mental model tối thiểu

```text
caller/UI
  -> orchestrator.run/resume
    -> compiled graph
      -> KernelSession
        -> AgentKernel.execute_tool
          -> middleware
          -> CapabilityRegistry
          -> ToolPort executor
          -> CapabilityResult + EventBus

graph delegate node
  -> DelegationManager
    -> policy + target registry + progress store
    -> child KernelSession
    -> DelegationPort adapter
```

### Ownership

| Thành phần | Sở hữu | Không được sở hữu |
|---|---|---|
| `AgentKernel` | Registry, events, frozen config, middleware | Per-run state/task lifecycle |
| `KernelSession` | Identity, scope, state, lifecycle | Shared registry/config |
| `AgentState` | Serializable graph/control state | Client, lock, kernel, connection |
| `DelegationManager` | Parent→child application call | Kernel tool execution |
| `EventLogger` | Disk event/read model metrics | Runtime decision logic |
| `checkpoint.json` | UI projection | Resume truth |

### Hai chokepoint

1. Tool/LLM: `KernelSession.execute_tool()` → `AgentKernel.execute_tool()`.
2. Delegation: `DelegationServicePort.delegate()` → `DelegationManager`.

Nếu change tạo đường thứ ba, hãy dừng lại và xem lại thiết kế.

## 5. Repo map

| Path | Trách nhiệm | Epic chính |
|---|---|---|
| `core/` | Kernel, session, contracts, registry, event/state | E01 |
| `discipline/` | JSON gate, budgets, condense, finish gate | E02 |
| `llm/`, `features/` | LLM adapter và feature plugins | E03/E01 |
| `observability/` | Event log, summary, inspect CLI | E04 |
| `graph/`, `orchestrator/` | Single-agent graph, checkpoint/resume facade | E05 |
| `safety/`, `toolbox/`, `middleware/` | Policy, workspace tools, cross-cutting wrappers | E06 |
| `skills/` | Skill parser/registry/progressive disclosure | E07 |
| `rag/` | Health/ingest/search qua ports; memory + optional Qdrant adapters | E08 |
| `roles/` | Role/lens configs, prompt/scope derivation | E09 |
| `delegation/`, `adapters/agents/` | Child session delegation substrate | E10 substrate |
| `supervisor/` | Agent O, Broker, Blackboard, acceptance loop/resume | E10 |
| `ui/` | Local HTTP/SSE console | UI/runtime operations |
| `tests/` | Offline living contracts | Theo từng Epic |
| `docs/rebuild_from_zero/` | Product intent/acceptance/roadmap | E01–E20 |
| `var/` | Runtime artifacts, gitignored | Không commit |

`MAP.md` là module index tự sinh. Sau khi thêm/đổi module docstring, chạy `python tools/gen_map.py`.

## 6. Cách chọn một contribution phù hợp

### Good first contribution

- thêm test cho edge case đã có behavior rõ;
- sửa/cập nhật tài liệu bị lệch code;
- cải thiện error message có test;
- thêm read-only feature/tool nhỏ qua plugin pattern;
- thêm validation cho parser/config;
- thêm observability field không chứa secret;
- sửa một finding P2/P3 trong `docs/CODE_REVIEW.md` với regression test.

### Không nên là change đầu tiên

- đổi `AgentState` schema/checkpoint migration;
- thay graph topology;
- thay `AgentKernel.execute_tool` envelope/event order;
- mở quyền terminal/git hoặc nới sandbox;
- làm delegation song song/durable effect ledger;
- refactor nhiều package cùng lúc;
- “cleanup” toàn repo không gắn behavior/acceptance.

### Trước khi code

Viết scope một câu:

```text
Given <state>, when <action>, then <observable behavior>.
```

Nếu không viết được câu này, issue còn quá mơ hồ.

## 7. Contribution workflow

### 7.1 Tạo branch nhỏ

```powershell
git switch -c feat/E10-short-description
```

Tên branch không phải API contract; ưu tiên dễ hiểu và gắn Epic nếu biết.

### 7.2 Giữ working tree có chủ đích

```powershell
git status --short
git diff --stat
```

Không xóa/format thay đổi không thuộc task. Không commit runtime artifacts, generated logs hoặc secret.

### 7.3 Acceptance-first

1. Mở `docs/rebuild_from_zero/E##_*/acceptance.md`.
2. Tìm AC liên quan hoặc bổ sung AC nếu feature mới.
3. Map behavior sang test offline.
4. Chạy test để thấy fail đúng lý do.
5. Implement nhỏ nhất để test xanh.
6. Chạy vùng test lân cận và full suite.

### 7.4 Commit nhỏ, message rõ

Convention quan sát từ lịch sử repo:

```text
feat(E10): add durable worker checkpoint
fix(E06): reject unsafe terminal argv
test(E08): cover empty-query behavior
docs: add contributor onboarding
refactor(E01): isolate registry descriptor lookup
```

Một commit nên có một lý do thay đổi có thể review độc lập.

### 7.5 Trước khi gửi review/PR

```powershell
git diff --check
python -m pytest
python -m ruff check .
python run_smoke.py
git status --short
```

Trong description, ghi:

```markdown
## Why
Vấn đề/acceptance nào được giải quyết?

## What
Boundary/file nào thay đổi?

## Verification
- [ ] targeted tests
- [ ] full pytest
- [ ] Ruff
- [ ] smoke

## Risks
Checkpoint/scope/safety/compatibility nào có thể bị ảnh hưởng?
```

## 8. Coding conventions

### Python

- Python target: 3.11;
- Ruff line length: 110;
- type hints cho public boundary và data flow quan trọng;
- immutable contracts ưu tiên `@dataclass(frozen=True)`;
- framework boundary ưu tiên `Protocol` thay vì import concrete implementation;
- optional/heavy dependency import lazy;
- public tool/service trả structured result, không rò raw exception;
- module mới có docstring dòng đầu nêu mục đích + Epic.

### Dependency direction

- `core/` không import `graph`, `ui`, `supervisor`, concrete adapters;
- graph nhận service qua injection/closure;
- business logic RAG dùng ports, không chạm backend concrete trực tiếp;
- roles có thể phụ thuộc skills; skills không phụ thuộc roles;
- Supervisor nằm trên core/session/delegation, không chui vào kernel.

### Tests

- offline, deterministic, không gọi network/model thật;
- inject fake/scripted LLM client;
- dùng `tmp_path` và `monkeypatch` cho filesystem/env;
- assert behavior/envelope/event/state, không phụ thuộc implementation detail vô ích;
- tên test mô tả behavior;
- khi bug được fix, regression test phải fail trên code cũ.

### Documentation

- giữ ngôn ngữ/style của file lân cận;
- mô tả **implementation đang chạy** khác với proposal/roadmap;
- command/config example phải chạy được;
- topology/public API/config đổi thì cập nhật `RUNTIME_FLOW.md`/`RUN_AND_CONFIGURE.md`;
- class ownership đổi thì cập nhật `CLASS_ENCYCLOPEDIA.md`/dependency diagram;
- module mới/đổi docstring thì chạy `python tools/gen_map.py`;
- thay đổi đáng kể thêm mục mới trên đầu `CHANGELOG.md`.

## 9. Playbook theo loại thay đổi

### 9.1 Thêm feature/tool

Checklist:

1. Tạo `FeatureDescriptor` và `install(kernel)`.
2. Executor tuân `ToolPort`: `.name`, `.execute(ToolRequest) -> dict`.
3. Chọn canonical capability name.
4. Đăng ký descriptor đúng:
   - `kind="model"` cho model;
   - `kind="read"` cho read-only;
   - `kind="effect"` cho write/side effect;
   - `idempotent` đúng thực tế;
   - `risk` phù hợp.
5. Áp workspace jail/policy trước I/O/effect.
6. Thêm feature config và disabled behavior test.
7. Test success, validation failure, policy/scope failure, exception normalization.
8. Cập nhật `MAP.md`, runtime/config docs.

Test gần nhất:

```powershell
python -m pytest tests/test_kernel.py tests/test_toolbox.py tests/test_safety.py
```

### 9.2 Sửa kernel/registry/session

Phải giữ:

- registry/config/middleware freeze;
- root scope ⊆ registered capabilities;
- child scope ⊆ parent scope;
- tool events có lineage/request ID;
- executor/middleware lỗi không làm hỏng envelope contract;
- state giữa session không alias.

Chạy:

```powershell
python -m pytest `
  tests/test_kernel.py `
  tests/test_session.py `
  tests/test_trace_ids.py `
  tests/test_event_concurrency.py `
  tests/test_capability_kind.py
```

### 9.3 Sửa graph topology/node

1. Liệt kê route output mới.
2. Cập nhật conditional edges trong `build_agent_graph`.
3. Đảm bảo mọi terminal branch đóng lifecycle đúng một lần.
4. Parse errors không tiêu step; same-tool guard chặn trước extra execution.
5. Cập nhật `docs/RUNTIME_FLOW.md`.

Chạy:

```powershell
python -m pytest tests/test_graph.py tests/test_orchestrator.py tests/test_lifecycle.py
```

### 9.4 Thêm/đổi checkpointed state

Đây là vùng rủi ro cao:

1. Chỉ primitives hoặc type được codec xử lý.
2. Mở rộng `encode_session_state/decode_session_state` nếu cần.
3. Đổi incompatible shape → tăng `schema_version` và thêm migration.
4. Giữ `run_id == thread_id`.
5. SQLite là truth; JSON là projection.
6. Test completed resume, interrupted resume và legacy migration nếu ảnh hưởng.

Chạy:

```powershell
python -m pytest `
  tests/test_state.py `
  tests/test_checkpoint.py `
  tests/test_resume.py `
  tests/test_lifecycle.py
```

### 9.5 Sửa delegation

- mọi parent→child call qua `DelegationManager`;
- validate trước create child;
- store progress trước publish;
- progress sequence liên tiếp và event ID idempotent;
- child state/scope/identity cô lập;
- parent vẫn active sau call-return;
- side effect/resume cần durable idempotency design, không chỉ retry.

```powershell
python -m pytest tests/test_delegation.py tests/test_session.py
```

### 9.6 Sửa Supervisor

Giữ:

- Agent O emit structured decision, không tự gọi tool;
- tool request đi qua supervisor session;
- Broker không mang capability scope;
- acceptance `passed` cần evidence ID có thật;
- max rounds/no-progress/repeated decision guard;
- checkpoint sau completed turn/round/terminal;
- resume không re-run completed turn trong cùng round.

```powershell
python -m pytest `
  tests/test_supervisor_loop.py `
  tests/test_supervisor_llm.py `
  tests/test_supervisor_resume.py `
  tests/test_supervisor_discipline.py `
  tests/test_context_broker.py `
  tests/test_acceptance_gate.py `
  tests/test_loop_guard.py
```

### 9.7 Thêm/đổi skill, role hoặc lens

Skills:

- YAML frontmatter có `name`, `description`;
- Allowed/Forbidden dùng canonical tool names;
- Steps/Report chỉ hiện ở `mode="full"`;
- chạy registry lint.

Roles/lenses:

- role required: name/role/department/system_prompt;
- skill forbidden wins khi derive role scope;
- route/test ownership có test;
- lens tool hints hiện chỉ là prompt hints, không phải enforcement.

```powershell
python -m pytest tests/test_skills.py tests/test_roles.py
```

### 9.8 Sửa RAG

- health gate trước ingest/search;
- ingest path qua workspace jail;
- logic chỉ dùng `EmbedderPort/VectorStorePort`;
- test offline bằng FakeEmbedder/InMemoryVectorStore;
- re-ingest phải replace source, không duplicate;
- threshold/top-k/output fields có test.
- Qdrant adapter import lazy; base install/memory backend không phụ thuộc Qdrant/fastembed.
- Integration collection phải throwaway và cleanup sau test.

```powershell
python -m pytest tests/test_rag.py

# optional: cần extras + local Qdrant
python -m pytest tests/test_rag_qdrant.py
```

### 9.9 Sửa safety/toolbox

- deny-by-default cho hành vi nguy hiểm;
- filesystem path resolve rồi containment-check;
- không dùng prompt làm security boundary;
- không mở git mutation mặc định;
- error trả structured envelope;
- nhớ: `terminal_run` hiện chưa phải OS sandbox.

```powershell
python -m pytest tests/test_safety.py tests/test_toolbox.py tests/test_supervisor_discipline.py
```

### 9.10 Sửa UI/API

- giữ default bind loopback;
- validate body size/type/path;
- file preview không thoát selected root và không mở sensitive/binary file;
- frontend render untrusted content bằng `textContent`, không `innerHTML`;
- SSE/client disconnect không làm server crash;
- thay API shape phải cập nhật `app.js`, tests và `RUN_AND_CONFIGURE.md`.

```powershell
python -m pytest tests/test_ui_server.py
python -m ui --help
```

## 10. Test strategy

### Test pyramid thực tế

| Tầng | Ví dụ | Mục tiêu |
|---|---|---|
| Pure unit | discipline, parsers, policy, codec | Nhanh, edge cases |
| Port/adapter | RAG store/embedder, LLM fake client | Contract không network |
| Component | kernel + feature, delegation manager | Boundary/envelope/events |
| Runtime | orchestrator/graph/Supervisor | Flow, budgets, lifecycle |
| Smoke | `run_smoke.py` | Foundation end-to-end nhỏ nhất |

### Khi nào cần full suite?

Luôn chạy trước khi bàn giao. Targeted tests chỉ giúp feedback nhanh trong lúc sửa.

### Unit/component tests không phụ thuộc network ngoài

- LLM: fake OpenAI-compatible client hoặc callable script;
- delegation: `ScriptedDelegationAgent`;
- Supervisor: `ScriptedOrchestrator`, `DeterministicBroker`;
- RAG: `FakeEmbedder`, `InMemoryVectorStore`;
- filesystem: `tmp_path`;
- time/backoff: monkeypatch sleep/env.

Ngoại lệ có chủ đích: `tests/test_rag_qdrant.py` là integration suite tới local Qdrant. Nó skip khi
`qdrant-client` hoặc server không sẵn sàng. Start bằng `docker compose -f docker-compose.rag.yml up -d`.

## 11. Debugging

### Xem run gần nhất

```powershell
python -m observability.inspect summary latest
python -m observability.inspect events latest
python -m observability.inspect events latest --kind LLMCallEvent
```

Artifacts:

```text
var/agent_runs/<run_id>/
  events.jsonl
  summary.json
  langgraph.sqlite
  checkpoint.json
  taskloop.sqlite       # nếu Supervisor checkpoint được bật
```

### Nguồn sự thật

- Parent resume: `langgraph.sqlite`;
- Supervisor Blackboard resume: `taskloop.sqlite` khi caller truyền store;
- UI display: `checkpoint.json` projection;
- timeline/metrics: `events.jsonl`, `summary.json`.

### Trace IDs

```text
run_id
  └─ task_id
       └─ session_id
            └─ request_id / delegation_id / child task_id
```

Tìm theo IDs trước khi đọc toàn log.

## 12. Các bẫy người mới thường gặp

1. **Gọi `kernel.execute_tool` trực tiếp**: bỏ session scope/lineage; runtime mới dùng session.
2. **Nhét object vào state**: checkpoint có thể vỡ; state phải encode được.
3. **Sửa `checkpoint.json` để resume**: không có tác dụng với modern run; SQLite mới là truth.
4. **Đăng ký tool sau khi tạo session**: registry đã freeze.
5. **Chỉ sửa prompt để hạn quyền**: prompt không phải security boundary.
6. **Tưởng skill/role tự chạy trong UI**: hiện phải build/inject thủ công.
7. **Bật retry cho write tool không khai descriptor**: có thể lặp side effect.
8. **Tưởng terminal cwd là sandbox**: process vẫn có thể truy cập ngoài workspace.
9. **Log secret trong tool args**: raw args hiện được ghi event.
10. **Đọc roadmap như implementation**: kiểm tra code/tests/runtime docs trước.
11. **Refactor kèm format toàn repo**: làm review khó và dễ đè thay đổi khác.
12. **Quên update docs/topology**: contributor sau sẽ xây trên mental model sai.

## 13. Documentation ownership

| Khi thay đổi | Cập nhật |
|---|---|
| Cách chạy/env/YAML/prompt/skill wiring | `docs/RUN_AND_CONFIGURE.md`, `README.md` |
| Graph/runtime/delegation/resume flow | `docs/RUNTIME_FLOW.md` |
| Class ownership/dependency | `docs/CLASS_ENCYCLOPEDIA.md`, `class_dependency.mermaid` |
| Rủi ro/invariant | `docs/KNOWN_RISKS.md`, `docs/CODE_REVIEW.md` |
| Module/package | module docstring, `MAP.md` qua generator |
| Feature/sprint đáng kể | `CHANGELOG.md` |
| Intent/acceptance | `docs/rebuild_from_zero/E##_*/` |

Không copy cùng một sự thật vào nhiều file nếu có thể link tới nguồn chính.

## 14. Review checklist

### Correctness

- Behavior có đúng acceptance không?
- Error path có structured result và terminal state đúng không?
- Boundary mới có bypass chokepoint không?
- Concurrency/resume có thể chạy effect hai lần không?

### State/persistence

- Dữ liệu mới encode được không?
- Resume giữ identity/scope/budget không?
- Migration backward-compatible không?

### Security

- Input path/argv/tool name được validate ở code-side không?
- Scope có bị mở rộng do default/empty semantics không?
- Secret/raw prompt có bị log không?
- Retry có an toàn với effect không?

### Observability

- Event có lineage IDs không?
- Success/failure metrics có phản ánh đúng lifecycle không?
- Observer lỗi có bị cô lập không?

### Maintainability

- Concrete dependency có thể nằm sau Protocol/adapter không?
- Logic bị duplicate giữa single/multi-agent không?
- Test có quá gắn implementation detail không?
- Docs/source map có còn đúng không?

## 15. Definition of Done

Một contribution hoàn thành khi:

- [ ] Scope/acceptance rõ ràng.
- [ ] Test mới hoặc test hiện có chứng minh behavior.
- [ ] Targeted tests xanh.
- [ ] Full `pytest` xanh.
- [ ] Ruff xanh.
- [ ] Smoke xanh.
- [ ] `git diff --check` sạch cho files thuộc change.
- [ ] Không có secret/runtime artifact/generated noise.
- [ ] Public contract/config/docs được cập nhật.
- [ ] Compatibility/resume/safety impact được ghi trong review description.
- [ ] Diff nhỏ, không đè thay đổi ngoài task.

## 16. Bài tập onboarding đề xuất

### Bài 1 — read-only trace

Chạy smoke, mở `events.jsonl`, lần theo `task.accepted → tool.requested → tool.completed →
task.completed`. Không sửa code.

### Bài 2 — thêm parser edge-case test

Thêm một test JSON repair hoặc role/skill validation. Không đổi public API.

### Bài 3 — feature nhỏ

Tạo read-only tool `text.stats`, đăng ký `kind="read", idempotent=True`, thêm config + tests +
MAP/docs.

### Bài 4 — review một finding

Chọn một P2/P3 trong `CODE_REVIEW.md`, viết Given/When/Then và đề xuất regression test trước khi
implement.

Hoàn thành bốn bài này là đủ để bắt đầu nhận task ở kernel-adjacent subsystem với review.

## 17. Khi cần hỏi maintainer

Hãy hỏi trước khi change yêu cầu:

- đổi public envelope/schema;
- migration checkpoint không backward-compatible;
- mở quyền/sandbox/network/secret handling;
- thêm dependency nặng hoặc service ngoài;
- thay topology hoặc execution semantics;
- triển khai roadmap Epic chưa có acceptance rõ;
- xóa compatibility path.

Một câu hỏi tốt gồm: behavior hiện tại, behavior mong muốn, acceptance đề xuất, files/boundary ảnh
hưởng và rủi ro.
