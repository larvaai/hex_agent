# Kien truc MCP tools cho `core_agent`

> Trang thai: de xuat kien truc, chua phai implementation.  
> Ngay ra soat: 2026-06-23.  
> Nen tang doi chieu: MCP specification `2025-11-25`, Python SDK `v1.28.0`.

## 1. Ket luan kien truc

Project nen dong vai tro **MCP host/client**: ket noi den nhieu MCP server va bien moi remote tool thanh mot
`ToolPort` cua kernel. MCP khong duoc tao mot duong thuc thi rieng.

Moi call phai giu invariant:

```text
agent/orchestrator
    -> AgentKernel.execute_tool()
    -> resolve descriptor + executor
    -> validate input
    -> policy + approval + budget
    -> MCP adapter
    -> MCP session manager
    -> external MCP server
    -> validate/sanitize output
    -> CapabilityResult + events
```

Nam quyet dinh chinh:

1. Dat integration tai `integrations/mcp/`, **khong tao top-level `mcp/`**. Top-level `mcp` se xung dot voi
   package `mcp` cua Python SDK chinh thuc.
2. Ten tool noi bo phai co namespace server: `mcp.<server_id>.<tool_name>`. Khong tao alias ngan neu chua
   khai bao tuong minh.
3. Registry co the biet toan bo tool, nhung model chi thay mot `ToolView` nho theo task/profile. Khong dua
   hang tram tool vao prompt.
4. Safety la mot policy pipeline o chokepoint cua kernel. MCP adapter chi lo protocol va transport, khong tu
   quyet dinh quyen.
5. Tool co side effect khong duoc retry tu dong neu chua co bang chung idempotent. Approval phai do user/UI
   cap, model khong bao gio duoc tu phe duyet.

## 2. Danh gia project hien tai

### 2.1 Nhung seam da phu hop

| Thanh phan | Diem phu hop voi MCP |
|---|---|
| `core/kernel.py` | `execute_tool()` da la chokepoint chung, bat exception va chuan hoa envelope. |
| `core/ports.py` | `ToolPort` la bien adapter phu hop de boc mot MCP tool. |
| `core/registry.py` | Co exact registration, feature ownership va null fallback. |
| `features/loader.py` | Co plugin pattern `install(kernel)` tu YAML. |
| `middleware/` | Co seam pre/post cho policy, budget, retry, timing va condense. |
| `orchestrator/checkpoint.py` | Co nen de dung run tai trang thai cho approval roi resume. |
| `observability/` | Da co `task_id`, `request_id`, event log va metrics. |
| `safety/` | Da co workspace jail va phan loai terminal/git co ban. |

Do do MCP nen la adapter moi cua kien truc hien tai, khong nen thay kernel bang mot MCP-specific runtime.

### 2.2 Khoang trong can xu ly

1. **Registry chi luu name/executor/feature.** Chua co JSON Schema, source server, trust, risk, timeout,
   idempotency hay output schema. Policy vi the khong du du lieu de quyet dinh.
2. **`ToolRequest` chi co name/args/request_id.** Chua co actor, task/run, tool descriptor revision, approval
   grant hay deadline.
3. **Hai safety path dang song song.** `SafeToolPort` boc tung toolbox tool, con `PolicyGate` la middleware
   deny-list. Neu MCP lai co wrapper thu ba, policy se phan manh.
4. **`Retry` hien retry moi result `ok=False` tru policy block.** Mot remote call da gui email, tao issue hay
   thanh toan co the bi lap lai. Day la blocker truoc khi bat write tool.
5. **Event `tool.requested` ghi raw args.** Token, PII hoac secret trong MCP arguments co the bi ghi vao
   `events.jsonl`.
6. **Output tool duoc dua lai model nhu du lieu tin cay.** MCP output phai duoc coi la untrusted content de
   giam prompt injection va data exfiltration.
7. **Hai loop `graph/` va `orchestrator/` chua hop nhat.** Ca hai deu goi tool qua kernel, nhung prompt/tool
   discovery va discipline khac nhau. MCP nen tich hop duoi kernel, con agent-facing exposure nen lam truoc
   cho `orchestrator/loop.py` va sau do tai su dung cho graph.
8. **Prompt hien tai khong chen tool schema.** `DEFAULT_SYSTEM` chi mo ta JSON action; model khong biet tool
   nao ton tai va arguments nao hop le. Day la blocker ve tinh dung dan, ke ca khi MCP connection da chay.
9. **Lifecycle hien tai la sync.** Python MCP SDK la async va session/stdio process can song lau. Khong duoc
   `asyncio.run()` hay spawn process lai cho moi tool call.
10. **Same-tool budget chua duoc ap vao orchestrator.** `BudgetGuard` co chu thich la phai wire per-run,
    nhung `orchestrator/loop.py` hien chua dang ky no va cung chua record repeated tool calls. Remote MCP tool
    vi the co the bi goi lap den khi cham step budget.

## 3. Folder de xuat

### 3.1 Layout muc tieu

```text
core_agent/
|-- integrations/
|   |-- __init__.py
|   `-- mcp/
|       |-- __init__.py
|       |-- feature.py          # install feature, dang ky proxy vao registry
|       |-- config.py           # parse + validate config MCP
|       |-- models.py           # ServerSpec, ToolDescriptor, CatalogRevision
|       |-- naming.py           # canonical name, sanitize, collision handling
|       |-- catalog.py          # discovery cache, schema hash, quarantine
|       |-- manager.py          # session/process lifecycle, health, reconnect
|       |-- adapter.py          # McpToolPort -> session.call_tool
|       `-- normalize.py        # CallToolResult -> CapabilityResult data
|-- safety/
|   |-- policy.py               # policy engine duy nhat; mo rong ban hien tai
|   |-- risk.py                 # risk classification va override
|   |-- approvals.py            # approval request/grant, TTL, one-time binding
|   |-- validation.py           # input/output JSON Schema validation
|   `-- secrets.py              # secret reference resolver + redaction
|-- middleware/
|   |-- policy.py               # bridge kernel middleware -> safety policy engine
|   |-- approval.py             # short-circuit khi can human approval
|   |-- rate_limit.py           # quota theo run/server/tool
|   |-- retry.py                # retry dua tren descriptor/idempotency
|   `-- output_guard.py         # size cap, content marking, redaction
|-- orchestrator/
|   |-- tool_view.py            # chon tool agent duoc thay theo task/profile
|   `-- approval_flow.py        # checkpoint waiting_for_approval + resume
|-- config/
|   |-- features.yaml
|   |-- mcp_servers.yaml        # connection inventory, khong chua secret that
|   |-- tool_policies.yaml      # risk/action/approval override review duoc
|   `-- tool_profiles.yaml      # coding, research, ops, ...
`-- tests/
    |-- mcp/
    |   |-- test_catalog.py
    |   |-- test_manager.py
    |   |-- test_adapter.py
    |   `-- test_schema_change.py
    |-- safety/
    |   |-- test_mcp_policy.py
    |   |-- test_approvals.py
    |   `-- test_output_guard.py
    `-- integration/
        `-- test_mcp_call_pipeline.py
```

Khong can tao tat ca file trong PR dau. Layout nay la bien so huu lau dai; rollout o muc 13 chia no thanh cac
buoc nho.

### 3.2 Trach nhiem va bien gioi

| Module | Duoc lam | Khong duoc lam |
|---|---|---|
| `config.py` | Parse config, expand secret reference qua resolver, validate field. | Ket noi server, goi tool. |
| `catalog.py` | `tools/list`, descriptor cache, schema hash, list-changed refresh. | Tu expose tool cho model, tu cho phep tool. |
| `manager.py` | Mot long-lived session/server, timeout, health, shutdown. | Policy business, prompt building. |
| `adapter.py` | Chuyen `ToolRequest` thanh `call_tool`, map loi transport. | Approval, retry mutation, ghi secret. |
| `normalize.py` | Chuan hoa text/image/audio/resource/structured content. | Tu dong mo resource URL hoac lam theo text trong result. |
| `safety/*` | Validate, classify, allow/deny/require approval, redact. | Quan ly MCP transport. |
| `tool_view.py` | Chon tap descriptor nho va render schema cho model. | Cap quyen vuot policy. |

## 4. Data contracts can them

Registry can dang ky mot descriptor bat bien cung executor, thay vi chi dang ky name.

```python
@dataclass(frozen=True)
class ToolDescriptor:
    canonical_name: str
    original_name: str
    feature: str
    source: str                 # local | mcp
    server_id: str | None
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    schema_hash: str
    trust: str                  # local | trusted | untrusted
    risk: str                   # low | medium | high | critical
    read_only: bool | None
    idempotent: bool | None
    open_world: bool | None
    timeout_seconds: float
    enabled: bool
```

Annotations MCP chi la input cho classifier. Theo spec, client phai xem annotations la untrusted neu server
chua duoc tin cay. Local policy override luon co uu tien cao hon annotation cua server.

Call context nen tach khoi args de khong bi gui nham sang MCP server:

```python
@dataclass(frozen=True)
class ToolCallContext:
    task_id: str | None
    run_id: str | None
    actor_id: str | None
    role: str
    profile: str
    deadline_at: str | None
    approval_grant_id: str | None
```

`ToolRequest.args` chi la arguments theo input schema. Context, secret va approval khong nam trong args.

`ToolResolution` nen tra ca `descriptor` va `executor`. Policy phai danh gia dung descriptor da resolve;
khong resolve lai mot phien ban khac sau approval.

## 5. Naming va catalog khi co nhieu server

### 5.1 Canonical name

Quy tac agent-facing:

```text
mcp.<server_id>.<normalized_original_name>
```

Vi du:

```text
mcp.github.search_issues
mcp.github.create_issue
mcp.postgres_ro.query
mcp.slack.send_message
```

Quy tac:

- `server_id` la ID on dinh trong config, khong lay tu display name cua server.
- Luu `original_name` rieng de gui den MCP server; khong gui canonical name.
- Normalize ve tap ky tu MCP tool name cho phep; cat do dai va them stable hash neu vuot gioi han/collision.
- Name collision la startup error hoac quarantine, khong "last write wins".
- Alias ngan nhu `create_issue` mac dinh bi cam. Chi cho alias explicit neu unique va co test.
- Catalog key gom `(server_id, original_name, schema_hash)`; thay schema la mot revision moi.

### 5.2 Tool list changed va schema drift

Khi server bao `tools/list_changed`:

1. Fetch list moi tren session do.
2. Tinh schema hash va diff descriptor.
3. Tool moi hoac tool doi input/output schema vao `quarantined`.
4. Chi activate neu van match allowlist va policy review; critical tool can explicit override.
5. Tool bi xoa tra `tool_unavailable`, khong fallback sang server/tool khac.
6. Emit event `mcp.catalog.changed` voi name/hash cu-moi, khong log secret.

Khong de mot server tu them tool moi roi lap tuc dua no vao prompt.

## 6. Khong de "nhieu tool" thanh "loan tool"

Phan biet ba tap:

1. **Catalog:** tat ca tool da discover; chi he thong thay.
2. **Enabled set:** tool duoc config va policy cho phep ton tai trong runtime.
3. **ToolView:** tap nho model duoc thay trong mot task/turn.

`ToolView` nen co gioi han cung, vi du 20 tool mac dinh va 40 toi da. Cach chon theo thu tu:

1. Profile tu request/role, vi du `coding`, `research`, `ops_readonly`.
2. Explicit include/exclude cua task.
3. Capability tags va server allowlist.
4. Sau nay moi them semantic retrieval tren description/schema.

Khong dung semantic score de cap quyen. Retrieval chi chon tool de hien; policy van quyet dinh tool co duoc
goi hay khong.

Profile mau:

```yaml
profiles:
  coding:
    max_tools: 20
    include:
      - fs_read
      - fs_write
      - terminal_run
      - mcp.github.search_issues
      - mcp.github.get_issue
    deny_risk: [critical]

  ops_readonly:
    max_tools: 15
    include_tags: [read, observe]
    deny_risk: [medium, high, critical]
```

Orchestrator phai render `name`, mo ta ngan va `input_schema` cua ToolView vao system/developer prompt.
Model khong nen tu doan arguments tu description text.

Neu can search catalog, co the them meta-tool read-only `tools.search`. Tool nay chi tra descriptor; no khong
activate tool va khong bypass profile/policy.

## 7. Config de xuat

### 7.1 `config/features.yaml`

```yaml
features:
  mcp_gateway:
    enabled: true
    module: integrations.mcp.feature
    servers_path: config/mcp_servers.yaml
    policies_path: config/tool_policies.yaml
    profiles_path: config/tool_profiles.yaml
```

`install(kernel)` doc cac path nay tu `kernel.config["features"]["mcp_gateway"]`; khong can doi signature cua
feature loader trong vertical slice dau tien.

### 7.2 `config/mcp_servers.yaml`

```yaml
version: 1

defaults:
  connect_timeout_seconds: 10
  call_timeout_seconds: 30
  max_concurrency: 4
  trust: untrusted
  expose: []                    # default deny

servers:
  github:
    enabled: true
    transport: stdio
    command: uvx                # static config, model khong duoc sua
    args: [github-mcp-server]
    env:
      GITHUB_TOKEN: ${secret:GITHUB_TOKEN}
    env_allowlist: [GITHUB_TOKEN]
    trust: trusted
    expose:
      - search_issues
      - get_issue
      - create_issue

  company_docs:
    enabled: true
    transport: streamable_http
    url: https://mcp.example.com/mcp
    auth:
      type: oauth
      audience: https://mcp.example.com
      scopes: [docs.read]
    expose:
      - search
      - fetch
```

Nguyen tac config:

- `expose` mac dinh rong. Khong co wildcard cho production; wildcard chi duoc dung trong local development
  voi warning va profile read-only.
- Khong luu token that trong YAML. `${secret:NAME}` duoc resolve luc connect va khong di vao registry/event.
- `command`, `args`, URL va transport den tu config do operator quan ly, khong bao gio den tu model arguments.
- Remote HTTP dung HTTPS va host allowlist. Redirect, OAuth discovery va audience phai duoc validate.
- Moi stdio server chi nhan env allowlist cua no, khong inherit toan bo environment cua host.

### 7.3 `config/tool_policies.yaml`

```yaml
version: 1

defaults:
  unknown_tool: deny
  unknown_risk: require_approval
  untrusted_server: require_approval

rules:
  - match: mcp.github.search_issues
    risk: low
    action: allow
    retry: read_only

  - match: mcp.github.create_issue
    risk: high
    action: require_approval
    retry: never

  - match: "mcp.*.*delete*"
    risk: critical
    action: deny

  - match: mcp.company_docs.*
    risk: low
    action: allow
    constraints:
      max_calls_per_run: 20
      max_result_bytes: 200000
```

Rule exact co uu tien hon glob; deny co uu tien hon allow. Config loader phai fail closed khi rule conflict.

## 8. Policy cho tool nguy hiem

### 8.1 Risk matrix

| Risk | Vi du | Default action | Retry |
|---|---|---|---|
| `low` | Search/read, list metadata, query read-only | Allow trong profile | Co gioi han neu idempotent |
| `medium` | Ghi reversible trong workspace, tao draft | Approval hoac bounded delegation | Mac dinh khong |
| `high` | Gui message/email, tao issue public, sua remote data | Exact approval moi call | Khong |
| `critical` | Xoa, admin, credential, money, publish/deploy | Deny; explicit enable + exact approval | Tuyet doi khong |

`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` cua MCP chi ho tro classifier. Chinh sach
cuc bo va trust tier moi la nguon quyet dinh.

### 8.2 Thu tu policy

Policy pipeline de xuat:

```text
resolve immutable descriptor
-> check tool/profile enabled
-> validate + normalize input schema
-> redact preview fields
-> hard deny rules
-> risk/trust classification
-> scope/quota/rate checks
-> approval check
-> idempotency-aware retry plan
-> execute with timeout
-> validate output schema
-> output guard + audit
```

Input validation phai chay truoc approval de user thay dung call se duoc gui. Policy phai chay lai sau khi co
approval grant va truoc execution.

### 8.3 Approval dung cach

Approval request gom:

```text
approval_request_id
task_id + run_id + actor_id
canonical tool + server_id
normalized args preview
args_digest + descriptor schema_hash
risk + reason + external side effect
expires_at
```

Approval grant phai:

- Do UI/API tin cay tao, khong doc tu model output hay MCP result.
- Bind vao `task_id`, `tool`, `args_digest`, `schema_hash` va actor.
- Co TTL ngan va one-time use.
- Vo hieu neu args, tool schema, actor hoac run thay doi.
- Duoc audit nhung khong ghi secret/raw credential.

Flow phu hop voi checkpoint hien tai:

```text
policy -> require_approval
orchestrator -> save checkpoint(status="waiting_for_approval")
run returns pending approval envelope
user approves/denies through trusted boundary
resume(run_id) -> re-resolve + revalidate + consume grant -> execute
```

Khong giu process cho doi prompt vo thoi han. MCP elicitation neu co cung khong thay the approval cua host;
day la hai flow co muc dich khac nhau.

### 8.4 Retry va ket qua khong xac dinh

Sua `middleware/Retry` truoc khi cho phep MCP write tools:

- Chi retry khi descriptor noi ro `read_only=True` hoac local policy dat `idempotent=True`.
- Chi retry transient transport errors nam trong allowlist.
- Khong retry validation error, policy/approval block, server-declared tool error hay timeout cua mutation.
- Timeout sau khi request da gui co the la `outcome=indeterminate`, khong duoc coi la failed an toan de retry.
- Voi side effect, dung read-back/reconciliation tool de kiem tra trang thai truoc khi user quyet dinh goi lai.

## 9. Transport, auth va secret

### 9.1 stdio

- Uu tien cho local server.
- Khoi dong mot process moi server va giu session song; khong spawn moi call.
- Command/args la static operator config va can allowlist executable/package.
- Moi server co working directory, env allowlist, timeout, output cap va process isolation rieng.
- Stderr la log server, stdout chi danh cho MCP protocol.
- Local server van la code co quyen chay tren may; "local" khong dong nghia "trusted".

### 9.2 Streamable HTTP

- Chi HTTPS trong production; endpoint host phai allowlist.
- Dung implementation cua SDK chinh thuc, khong tu viet JSON-RPC/SSE.
- Bao ve session ID; session ID khong phai authentication.
- OAuth token phai dung audience/server do; khong token passthrough sang downstream service.
- Request scope theo least privilege, tang scope co chu dich va audit.
- Validate discovery/redirect URL de tranh SSRF, dac biet neu host chay server-side.

### 9.3 Secret

- Token khong nam trong prompt, `ToolRequest.args`, checkpoint, event log hay error message.
- Secret resolver tra secret truc tiep cho transport/auth provider.
- Redactor biet key pattern (`token`, `secret`, `password`, `authorization`, `cookie`) va explicit schema field.
- Khong dua toan bo host environment cho stdio child process.

## 10. Output guard va prompt injection

MCP tool result la du lieu ben ngoai, ke ca khi server trusted.

`normalize.py` nen giu ro loai content:

```python
{
    "content": [...],
    "structured_content": {...},
    "is_error": False,
    "source": {"type": "mcp", "server_id": "github", "tool": "search_issues"},
    "untrusted": True,
}
```

Output guard phai:

1. Validate `structuredContent` theo `outputSchema` neu co.
2. Gioi han byte/block/image/resource link va condense truoc khi dua lai model.
3. Redact credential/PII theo policy.
4. Khong tu dong fetch `resource_link` hoac mo URL do result tra ve.
5. Khong bien text trong result thanh system/developer instruction.
6. Giu provenance de prompt noi ro day la observation, khong phai authority.
7. Tach protocol error, tool-declared error, timeout va policy block trong metadata.

## 11. Lifecycle va sync/async

Python SDK dung async context manager. Project hien tai sync, vi vay can mot lifecycle ro rang.

Muc tieu lau dai:

```python
async with create_runtime(config) as runtime:
    result = await runtime.run(...)
```

Trong giai doan chuyen tiep co the giu `AgentKernel.execute_tool()` sync bang mot AnyIO blocking portal/background
event loop duy nhat trong `McpSessionManager`. Tuyet doi khong:

- `asyncio.run()` cho moi call;
- tao/initialize MCP session cho moi call;
- dung event loop thread khac nhau cho cung mot session;
- de stdio process mo ma khong co `close()`/shutdown.

Nen them `create_runtime()` ben canh `create_kernel()` de giu backward compatibility. Runtime so huu manager,
session va cleanup; kernel van chi so huu capability execution.

Manager can co state machine:

```text
disabled -> disconnected -> connecting -> ready -> degraded -> closed
```

Mot server hong khong lam bootstrap toan bo agent hong neu profile khong bat buoc server do. Health va catalog
revision phai quan sat duoc.

## 12. Observability can them

Event de xuat:

```text
mcp.server.connecting
mcp.server.ready
mcp.server.failed
mcp.catalog.loaded
mcp.catalog.changed
tool.policy.decided
tool.approval.requested
tool.approval.granted
tool.approval.denied
tool.execution.started
tool.execution.completed
tool.execution.indeterminate
```

Field toi thieu:

```text
run_id, task_id, request_id, actor_id
canonical_tool, server_id, transport
schema_hash, catalog_revision
risk, policy_action, policy_rule_id
approval_request_id (neu co)
duration_ms, timeout_ms, retry_count
result_size, result_digest, error_class
```

Khong log raw secret. `tool.requested` hien tai dang ghi raw args; can doi thanh redacted args hoac
`args_digest + safe_preview` truoc khi bat MCP production.

Metrics nen co:

```text
mcp_connections, mcp_connection_failures, mcp_calls, mcp_timeouts
policy_denies, approval_requests, approval_denies
schema_changes, quarantined_tools, indeterminate_calls
```

## 13. Dau noi vao project

### 13.1 Bootstrap

`integrations.mcp.feature.install(kernel)` chi lam registration/lifecycle binding:

```python
def install(kernel: AgentKernel) -> None:
    cfg = load_mcp_config(kernel.config)
    manager = McpSessionManager(cfg, events=kernel.events)
    catalog = McpToolCatalog(manager, cfg)

    for descriptor in catalog.enabled_descriptors():
        kernel.registry.register_tool(
            descriptor.canonical_name,
            McpToolPort(descriptor, manager),
            descriptor=descriptor,
            feature_name="mcp_gateway",
        )
```

Thuc te discovery async nen `create_runtime().start()` se connect/list tools truoc, hoac feature dung lazy
catalog co explicit startup phase. Khong che giau network I/O trong import module.

### 13.2 Middleware order

Thu tu muc tieu ngoai -> trong:

```text
Trace/Timing
-> ResolveContext
-> InputValidation
-> Policy
-> Approval
-> Rate/Budget
-> RiskAwareRetry
-> executor (local hoac MCP)
-> OutputValidation/Guard
-> Condense
```

`PolicyGate` hien tai la deny-set; nen bien no thanh adapter goi `ToolPolicyEngine`. `SafeToolPort` giu tam cho
toolbox trong giai doan migration, sau do toolbox cung di qua global pipeline de chi con mot nguon policy.

### 13.3 Orchestrator

Truoc moi LLM call:

1. Lay ToolView cua task/profile.
2. Render tool descriptors/schema vao prompt hoac API tool schema.
3. Parse action va kiem tra tool nam trong ToolView.
4. Goi `kernel.execute_tool()`; kernel policy van re-check, vi ToolView khong phai authorization.
5. Neu pending approval, checkpoint va return; khong dua request cho model tu phe duyet.
6. Dua normalized, guarded observation lai model.

Nen chon `orchestrator/loop.py` lam runtime agent chinh cho MCP. `graph/runtime.py` co the tai su dung
`ToolView` va approval flow sau; khong nhan doi MCP manager/policy trong `graph/`.

## 14. Rollout theo PR

### PR 1 - Descriptor va registry, chua ket noi MCP

- Them `ToolDescriptor` va schema/risk/source metadata.
- Registry register/describe descriptor va reject collision.
- Them `ToolCallContext`/resolved call seam.
- Redact `tool.requested` args.
- Test backward compatibility voi echo/toolbox.

### PR 2 - Hop nhat safety pipeline

- `PolicyDecision = allow | deny | require_approval`.
- Descriptor-aware `PolicyGate` va risk-aware retry.
- Them input/output validation, rate limit, event fields.
- Toolbox chay qua global policy; deprecate `SafeToolPort` sau khi test parity.

### PR 3 - MCP read-only vertical slice

- Them optional dependency `mcp>=1.28,<2` va JSON Schema validator.
- Implement config, naming, manager, catalog, adapter.
- Chi stdio + read-only allowlist; default deny tool unknown/write.
- Fake MCP server trong test, khong phu thuoc network.

### PR 4 - ToolView va orchestrator

- Render schema trong prompt.
- Profiles va max-tool cap.
- Catalog/list-changed quarantine.
- Checkpoint/resume van hoat dong khi server reconnect.

### PR 5 - Approval

- Approval store/API, one-time digest-bound grant.
- `waiting_for_approval` checkpoint state.
- High/critical policy va audit tests.

### PR 6 - Streamable HTTP + OAuth

- HTTPS/host allowlist, OAuth discovery, audience/scope checks, SSRF controls.
- Session lifecycle, reconnect va health metrics.
- Khong enable production truoc threat-model review.

## 15. Test bat buoc

### Catalog va naming

- Hai server co cung tool name khong collision.
- Ten qua dai/ky tu la duoc map on dinh va reversible ve original name.
- Tool moi/schema drift bi quarantine.
- Disabled/unexposed tool khong vao ToolView.

### Policy

- Untrusted annotations khong ha risk.
- Unknown tool/risk fail closed.
- High-risk exact approval; args thay doi lam grant mat hieu luc.
- Grant het TTL/da consume/khac task bi deny.
- Model text va MCP output khong the tao approval grant.

### Execution

- Input sai schema bi chan truoc network call.
- Read-only transient error retry co gioi han.
- Mutation timeout tra indeterminate va khong retry.
- Output sai schema bi danh dau/chan truoc khi vao model.
- Size cap, timeout, concurrency va cancellation hoat dong.

### Secrets va observability

- Token khong xuat hien trong events, checkpoint, errors hay prompt.
- Child stdio chi nhan env allowlist.
- Moi decision/call co run/task/request correlation.
- Observer hong khong lam crash runtime.

### Lifecycle

- Mot process/session cho nhieu call.
- Startup failure cua server tuy chon khong lam sap kernel.
- Close runtime dong session/process.
- Resume khong thuc thi lai mutation da co outcome indeterminate.

## 16. Definition of done cho MCP production

- Tat ca MCP calls di qua `AgentKernel.execute_tool()`.
- Khong co direct `session.call_tool()` ngoai `integrations/mcp/adapter.py`.
- Registry co descriptor/schema/risk/source cho moi tool.
- ToolView co cap va khong expose full catalog.
- Default deny cho server/tool moi; schema drift quarantine.
- Sensitive tool co human approval bind dung arguments.
- Mutation khong retry tu dong.
- Input/output schema validation va output guard bat.
- Secret khong vao prompt/log/checkpoint.
- Long-lived session co startup/shutdown ro rang.
- Co fake-server integration tests cho stdio va HTTP truoc khi production.

## 17. Tai lieu doi chieu

- [MCP architecture, spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/architecture)
- [MCP tools, schemas, annotations va security](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- [MCP transports: stdio va Streamable HTTP](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [MCP authorization](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)
- [MCP security best practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

## 18. Khuyen nghi uu tien ngay

Chua nen bat MCP write tool ngay. Thu tu ngan gon de co gia tri som ma van kiem soat duoc:

1. Descriptor-rich registry + redacted events.
2. Risk-aware policy/retry va mot global safety path.
3. Mot stdio MCP server read-only, allowlist 2-5 tool.
4. ToolView/profile trong orchestrator.
5. Sau khi audit tot moi them approval va write tool.

Kien truc nay cho phep tang tu vai tool len nhieu server ma kernel van nho: protocol o integration, quyen o
safety, cross-cutting behavior o middleware, tool selection o orchestrator, va moi execution van di qua mot
chokepoint co the quan sat.
