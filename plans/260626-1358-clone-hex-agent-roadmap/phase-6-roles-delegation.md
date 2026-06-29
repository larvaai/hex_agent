---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 6 — Roles & Multi-agent delegation

> Epic: E09 + E10 · Cổng vào: Phase 4 + 5 · Rời phase với: multi-agent loop chạy LLM thật (Agent O compose team → decide → judge), mỗi worker chạy trong child session có **scope con ⊆ cha**, và acceptance chỉ "passed" khi cited id resolve được + ≥1 là evidence thật — không phải scaffolding của chính loop.

## 1. Mục tiêu & ranh giới

Bốn phase trước cho bạn **một** agent: một graph (Phase 4), nói được với LLM kỷ luật (Phase 2), gọi tool an toàn qua toolbox (Phase 3), bind skill (Phase 5). Phase 6 nhân nó lên thành **nhiều** agent — mà vẫn audit được từng nước đi và không cho ai leo quyền.

Ba ý lớn, đọc kỹ trước khi gõ phím:

- **Role là danh tính, có MỘT định nghĩa.** `RoleSpec` (yaml) là nguồn chân lý cho cả đường single-agent (Phase 4) lẫn multi-agent (phase này). Cùng một `AgentRegistry.build_agent` dựng ra `Agent` cho cả hai. Role tự **enforce allowlist** của nó — tool ngoài danh sách bị chặn ngay tại agent, không đợi tới kernel.
- **Delegation là một cái cửa RIÊNG, không phải method của kernel.** Khi một agent giao việc cho agent khác, nó đi qua `DelegationManager.delegate` — một chokepoint thứ hai, song song với `execute_tool` của kernel (chokepoint thứ nhất, Phase 1). Cái cửa này validate depth/budget/scope, mở child session, persist progress, rồi publish event. Bỏ qua nó = mất audit + cho con leo quyền vượt cha.
- **Agent O không tin lời chính nó.** Supervisor (Agent O) điều phối nhiều worker trên một **Blackboard** serializable. Khi O báo "xong" (`finished`), cổng acceptance không tin ngay: nó đòi mọi id O trích dẫn phải có thật trên Blackboard, **và** ít nhất một id phải là evidence thật (diff/test_result/tool_result…), không phải `session_plan`/`context_packet`/`ac_report` mà loop tự đẻ ra. O không thể "pass" bằng cách trỏ vào giàn giáo của chính nó.

Trong phase: `roles/` (E09 — role spec/registry/allowlist + lenses), `delegation/` (chokepoint riêng), `supervisor/` (E10 — Blackboard + Agent O loop + context broker + acceptance evidence gate + SQLite checkpoint), một adapter delegation chạy trên graph Phase 4.

Ngoài phase: Departments (alias gom role, DEC-2 — park), Router/GlobalSupervisor đa-task (E12 — park), control plane realtime + roster-growth lúc chạy (E21). Ở đây delegation là **tuần tự**, **không đệ quy** (worker không tự gọi worker), O là delegator duy nhất.

Ranh giới cứng: phase này sống **TRÊN** kernel đã `freeze()`, không sửa kernel. `supervisor/` và `delegation/` là lớp application service, gọi xuống `execute_tool` và `create_child` — không thêm đường thực thi mới nào.

Một bức tranh để giữ trong đầu suốt phase — **hai chokepoint song song, một cây session**:

```
     ┌─────────────── supervisor/ (Agent O loop) ───────────────┐
     │  compose_team → o_decide → run_round → judge_acceptance   │   ← lớp ABOVE
     └───────────────┬──────────────────────┬───────────────────┘
                     │ delegate()           │ execute_tool()
            ┌────────▼─────────┐   ┌─────────▼──────────┐
            │  delegation/     │   │   core/kernel.py   │             ← hai cửa
            │  manager.py:63   │   │   execute_tool     │
            │  (policy+scope)  │   │   (Phase 1)        │
            └────────┬─────────┘   └────────────────────┘
                     │ create_child(scope ⊆ parent)
            ┌────────▼─────────┐
            │  child session   │  ← worker = graph Phase 4 (đệ quy delegation TẮT)
            └──────────────────┘
```

Agent O ở trên cùng, không phải trong kernel. Nó dùng **hai** cửa: `execute_tool` (xin tool / gọi LLM) và `delegate` (giao việc cho worker). Worker là một child session chạy lại graph Phase 4 — nên "multi-agent" thực ra là "single-agent lồng nhau, có cổng kiểm soát ở mỗi mép".

## 2. Bạn sẽ xây gì (bản đồ module)

| file | vai trò | class/hàm chính |
|---|---|---|
| `roles/spec.py` | RoleSpec canonical + RoleView (projection E10) + loader; **chỗ DUY NHẤT** role gặp skill để suy allowlist | `RoleSpec`, `RoleView`, `TestOwnership`, `allowed_tools`, `parse_role`, `load_role_file` |
| `roles/agent.py` | Agent = role bound skill/lens, **enforce allowlist** + separation-of-duties | `Agent`, `guard_tool_call`, `guard_finish`, `build_prompt` |
| `roles/lenses.py` | viewpoint review (correctness/security…) render vào prompt | `LensSpec`, `LensRegistry`, `parse_lens` |
| `roles/registry.py` | **MỘT** store role, chia sẻ single ↔ multi | `AgentRegistry`, `build_agent`, `role_view`, `list_roles` |
| `delegation/manager.py` | chokepoint delegation: policy → child → progress → result | `DelegationManager.delegate` (`:63`) |
| `delegation/policy.py` | enforce depth/budget + **scope con ⊆ cha** | `DelegationPolicyEngine.validate` |
| `delegation/registry.py` | target → port, fail tường minh khi mơ hồ | `DelegationRegistry.resolve` |
| `delegation/store.py` | progress thread-safe, ordered, idempotent (persist trước publish) | `InMemoryDelegationStore` |
| `delegation/bootstrap.py` | wire target local mặc định | `create_delegation_service` |
| `adapters/agents/langgraph_agent.py` | DelegationPort cụ thể — chạy graph Phase 4 làm worker | `LangGraphDelegationAgent` |
| `supervisor/state.py` | TaskLoopState = Blackboard serializable | `TaskLoopState`, `AcceptanceCheck`, `AgentTurn`, `encode/decode` |
| `supervisor/contracts.py` | hợp đồng JSON: SessionPlan / OrchestratorDecision / ContextPacket | `parse_session_plan`, `parse_decision`, `AgentAssignment` |
| `supervisor/orchestrator.py` | port Agent O (scripted offline) | `OrchestratorPort`, `ScriptedOrchestrator` |
| `supervisor/broker.py` | Context Broker: briefing just-enough, **không bao giờ set scope** | `BrokerPort`, `DeterministicBroker` |
| `supervisor/graph.py` | các node: compose_team / o_decide / run_round / run_tool / judge_acceptance | `SupervisorContext`, `judge_acceptance` (`:238`) |
| `supervisor/evidence.py` | phân loại evidence cho cổng acceptance (DEC-7) | `evidence_type_of`, `NON_EVIDENCE_KINDS`, `record_ac_report` |
| `supervisor/loop.py` | facade: `run_task_loop` + `resume_task_loop` + loop-guard cơ học | `_drive`, `_terminate` |
| `supervisor/checkpoint.py` | SQLite checkpoint cho Blackboard = nguồn chân lý resume | `SqliteTaskLoopStore` |
| `supervisor/llm.py` | Agent O + Broker bản LLM thật, qua `llm.chat` | `LLMOrchestrator`, `LLMBroker`, `KernelChatLLM` |

## 3. Dựng step-by-step

Thứ tự bám đúng dây phụ thuộc: roles trước (không phụ thuộc gì trong phase) → delegation (cần roles cho scope nhưng độc lập supervisor) → adapter → Blackboard state → các node O → evidence gate → checkpoint resume. Mỗi bước tự kiểm offline.

**B1 — `roles/spec.py`: role→allowlist suy ở MỘT chỗ.**
`RoleSpec` là frozen dataclass. Trái tim là `allowed_tools(skills, core_tools)` (`spec.py:53`): union(explicit_tools, core_tools, các tool skill khai) **trừ** forbidden của skill — **forbidden thắng** (`spec.py:63`). Đây là chỗ duy nhất skill (Phase 5) gặp role. `TestOwnership(owns_validation, must_handoff_to)` đánh dấu separation-of-duties. `parse_role` raise `ValueError` nêu tên file + field thiếu.
Tự kiểm: load `roles/library/code.yaml` → `owns_validation==False`, `must_handoff_to=="test"`, `allowed_tools` chứa `fs_read` nhưng không chứa tool nào bị skill `file_edit` cấm.

**B2 — `roles/lenses.py`: viewpoint thành prompt.**
`LensSpec` (frozen) có `name/purpose/allowed_tools/forbidden_tools/output_schema`, `render()` ra block markdown. `LensRegistry` load từ yaml, tên unique (register trùng → `ValueError`). Một role chỉ render các lens nó khai (`spec.lenses`).
Tự kiểm: `LensRegistry().load_file("roles/library/lenses/security_review.yaml")` rồi `.render("security_review")` chứa `### Lens:`.

**B3 — `roles/agent.py`: Agent enforce allowlist + chặn tự-chứng-thực.**
Constructor làm hai việc quan trọng: (1) **fail-fast separation-of-duties** — role không own validation mà không khai `must_handoff_to` thì raise ngay khi dựng (`agent.py:31`), vì việc của nó sẽ không ai validate được. (2) Resolve `allowed_tools` một lần. Hai guard loop sẽ gọi: `guard_tool_call(tool)` trả envelope blocker nếu tool ngoài allowlist (`agent.py:45`), `guard_finish(claim_validated)` ép handoff nếu role không own validation mà đòi tự đóng dấu "đã validate" (`agent.py:56`).
Tự kiểm: dựng Agent từ `code.yaml`; `guard_tool_call("rm_rf")` trả dict `finish_reason=="blocker"`; `guard_finish(claim_validated=True)` trả `handoff_to=="test"`.

**B4 — `roles/registry.py`: MỘT store, hai đường dùng.**
`AgentRegistry` giữ `RoleSpec` + skill/lens registry + core_tools. `build_agent(name)` là cái mà **cả** Phase 4 (single) lẫn phase này (multi) gọi — nên một role có đúng một định nghĩa (S09.6). `list_roles()` trả tuple `RoleView` (slim: agent_id/role/system_prompt/default_scope) cho Agent O đọc catalog.
Tự kiểm: register 1 role rồi `build_agent` hai lần → hai Agent object nhưng cùng `spec`; `list_roles()[0]` là `RoleView` có `default_scope` là frozenset.

**B5 — `delegation/policy.py`: cái van scope (đọc kỹ nhất phase).**
`DelegationPolicyEngine(max_steps=100, max_depth=8)`. `validate(parent, requested)` (`policy.py:13`) làm bốn việc theo thứ tự: kiểm `max_steps`/`max_depth` trong biên → kiểm `parent.depth + 1 <= max_depth` (raise `PermissionError` nếu sâu quá) → lấy `scope = requested.allowed_capabilities or parent.allowed_capabilities` → **kiểm `scope <= parent.allowed_capabilities`** (`policy.py:26`), không phải subset thì `PermissionError`. Trả về policy đã chuẩn hoá với scope đông cứng.
Để ý một cạm bẫy tinh tế trong `scope = requested or parent`: nếu O **không** khai scope (`allowed_capabilities` rỗng), worker **kế thừa nguyên scope cha** — không phải "deny all". Muốn hẹp thì O phải khai tường minh. (Đối lập với `create_child`: ở đó `requested_scope=None` mới là "inherit", còn `frozenset()` rỗng tường minh = "deny all" — `core/session.py:160-162`. Hai chỗ, hai mặc định khác nhau; đừng nhầm.)
Tự kiểm: parent scope `{a,b}`; `validate` với requested `{a}` OK (con hẹp hơn); với `{a,c}` raise `PermissionError` (con rộng hơn → leo quyền); với requested rỗng → scope = `{a,b}` (kế thừa); với `max_depth=0` hoặc `max_steps=0` → `ValueError`; với parent depth = `max_depth` → `PermissionError` (đệ quy sâu quá).

**B6 — `delegation/registry.py` + `store.py`.**
`DelegationRegistry.resolve(target)` (`registry.py:27`): lọc handler `can_handle(target)`; 0 match → `LookupError`, **>1 match → `LookupError` mơ hồ tường minh** (không chọn bừa). `freeze()` khoá trước session đầu. `InMemoryDelegationStore`: progress phải tăng đúng `sequence = len+1` (`store.py:32`), `event_id` trùng → no-op idempotent, kết quả ghi đè khác nhau → `ValueError`. Quy tắc: **persist trước, publish sau** — store là source of truth.
Tự kiểm: hai handler cùng `can_handle("x")` → `resolve("x")` raise "Ambiguous"; append progress sequence 2 khi mới có 0 item → `ValueError`.

**B7 — `delegation/manager.py`: chokepoint riêng (`:63`).**
`delegate(parent, target, spec, policy)` là cái cửa. Trình tự (đọc `manager.py:63-192`): chặn parent inactive/target rỗng/objective rỗng → `policy.validate` (lỗi → ghi request "rejected" rồi `_finish`, **vẫn** vào store + event, không nuốt im) → `registry.resolve` → `sessions.create_child(..., requested_scope=active_policy.allowed_capabilities)` → set `delegation_policy` lên child state → chạy `handler.run(request, child, progress_sink)`. `progress_sink` kiểm `delegation_id` khớp + `sequence <= max_steps`, **append store trước, publish event sau** (`manager.py:147`). Cuối: gộp artifact (progress trước, result-only sau, khử trùng theo `artifact_id`), đóng child (`complete_task`/`fail_task`), `_finish` publish `delegation.finished`.
Tự kiểm với `ScriptedDelegationAgent`: delegate scope vượt cha → `outcome=="rejected"`, error nói "scope exceeds"; delegate hợp lệ → `outcome=="success"`, store có progress đúng thứ tự.

**B8 — `adapters/agents/langgraph_agent.py`: worker = graph Phase 4.**
`LangGraphDelegationAgent(target)` implement `DelegationPort`: `can_handle(target)` so tên, `run(...)` dựng `AgentState` mới cho child session, build graph Phase 4 (`build_agent_graph(..., delegation_service=None)` — **đệ quy delegation tắt ở v1**), stream từng step, emit `ArtifactEnvelope(kind="agent_step")` qua `progress_sink`, trả `DelegationResult` outcome theo status cuối. `bootstrap.create_delegation_service` chỉ wire nó khi `config["delegation"]["enabled"]`.
Tự kiểm: chạy delegate qua adapter này với một objective đơn giản, kiểm `result.summary["child_session_id"]` khác parent.

**B9 — `supervisor/state.py`: Blackboard chỉ chứa primitive.**
`TaskLoopState` là dataclass thường (mutable, để node sửa tại chỗ) nhưng **mọi field serializable**: `selected_agents: list[str]`, `acceptance_checks`, `turns`, `artifacts: dict[str, dict]`, `tool_results`, `final_output`. `encode_taskloop_state`/`decode_taskloop_state` round-trip qua JSON. `AcceptanceCheck.is_satisfied` = `status=="passed" and có evidence_ids`. `all_accepted()` = có check **và** mọi check satisfied.
Tự kiểm: `decode_taskloop_state(encode_taskloop_state(s)) == s` về mặt nội dung; không có object không-serializable nào lọt vào artifacts.

**B10 — `supervisor/contracts.py` + `orchestrator.py` + `broker.py`: hợp đồng + O scripted + Broker.**
`parse_session_plan`/`parse_decision` dùng lại json-gate Phase 2 (`parse_json_object`), schema sai → `JsonGateError`. `OrchestratorDecision.decision ∈ {continue,need_tool,finished,blocked,failed}`. **`AgentAssignment.allowed_capabilities`** là chỗ DUY NHẤT scope worker được đặt — `ContextPacket` (Broker viết) **không có field scope** (`contracts.py:59`, `to_spec` không map scope). `ScriptedOrchestrator` trả JSON canned để test offline; `DeterministicBroker.write_packet` build briefing chỉ từ slice được trao, gắn `source_ids` (provenance), cắt theo `char_budget` — và emit **không** field scope nào.
Tự kiểm: `parse_decision('{"decision":"finished"}')` OK; `parse_decision('{"decision":"x"}')` raise; `ContextPacket(...).to_spec()` ra `DelegationSpec` không có capability.

**B11 — `supervisor/graph.py`: năm node trên Blackboard.**
Mỗi node nhận `(state, ctx)` và sửa state tại chỗ. `compose_team` parse SessionPlan, **validate trước khi mutate**: chặn agent trùng + agent ngoài catalog (`graph.py:91-98`), set `selected_agents`. `o_decide` parse một decision, JSON hỏng thì `budget.record_parse_error` + re-prompt, hết budget trả `None`. `run_round`: **authority check toàn batch trước** (assignment phải target agent đã compose — `graph.py:142-148`), rồi mỗi assignment: Broker viết packet → **kiểm packet.target == assignment.agent_id** (Broker không được đổi hướng turn) → `DelegationPolicy(allowed_capabilities=assignment.allowed_capabilities)` (scope CHỈ từ O, `graph.py:175`) → `delegation_service.delegate` → merge artifact + `checkpoint` sau mỗi turn. `run_tool` cho O xin tool — đi qua `supervisor_session.execute_tool` (chokepoint kernel). `judge_acceptance` ở B12.
Tự kiểm: assignment tới agent chưa compose → `run_round` raise `PermissionError`; Broker trả packet target lệch → raise `PermissionError`.

**B12 — `supervisor/evidence.py` + `judge_acceptance`: cổng theo evidence (DEC-7).**
Đây là chỗ "judge ≠ doer" được thực thi. `evidence_type_of(artifact)` (`evidence.py:26`) suy loại từ `artifact.kind` theo ba nhánh:

| `artifact.kind` | `evidence_type_of` trả | nghĩa |
|---|---|---|
| `""` (rỗng) **hoặc** ∈ `NON_EVIDENCE_KINDS` | `None` | KHÔNG phải evidence — scaffolding hoặc vô danh |
| ∈ `EVIDENCE_TYPES` (`artifact/tool_result/reviewer_report/diff/test_result`) | chính nó | evidence có loại |
| worker kind lạ + `delegation_result` | `"artifact"` | evidence generic (trust-worker) |

`NON_EVIDENCE_KINDS={session_plan, context_packet, ac_report}` — đúng ba thứ loop **tự đẻ ra về chính nó**: kế hoạch team, gói briefing, báo cáo AC. Threat model (DEC-7): mối nguy là **O trích nhầm scaffolding**, không phải worker thù địch — nên worker kind lạ vẫn được tin là `artifact`.
`judge_acceptance` (`graph.py:238`): honor `passed` chỉ khi **mọi** id cited resolve trên Blackboard **VÀ ≥1** id có `evidence_type_of != None`. **≥1-valid, KHÔNG all-valid** — O được kèm một id scaffolding cạnh evidence thật mà không bị chặn oan; nhưng nếu CHỈ có scaffolding thì không pass (chặn red-team FM-HIGH). `record_ac_report` (`evidence.py:60`) chụp trạng thái AC khi FINISHED thành một artifact `kind=ac_report` (id `ac_report-{session_id}` → idempotent qua resume) — và vì `ac_report ∈ NON_EVIDENCE_KINDS`, báo cáo này không bao giờ tự làm evidence cho chính mình.
Tự kiểm: AC cite chỉ một `session_plan` id → vẫn `pending`; cite một `diff` id + một `context_packet` id → `passed` (≥1-valid); cite id không tồn tại trên Blackboard → `pending` (all-exist fail).

**B13 — `supervisor/loop.py`: facade + loop-guard cơ học.**
`run_task_loop` dựng state, `compose_team`, rồi `_drive`. `_drive` lặp: check `max_rounds` → `o_decide` → theo `decision.decision` route (finished→judge+all_accepted→record_ac_report→terminate; need_tool→run_tool+judge; continue→run_round+judge; blocked/failed→terminate). **Loop-guard tách rời O**: terminate nếu max_rounds, nếu một round không tiến triển (artifact + acceptance snapshot không đổi — `loop.py:193`), hoặc O lặp y hệt decision quá `max_decision_repeats`. Checkpoint ở mỗi round boundary.
Tự kiểm: O luôn trả `continue` mà không sinh artifact → loop terminate `BLOCKED "no progress"`, không treo vô hạn.

**B14 — `supervisor/checkpoint.py`: SQLite = chân lý resume.**
`SqliteTaskLoopStore(run_id)`: `run_id` phải là **một** path segment (path-like → `ValueError`, chặn escape khỏi `runs_dir`). `save` upsert `encode_taskloop_state` vào một row; `load` decode hoặc `None`. `resume_task_loop` (`loop.py:108`): load state, **kiểm identity** (session_id + task_id của checkpoint phải khớp supervisor session đang chạy — `loop.py:128`, không cho session lạ nhận Blackboard của run khác), nếu terminal trả luôn, ngược lại `_drive` tiếp. `run_round` skip agent đã có turn trong round (worker turn không bao giờ chạy lại).
Tự kiểm: chạy nửa chừng, `save`, `load`, `resume` từ session khác identity → `ValueError`; resume đúng session → tiếp tục từ round dang dở.

**B15 — `supervisor/llm.py`: O + Broker bản thật.**
Swap `ScriptedOrchestrator`/`DeterministicBroker` bằng `LLMOrchestrator`/`LLMBroker`, cùng port, cùng json-gate. Cả hai gọi model qua `KernelChatLLM` → `execute_tool("llm.chat")` — tức **qua chokepoint kernel**, được observe + discipline như mọi capability. Guardrail giữ trong CODE, không tin model: Broker `source_ids` giao với slice id thật (id ảo bị bỏ — `llm.py:127`), briefing cắt `char_budget`, packet **không có scope field**.
Tự kiểm: `test_supervisor_llm.py` với fake LLM trả JSON hợp lệ → loop chạy hết; Broker trả id không có trong slice → bị lọc khỏi `source_ids`.

## 4. Class & biến kiểm soát (cái neo)

| neo | ở đâu | giữ gì |
|---|---|---|
| `Agent.guard_tool_call` | `roles/agent.py:45` | tool ngoài allowlist → blocker, role tự enforce |
| `RoleSpec.allowed_tools` | `roles/spec.py:53-63` | union skill+core, forbidden thắng — MỘT chỗ suy scope |
| `AgentRegistry.build_agent` | `roles/registry.py:60` | single & multi cùng dựng từ MỘT store |
| `DelegationManager.delegate` | `delegation/manager.py:63` | chokepoint riêng, không phải method kernel |
| `DelegationPolicyEngine.validate` | `delegation/policy.py:26` | `scope <= parent.allowed_capabilities` |
| `DelegationRegistry.resolve` | `delegation/registry.py:33-35` | >1 match → LookupError mơ hồ |
| `judge_acceptance` | `supervisor/graph.py:238-249` | passed = all-exist + ≥1-valid evidence |
| `NON_EVIDENCE_KINDS` | `supervisor/evidence.py:23` | scaffolding không bao giờ tính là evidence |
| identity-check resume | `supervisor/loop.py:128` | Blackboard chỉ resume bởi session sở hữu |

Một role là một file yaml — đọc `roles/library/code.yaml` để thấy mọi neo cùng chỗ: `allowed_tools` (explicit), `allowed_skills` (kéo thêm tool, Phase 5), `route_permissions.may_route_to` (đi đâu khi block), và `test_ownership` (separation-of-duties):

```yaml
name: code
allowed_tools: [fs_read, fs_write, fs_list]
allowed_skills: [file_edit]
route_permissions:
  may_route_to: [test, reviewer]
test_ownership:
  owns_validation: false      # role này KHÔNG tự validate
  must_handoff_to: test       # → buộc phải giao cho 'test'
lenses: [correctness]
```

`owns_validation: false` + `must_handoff_to: test` chính là cái `Agent.__init__` kiểm fail-fast (`agent.py:31`) và `guard_finish` thực thi lúc chạy (`agent.py:56`). Bỏ `must_handoff_to` mà giữ `owns_validation: false` → dựng Agent nổ ngay.

Allowlist enforce ngay tại agent (không đợi kernel):

```python
def guard_tool_call(self, tool_name: str) -> dict | None:
    if self.is_tool_allowed(tool_name):
        return None
    return {
        "finish_reason": "blocker",
        "blocked_tool": tool_name,
        "reason": f"Tool '{tool_name}' is outside role '{self.spec.name}' allowlist.",
        "may_route_to": list(self.spec.may_route_to),
    }
```

Scope con ⊆ cha — cái van delegation:

```python
scope = policy.allowed_capabilities or parent.allowed_capabilities
if not scope <= parent.allowed_capabilities:
    raise PermissionError("Delegation capability scope exceeds the parent scope.")
```

Cổng acceptance honor evidence (≥1-valid, KHÔNG all-valid):

```python
if (
    claimed == "passed"
    and evidence
    and all(e in state.artifacts for e in evidence)          # mọi id resolve
    and any(evidence_type_of(state.artifacts[e]) is not None  # ≥1 là evidence thật
            for e in evidence)
):
    check.status = "passed"
    check.evidence_ids = evidence
```

## 5. Invariant của phase

- **I13 — Delegation là chokepoint RIÊNG, không phải method kernel.** Mọi giao việc đi qua `DelegationManager.delegate` (`manager.py:63`), không có `kernel.delegate()`. Tách khỏi kernel để kernel `freeze()` vẫn nhỏ; gom delegation về một cửa để audit (`delegation.started`/`progress`/`finished`) + scope check không bị bypass. (known-risks Part1 row 5.)
- **I14 — Scope con ⊆ scope cha, luôn luôn.** `policy.validate` (`policy.py:26`) **và** `SessionFactory.create_child` (`core/session.py:163`) đều kiểm `scope <= parent.allowed_capabilities` — phòng thủ hai lớp. Trong loop, scope worker chỉ đến từ `AgentAssignment.allowed_capabilities` của O, không bao giờ từ Broker (`graph.py:175`). Con chỉ được hẹp hơn cha, không bao giờ rộng hơn.
- **I15 — O không "pass" bằng giàn giáo của chính nó.** `judge_acceptance` (`graph.py:238`) đòi cited id resolve + ≥1 là evidence thật; `NON_EVIDENCE_KINDS` (`evidence.py:23`) loại `session_plan/context_packet/ac_report`. Quantifier là **≥1-valid** (không phải all-valid — đó là lỗ red-team FM-HIGH ngược lại: all-valid quá ngặt, sẽ chặn oan khi O kèm một scaffolding id hợp lệ). `record_ac_report` đẻ `ac_report` cũng nằm trong `NON_EVIDENCE_KINDS` → không tự làm evidence cho chính mình (AC5).
- **AgentRegistry là SINGLE store.** Một role có đúng một `RoleSpec`; `build_agent` chia sẻ giữa single (Phase 4) và multi (phase này). Không có hai catalog trôi lệch nhau.
- **Blackboard serializable = nguồn chân lý resume.** `TaskLoopState` chỉ chứa primitive; checkpoint SQLite sau mỗi turn + mỗi round; resume kiểm identity. Worker turn đã xong không chạy lại (`run_round` skip theo `done_this_round`).

## 6. Pitfall / bug sẽ gặp

**Triệu chứng: delegation chạy nhưng không có event/audit, scope không bị check.**
→ Nguyên nhân: bạn thêm `kernel.delegate()` hoặc gọi `handler.run()` thẳng, bỏ qua `DelegationManager`. Trộn delegation vào kernel = mất `delegation.started/finished` + bypass `policy.validate`.
→ Cách tránh: mọi giao việc đi qua `delegation/manager.py:63`. Adapter chỉ implement `DelegationPort.run`, không ai gọi nó ngoài manager.

**Triệu chứng: child session làm được tool mà parent không có quyền; hoặc đệ quy delegation không dừng.**
→ Nguyên nhân: bỏ `DelegationPolicyEngine.validate`, hoặc nới `max_depth`/`max_steps` vô cớ. Con leo quyền vượt cha hoặc loop đệ quy.
→ Cách tránh: mọi delegation qua `validate` (`policy.py:13`); giữ check `scope <= parent.allowed_capabilities` (`policy.py:26`); v1 tắt đệ quy ngay tại adapter (`langgraph_agent.py`: `delegation_service=None`). Không đổi `max_depth=8`/`max_steps=100` mà không có lý do ghi lại.

**Triệu chứng: O báo "finished", loop chấp nhận, nhưng chẳng có sản phẩm thật nào — chỉ session_plan với context_packet.**
→ Nguyên nhân: cổng acceptance không phân loại evidence, hoặc dùng all-exist mà quên ≥1-valid. O trỏ vào scaffolding của chính loop để "pass".
→ Cách tránh: `judge_acceptance` (`graph.py:238`) phải `any(evidence_type_of(...) is not None)`; giữ `NON_EVIDENCE_KINDS` (`evidence.py:23`). Test `tests_audit/test_acceptance_evidence_adversarial.py` ghim bất biến này.

**Triệu chứng: cổng acceptance chặn oan — O kèm một id hợp lệ cạnh evidence thật mà vẫn `pending`.**
→ Nguyên nhân: bạn viết `all(evidence_type_of(...) is not None)` (all-valid) thay vì `any(...)` (≥1-valid). Đây là lỗi ngược của lỗi trên — quá ngặt.
→ Cách tránh: quantifier đúng là **≥1-valid** (`graph.py:246`, DEC-7). all-exist + ≥1-typed, không phải all-typed.

**Triệu chứng: resume nổ, hoặc nhặt nhầm Blackboard của run khác, hoặc chạy lại turn đã xong.**
→ Nguyên nhân: Blackboard chứa object không-serializable (encode/decode mất dữ liệu), hoặc thiếu identity-check khi resume.
→ Cách tránh: `TaskLoopState` chỉ primitive (`state.py`); resume kiểm `session_id`+`task_id` khớp (`loop.py:128`); `SqliteTaskLoopStore` chặn `run_id` path-like (`checkpoint.py:24`); `run_round` skip agent đã có turn trong round.

## 7. Definition of Done

Test thật (offline, `python -m pytest -q`):

- `tests/test_roles.py` (14) — allowlist suy đúng, forbidden thắng, separation-of-duties fail-fast, lens render.
- `tests/test_delegation.py` (6) — chokepoint delegate, scope reject, progress order, idempotent.
- `tests/test_supervisor_loop.py` (8) — compose→decide→round→judge tới terminal, loop-guard.
- `tests/test_supervisor_resume.py` (3) — save/load/resume từ round dang dở, identity match.
- `tests/test_supervisor_llm.py` (5) — O + Broker bản LLM qua `llm.chat`, guardrail trong code.
- `tests/test_acceptance_gate.py` (9) — passed chỉ khi all-exist + ≥1-valid.
- `tests/test_evidence.py` (9) — `evidence_type_of` phân loại đúng, `NON_EVIDENCE_KINDS`.
- `tests_audit/test_supervisor_adversarial_matrix.py` (11) — compose reject unknown/duplicate, round reject agent chưa-compose + Broker đổi target, acceptance reject evidence rỗng/lạ/một-phần, checkpoint reject run_id path-like + identity lệch, concurrent save lossless.
- `tests_audit/test_acceptance_evidence_adversarial.py` (3) — ac_report không tự làm evidence (AC5), resume sau finish không nhân đôi report (AC6), property hypothesis cho cổng.
- `tests_audit/test_session_delegation_state_machine.py` (11) — policy reject mọi chiều out-of-bounds, biên inclusive, empty-scope = deny-all, store duplicate/out-of-order/conflicting result, handler corruption → durable failure, progress budget không mất artifact cũ.

Xanh hết = phase đạt: nhiều agent chạy LLM thật, mỗi worker scope ⊆ cha, O không pass bằng scaffolding, resume từ Blackboard chính xác.

## 8. Vì sao tổ chức thế này giúp kiểm soát

Ba quyết định kiến trúc của phase này không phải tình cờ — chúng là cách giữ kiểm soát khi số agent tăng:

**Chokepoint delegation riêng (I13).** Kernel chỉ lo `execute_tool` (Phase 1). Giao-việc-giữa-agent là một loại sự kiện khác — có vòng đời (started→progress→finished), có policy (depth/scope/budget), có child session. Gom nó về **một** cửa thứ hai (`manager.py:63`) thay vì rắc vào kernel cho hai lợi ích: kernel `freeze()` vẫn nhỏ và bất biến, và mọi delegation đều để lại dấu vết audit + đi qua scope check — không có đường tắt. Trộn vào kernel là cách nhanh nhất để mất cả hai.

**Scope con ⊆ cha (I14), kiểm hai lớp.** Một hệ nhiều agent dễ chết vì leo quyền: agent A scope hẹp giao việc cho B, B "vô tình" rộng hơn A. Bất biến "con chỉ hẹp hơn cha" + kiểm ở **cả** `policy.validate` lẫn `create_child` nghĩa là quyền chỉ co lại theo cây delegation, không bao giờ nở ra. Cộng với "scope chỉ đến từ O, không từ Broker" — Broker shape thông tin, O shape quyền, hai vai tách bạch.

**Acceptance theo evidence (I15), ≥1-valid.** Khi O vừa là người làm vừa là người chấm, cám dỗ lớn nhất là tự chấm đậu. Phân loại evidence từ `artifact.kind` + đòi ≥1 evidence thật khiến O **không thể** đậu bằng giàn giáo của chính nó. Chọn ≥1-valid (không all-valid) là cân bằng có chủ đích: đủ ngặt để chặn scaffolding-only, đủ lỏng để không chặn oan khi O trích dẫn trung thực.

Bài học rời phase: **nhiều agent mà vẫn audit được + không leo quyền** không đến từ tin agent ngoan, mà từ ba cái van cơ học đặt đúng chỗ — một cửa delegation, một quy tắc scope, một cổng evidence. Mỗi cái van là code đọc được, test được, không phải kỷ luật con người.

---
*Điều hướng: ← [Phase 5](phase-5-skills-rag.md) · → [Phase 7](phase-7-control-plane.md)*
