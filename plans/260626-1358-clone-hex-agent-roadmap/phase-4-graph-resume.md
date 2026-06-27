---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 4 — Single-agent graph & resume (SQLite-truth)

> Epic: E05 · Cổng vào: Phase 1–3 · Rời phase với: một single-agent loop chạy task thật (LLM → tool → finish) và resume đúng tiến trình sau khi process chết giữa chừng, đọc từ SQLite chứ không phải file projection.

## 1. Mục tiêu & ranh giới

Phase 1–3 cho bạn ba thứ: **kernel** (`execute_tool` là chokepoint duy nhất), **discipline** (`Budget`, `parse_action`, `check_finish` — JSON gate), **toolbox** (tool an toàn sau workspace jail). Phase này dán chúng lại thành **một vòng lặp agent chạy được**, rồi làm cho vòng lặp đó **resume được qua restart**.

Bạn xây đúng bốn thứ:

1. **`AgentState`** — state điều phối *chỉ-serializable* cho một run, kèm codec encode/decode.
2. **Topology** `build_agent_graph` — đồ thị LangGraph 6 node, route bằng một field `route`.
3. **Node lifecycle** — mỗi node làm đúng một việc, kết thúc đúng một lần qua `complete_task`/`fail_task`.
4. **Facade `run`/`resume`** — public API, với **SQLite là nguồn sự thật** và `checkpoint.json` chỉ là projection cho UI.

Ranh giới cứng (đừng vượt):
- **Một** runtime agent. LangGraph chỉ điều phối; `core/` không import LangGraph.
- Service runtime (kernel, LLM client, SQLite connection) **không bao giờ** vào checkpoint — chúng được bind lúc compile node qua `partial(...)`.
- **Single-agent**. Node `delegate` có mặt trong topology nhưng delegation đầy đủ (depth/scope/policy) là phần của Phase tiếp theo; ở đây nó chỉ là một cạnh route hợp lệ.

Hai entrypoint cùng chạy *một* graph: `orchestrator.run`/`resume` (`orchestrator/loop.py`) là facade public ổn định — **dùng cái này**; `run_agent(...)` (`graph/runtime.py:85`) là facade tương thích ngược cho test cũ (`llm_call=`), build trên đúng `build_agent_graph`. `run_id` ↔ LangGraph `thread_id`; `task_id` là correlation ID cho lifecycle + tool event.

Bằng chứng "đã rời phase" (cụ thể, đo được): (1) một task chạy LLM → tool → `final` và đóng lifecycle đúng một lần; (2) kill process giữa chừng rồi `resume(kernel, run_id)` chạy tiếp từ đúng node dở dang, **không** lặp lại node đã chạy; (3) resume một run đã xong trả lại outcome cũ **không** gọi LLM lần nữa. Cả ba có test bảo chứng (xem §7).

Tham chiếu nền: `docs/reference/runtime-flow.md` §3 (topology), §4 (node lifecycle), §6 (state), §7 (resume) — doc này là xương sống của phase. `docs/reference/known-risks.md` Phần 1 hàng 2,3,4 + footgun `checkpoint.json`. Lịch sử: `CHANGELOG.md` Sprint 3 (LangGraph runtime consolidation — chuyển checkpoint thật sang `langgraph.sqlite` per-run, `checkpoint.json` thành projection nguyên tử) và Sprint 4 (checkpoint `session_state` schema v2, migrate key `kernel_state`).

## 2. Bạn sẽ xây gì (bản đồ module)

| File | Vai trò | Symbol neo |
|---|---|---|
| `graph/state.py` | State serializable + codec + factory | `AgentState`, `encode/decode_session_state`, `new_agent_state` |
| `graph/runtime.py` | Build & compile topology; facade tương thích cũ | `build_agent_graph`, `_route`, `run_agent` |
| `graph/nodes.py` | 6 node: guard/agent/tool/delegate/finish/fail | `guard_node` … `fail_node`, `_restore_session`, `_session_snapshot` |
| `orchestrator/loop.py` | Facade public run/resume; nhánh migrate legacy | `run`, `resume`, `_legacy_state`, `_restore_persisted_session` |
| `orchestrator/checkpoint.py` | SQLite checkpointer + JSON projection cho UI | `open_checkpointer`, `checkpoint_db_path`, `save_graph_projection`, `Checkpoint` |

Tạo tác mỗi run nằm dưới `var/agent_runs/<run_id>/`: `events.jsonl`, `summary.json`, **`langgraph.sqlite`** (truth), `checkpoint.json` (projection). `var/` gitignored.

## 3. Dựng step-by-step

### Bước 1 — `AgentState`: hợp đồng serializable + codec

`AgentState` là `TypedDict, total=False` (`graph/state.py:12`). Quy tắc một dòng: **mọi field phải là primitive JSON** (str/int/list/dict/None). Service runtime *cố tình* không có chỗ ở đây — docstring tại `graph/state.py:13-18` nói rõ.

`session.state` (snapshot của kernel session) thường có giá trị không-primitive — cụ thể `current_task` là một `TaskEnvelope` (dataclass). Codec xử lý đúng một special-case đó: `encode_session_state` (`graph/state.py:42`) bọc thành `{"__task__": task.as_dict()}`; `decode_session_state` (`graph/state.py:51`) dựng lại. Snapshot vào state luôn đi qua encode.

`new_agent_state` (`graph/state.py:70`) là factory: set `schema_version=2`, `run_id`/`task_id` từ `session.identity`, encode `session.state.snapshot()`, `route="guard"`, `status="running"`. Field `kernel_state` (`graph/state.py:30`) là **migrate-only key** từ schema v1 — code mới đọc `session_state`, đọc `kernel_state` chỉ để tương thích.

**Tự kiểm**: `python -c "from graph.state import AgentState; print(AgentState.__total__)"` → `False`. `python -m pytest tests/test_state.py -q`.

### Bước 2 — Topology `build_agent_graph`

Sơ đồ thật (từ `graph/runtime.py:49-65`, khớp `runtime-flow.md` §3):

```text
START -> guard
guard    -> agent | fail
agent    -> tool | delegate | finish | guard | fail
tool     -> guard | fail
delegate -> guard | fail
finish   -> guard (bị-chặn) | END
fail     -> END
```

Hai điểm dễ bỏ sót: node `delegate` là thật, và cạnh `finish -> guard` là thật (finish gate chặn được → quay lại guard, *không* terminate). Mỗi `add_conditional_edges` route bằng một hàm duy nhất `_route` (`graph/runtime.py:27`) đọc field `state["route"]`. Service được bind lúc add_node: `partial(guard_node, session=session)` (`graph/runtime.py:39`) — vì thế kernel/session **không** vào state.

`build_agent_graph` nhận `checkpointer=` (None = không persist) và `delegation_service=` (None = node delegate trả `fail` "delegation is not configured").

Tại sao mọi node đi qua đồ thị này lại an toàn về quan sát/quyền: mọi hành động ra ngoài (LLM **và** tool) gọi `session.execute_tool` → chokepoint `AgentKernel.execute_tool` của Phase 1. Một step điển hình của vòng lặp đếm qua cạnh `guard → agent → tool → guard`:

```text
guard:  steps=0 < max_steps -> route=agent
agent:  llm.chat -> parse_action OK -> record_step (steps=1) -> route=tool
tool:   record_tool_call -> execute_tool -> nối envelope -> route=guard
guard:  steps=1 < max_steps -> route=agent ...  (lặp tới khi final hoặc cạn budget)
```

`record_step` chỉ ở `agent_node` (`graph/nodes.py:84`) → budget đếm **action hợp lệ**, parse lỗi không tốn step. Vòng quay luôn về `guard` trước LLM call kế → step budget không bao giờ bị vượt mà không bị chặn.

**Tự kiểm**: `python -m pytest tests/test_graph.py -q`.

### Bước 3 — Từng node (lifecycle)

Quy ước chung mọi node tuân theo (nhìn ra ngay khi đọc `graph/nodes.py`):
- **Mở** bằng `_restore_session(state, session)` (`graph/nodes.py:20`) — nạp `session.state` từ `state["session_state"]` (fallback `kernel_state`) sau khi `decode_session_state`. Đây là lý do session *không* cần nằm trong checkpoint: nó được tái dựng từ snapshot primitive ở đầu mỗi node.
- **Đóng** bằng `dict` partial-update LangGraph merge vào state, **luôn kèm** `route` (cho `_route` đọc) và `session_state` mới (`_session_snapshot`, `:25`) để transition kế thấy state cập nhật.
- Mọi hành động ra ngoài đi qua `session.execute_tool` (kể cả LLM) — không có đường tắt. Telemetry qua `_emit` (`:29`).

1. **`guard`** (`graph/nodes.py:40`) — *step budget gate*, chặn **trước** mỗi lần gọi LLM. `budget.steps >= budget.max_steps` → `{"route":"fail","error":"step budget exceeded"}` + emit `graph.budget_blocked`. Ngược lại → `route="agent"`. Đây là van chống cháy túi: mọi vòng lặp quay về `guard` trước khi tốn thêm một LLM call.
2. **`agent`** (`graph/nodes.py:51`) — *bộ não một step*. Gọi `session.execute_tool("llm.chat", {messages, model, json_mode:True})`, nối assistant message, rồi `parse_action(content)` (JSON gate của discipline) ép **đúng một** action.
   - Parse lỗi (`JsonGateError`): `budget.record_parse_error()`; nếu `parse_exceeded()` → `route="fail"` ("too many parse errors"); chưa quá → nối `build_retry_message(exc)` rồi `route="guard"` (thử lại, không tốn step).
   - Hợp lệ: `budget.record_step()`, set `last_action`, route theo verb — `tool`→`tool`, `delegate`→`delegate`, `final`→`finish`, verb lạ → nối nhắc nhở + `route="guard"`. Chỉ ở đây `steps` mới tăng → budget đếm **action hợp lệ**, không đếm lần parse hỏng.
3. **`tool`** (`graph/nodes.py:106`) — *thực thi tool*. Đọc `last_action.tool`/`args`, chuẩn hóa args không-dict thành `{}` (`:112`), `budget.record_tool_call(key)`; `same_tool_exceeded(key)` → `route="fail"` (chặn lặp cùng tool). Ngược lại `session.execute_tool(name, args)`, nối envelope JSON (`default=str`) vào messages → `route="guard"`.
4. **`delegate`** (`graph/nodes.py:141`) — *chokepoint delegation riêng*. `delegation_service is None` → `fail` ("delegation is not configured"). Validate `target`/`spec`/`policy`; `spec.objective` rỗng → `fail`. Gọi `delegation_service.delegate(session, target, spec, policy)` trong try/except (lỗi boundary → `fail`, không sập graph); ok → nối `DELEGATION_RESULT: ...` → `route="guard"`. Ở phase này delegation_service thường là None — node tồn tại nhưng chưa cấu hình.
5. **`finish`** (`graph/nodes.py:202`) — *cổng kết thúc + đóng lifecycle*. Nếu `finish_reason=="error"` → đây là thất bại terminal (LLM adapter cạn retry): `session.fail_task(reason)`, `status="failed"`, `route="end"` — *không* giả vờ completed. Ngược lại `check_finish(session.state.as_dict(), finish_reason)` (`:220`): gate `allowed=False` (vd đổi code mà chưa validate) → nối lý do + `route="guard"` (quay lại làm tiếp, emit `graph.finish_blocked`); gate cho qua → `session.complete_task(final)`, `status="completed"`, `route="end"`.
6. **`fail`** (`graph/nodes.py:243`) — *đóng run thất bại qua cùng lifecycle*. `session.fail_task(reason, steps, parse_errors)`, `status="failed"`, `route="end"`. Quan trọng: thành công và thất bại đóng qua **cùng một** API lifecycle (`complete_task`/`fail_task`) — không có đường đóng thứ hai.

Lưu ý I12: `complete_task` chỉ ở `finish_node:232`; `fail_task` ở `finish_node:211`, `fail_node:248`. Mỗi đường terminal gọi **đúng một** trong hai, rồi `route="end"` → END. Không nhánh nào đóng hai lần.

**Tự kiểm**: `python -m pytest tests/test_lifecycle.py -q` (đóng lifecycle đúng một lần).

### Bước 4 — Facade `run`/`resume`

`run` (`orchestrator/loop.py:89`): tạo/nhận session → validate → `new_agent_state` → stream → sync budget → outcome. Ba guard validate *cố ý chặt* (vì session là cửa quyền hạn, nhầm là rò state giữa run):
- `active_session.kernel is not kernel` → `ValueError` (`:107`) — session phải thuộc đúng kernel.
- `current_task` không phải `TaskEnvelope` hoặc `user_request` lệch → `ValueError` (`:109-111`) — session phải *sở hữu* task đang chạy.
- `run_id` truyền vào mà lệch `session.identity.run_id` → `ValueError` (`:112`).

Sau đó `_config(rid, budget)` đặt `thread_id == rid == run_id` và `recursion_limit` đủ rộng theo budget (`:40-44`). `checkpoint=False` → graph không checkpointer (path nhanh, không resume được). `checkpoint=True` → `open_checkpointer(rid)` bọc cả vòng stream.

`_sync_budget` (`orchestrator/loop.py:58`) copy `steps`/`parse_errors`/`_tool_calls` từ state cuối **về lại** `Budget` object của caller — để caller thấy đúng số step đã tiêu (state là truth, object chỉ là view). `_stream` (`:65`) gọi `save_graph_projection` mỗi values; nếu graph throw, cố ghi snapshot cuối từ `graph.get_state` rồi re-raise (`:77-82`) — projection không bao giờ mất transition cuối ngay cả khi lỗi.

`resume` (`orchestrator/loop.py:213`): rẽ nhánh ngay ở đầu bằng `checkpoint_db_path(run_id).exists()`.

**Đường chính — có `langgraph.sqlite`** (`orchestrator/loop.py:242-269`):
1. `open_checkpointer(run_id)` mở đúng DB của run đó.
2. `saver.get_tuple({"configurable":{"thread_id":run_id}})` đọc **raw** checkpoint; `None` → `FileNotFoundError`.
3. `persisted = raw.checkpoint["channel_values"]` — chính là `AgentState` đã lưu. `_restore_persisted_session(kernel, run_id, persisted)` (`:184`) dựng lại `KernelSession`: decode `session_state`, lấy `SessionIdentity` từ `session_identity` (hoặc tổng hợp nếu thiếu), `allowed_capabilities` (fallback toàn bộ tool registry).
4. Compile lại graph cùng `thread_id`, `graph.get_state` lấy snapshot "live".
5. Cổng chạy-tiếp: `persisted["status"] != "running"` **hoặc** `not snapshot.next` → run đã xong → `return _outcome(persisted)` (không chạy gì thêm). Ngược lại `_stream(graph, None, ...)` — truyền `graph_input=None` để LangGraph **nối từ checkpoint** thay vì khởi tạo lại.

**Đường legacy — không có SQLite** (`orchestrator/loop.py:146-181`): `_legacy_state` đọc một lần `checkpoint.json` *cũ* (`backend=="legacy-json"`, run tạo trước thời LangGraph). Nếu run cũ đã terminal → trả `last_result` luôn. Nếu còn `running` → dựng `TaskEnvelope`/`Budget`/`SessionIdentity`, `factory.restore(...)`, `new_agent_state(...)` rồi chạy tiếp **trên graph mới**. Đây là *ngoại lệ duy nhất* nơi `checkpoint.json` được đọc — và chỉ để migrate, không phải resume thường ngày (I11 vẫn đúng).

Worked trace (crash giữa chừng): run tốn 2 step, ghi SQLite sau mỗi transition, process chết tại `tool` thứ 3 → khởi động lại → `resume(kernel, run_id)` → có SQLite → đọc state ở step 2, `status=="running"`, `snapshot.next=("tool",)` → stream tiếp từ đúng node `tool`, **không** chạy lại 2 step đầu. Đây chính là điều `test_crash_after_effect_does_not_replay_effect_on_resume` bảo chứng.

### Bước 5 — SQLite checkpoint + projection

`open_checkpointer(run_id)` (`orchestrator/checkpoint.py:35`) — một `SqliteSaver` per-run tại `var/agent_runs/<run_id>/langgraph.sqlite` (`checkpoint_db_path`, `:30`). Một DB/run → tránh lock chéo, dễ archive.

`save_graph_projection(state)` (`orchestrator/checkpoint.py:134`) ghi **`checkpoint.json`** sau mỗi transition — đây là **projection cho UI** với schema ổn định (`Checkpoint.from_graph_state`, `:103`): `run_id`, `task`, `messages`, `budget`, `state` (đã decode), `step`, `status`, `backend="langgraph"`.

Tính atomic của write quan trọng vì UI có thể đọc đồng thời, và nhiều run có thể ghi song song:
- Ghi vào temp **tên duy nhất per-write** (`{name}.{uuid}.tmp`, `:128`) — hai writer cùng run không chia sẻ temp file.
- `os.replace(tmp, path)` dưới `_REPLACE_LOCK` (`:130`) — trên Windows `os.replace` đồng thời cùng đích race ra `PermissionError`; lock serialize bước rename.
- Kết quả: reader luôn thấy **một** file JSON hợp lệ (hoặc bản cũ, hoặc bản mới — không bao giờ nửa vời).

`load_checkpoint` (`:138`) có docstring nói thẳng: "Resume intentionally does not call this function". `checkpoint_path` (`:25`) cũng ghi rõ "It is not used to resume a graph". Hai dấu này khóa I11 ngay tại nguồn: ai đó định resume từ projection sẽ vấp ngay comment.

**Tự kiểm**: chạy một run rồi `ls var/agent_runs/<run_id>/` thấy đủ 4 file (`events.jsonl`, `summary.json`, `langgraph.sqlite`, `checkpoint.json`); `python -m pytest tests/test_resume.py tests/test_orchestrator.py -q`. Kiểm projection atomic dưới ghi đồng thời: `test_json_projection_same_run_concurrent_writes_remain_atomic_and_valid` (`tests_audit/test_graph_resume_matrix.py:192`).

## 4. Class & biến kiểm soát (cái neo)

| Neo | File:line | Vì sao là neo |
|---|---|---|
| `AgentState` (TypedDict, serializable-only) | `graph/state.py:12` | Hợp đồng: vi phạm → resume vỡ âm thầm |
| `encode/decode_session_state` | `graph/state.py:42`,`:51` | Cầu nối dataclass↔primitive (special-case `TaskEnvelope`) |
| `schema_version=2` + key `kernel_state` | `graph/state.py:30`,`:82` | Migrate v1→v2 |
| `_route` | `graph/runtime.py:27` | Một hàm route cho mọi conditional edge |
| `build_agent_graph` topology | `graph/runtime.py:49-65` | Đồ thị + cạnh; service bind qua `partial` |
| `resume` đọc SQLite | `orchestrator/loop.py:242-269` | Truth = `saver.get_tuple` / `graph.get_state` |
| `run_id == thread_id` | `orchestrator/loop.py:40-44` | Cùng ID nối checkpoint qua restart |
| `checkpoint_db_path` vs `checkpoint_path` | `orchestrator/checkpoint.py:30`,`:25` | SQLite (truth) vs JSON (projection) |

Codec — special-case duy nhất, mọi thứ khác phải là primitive (`graph/state.py:42-57`):

```python
def encode_session_state(state: dict[str, Any]) -> dict[str, Any]:
    encoded = dict(state)
    task = encoded.get("current_task")
    if isinstance(task, TaskEnvelope):
        encoded["current_task"] = {"__task__": task.as_dict()}
    return encoded
# decode đảo lại: dict có "__task__" -> TaskEnvelope.from_dict(...)
```

`_route` — toàn bộ logic điều hướng đồ thị nằm trong một dòng (`graph/runtime.py:27-28`):

```python
def _route(state: AgentState) -> str:
    return str(state.get("route") or "fail")  # default "fail" = an toàn, không bao giờ kẹt
```

Resume đọc SQLite, **không** đọc projection (`orchestrator/loop.py:242-261`, rút gọn):

```python
with open_checkpointer(run_id) as saver:           # var/agent_runs/<run_id>/langgraph.sqlite
    raw = saver.get_tuple({"configurable": {"thread_id": run_id}})  # run_id == thread_id
    persisted = dict(raw.checkpoint.get("channel_values") or {})
    session = _restore_persisted_session(kernel, run_id, persisted)
    graph = build_agent_graph(session=session, checkpointer=saver, ...)
    snapshot = graph.get_state({"configurable": {"thread_id": run_id}})
    if persisted.get("status") != "running" or not snapshot.next:
        return _outcome(persisted)                 # đã xong -> trả lại, KHÔNG chạy lại
    return _outcome(_stream(graph, None, ...))      # graph_input=None -> nối từ checkpoint
```

`run_id == thread_id` — sợi dây nối run với checkpoint, đặt ở một chỗ duy nhất (`orchestrator/loop.py:40-44`). Đổi nó là vỡ resume:

```python
def _config(run_id: str, budget: Budget) -> dict[str, Any]:
    return {
        "configurable": {"thread_id": run_id},   # thread_id LUÔN == run_id
        "recursion_limit": max(100, budget.max_steps * 4 + budget.max_parse_errors * 3 + 20),
    }
```

`new_agent_state` chốt schema khi tạo state mới (`graph/state.py:70-101`): set `schema_version=2`, encode `session.state.snapshot()` vào `session_state`. Đổi shape state về sau ⇒ phải bump `schema_version` và thêm nhánh đọc key cũ (như `kernel_state` cho v1) — nếu không, run cũ resume sẽ decode sai.

## 5. Invariant của phase

- **I10 — Hợp đồng serializable của state.** Mọi thứ bỏ vào `session.state` (→ vào `AgentState["session_state"]`) phải là primitive **hoặc** được xử lý trong `encode/decode_session_state`. Neo: `graph/state.py:12`, `:42-57`. Đổi shape state → tăng `schema_version` + thêm nhánh migrate. (`known-risks.md` Phần 1 #2.)
- **I11 — SQLite là sự thật, `checkpoint.json` chỉ là projection.** `resume()` chỉ đọc `langgraph.sqlite`; không bao giờ resume từ `checkpoint.json`; `run_id == thread_id`. Neo: `orchestrator/loop.py:242-269`, `orchestrator/checkpoint.py:25` vs `:30`, `:139`. (`known-risks.md` Phần 1 #3 + footgun.)
- **I12 — Đóng lifecycle đúng một lần, không loop.** Mọi nhánh kết thúc về `finish`/`fail`, lifecycle đóng đúng một lần qua `complete_task`/`fail_task`; route hợp lệ ⇒ không loop vô tận, không đóng hai lần. Neo: `graph/runtime.py:49-65`, `graph/nodes.py:232`,`:248`. (`known-risks.md` Phần 1 #4.)

## 6. Pitfall / bug sẽ gặp

**Nhét object thường vào `session.state` → vỡ resume âm thầm.**
- *Triệu chứng*: run xanh, nhưng resume sau restart raise serialize/restore lỗi — hoặc tệ hơn, state khôi phục sai mà không báo.
- *Nguyên nhân*: SQLite checkpointer chỉ serialize primitive; dataclass/đối tượng tự do không qua codec → hỏng. `graph/state.py:42-57`.
- *Cách tránh*: chỉ bỏ primitive vào `session.state`, hoặc mở rộng `encode/decode_session_state` cho type mới + thêm test resume. Đổi shape → bump `schema_version`.

**Resume từ `checkpoint.json` → mất tiến trình / chạy lại node side-effect.**
- *Triệu chứng*: resume "ăn gian" — bỏ qua state mới nhất, hoặc chạy lại một tool đã ghi đĩa lần hai.
- *Nguyên nhân*: nhầm projection là truth. `checkpoint.json` ghi *sau* transition cho UI, không phải state để nối graph. `orchestrator/checkpoint.py:139` (docstring), `:25`.
- *Cách tránh*: resume luôn qua `open_checkpointer` + `saver.get_tuple` (`orchestrator/loop.py:242-249`). Debug bằng SQLite + `events.jsonl`, không sửa tay `checkpoint.json`. Test bảo chứng: `test_crash_after_effect_does_not_replay_effect_on_resume` (`tests_audit/test_graph_resume_matrix.py:153`).

**Đổi `run_id ↔ thread_id`.**
- *Triệu chứng*: resume báo `FileNotFoundError: No checkpoint for run_id=...` dù run đã chạy.
- *Nguyên nhân*: checkpoint khóa theo `thread_id`; nếu config dùng ID khác `run_id`, LangGraph không tìm thấy thread. `orchestrator/loop.py:40-44`.
- *Cách tránh*: giữ `thread_id` == `run_id` ở mọi config (`_config`, bootstrap_config). Đừng sinh ID mới ở resume.

**Route sai → loop vô tận / đóng lifecycle hai lần.**
- *Triệu chứng*: run không terminate (đụng `recursion_limit`), hoặc `complete_task`/`fail_task` chạy hai lần.
- *Nguyên nhân*: node trả `route` không khai báo trong `add_conditional_edges`, hoặc nhánh không về `finish`/`fail`. `graph/runtime.py:49-65`.
- *Cách tránh*: thêm node ⇒ khai báo đủ cạnh + set `route` hợp lệ; mọi nhánh terminal về `finish`/`fail` đúng một lần (I12). `_route` mặc định `"fail"` để không kẹt im lặng (`graph/runtime.py:28`).

**Đổi shape state mà quên bump `schema_version` → run cũ resume decode sai.**
- *Triệu chứng*: run *mới* xanh, nhưng resume một run *cũ* (tạo trước khi đổi) khôi phục state lệch field — không crash, chỉ sai.
- *Nguyên nhân*: state cũ trong SQLite có shape v1, code mới đọc theo shape mới mà không có nhánh migrate. Dấu vết: key `kernel_state` (`graph/state.py:30`) là di sản của lần migrate v1→v2.
- *Cách tránh*: đổi shape ⇒ tăng `schema_version` (`graph/state.py:82`) + thêm nhánh đọc key cũ trong `_restore_session`/codec. `_restore_session` đã có fallback `session_state or kernel_state` (`graph/nodes.py:21`) làm mẫu.

## 7. Definition of Done

Tất cả xanh, offline (không network, không LLM thật — dùng scripted client):

```bash
python -m pytest tests/test_state.py tests/test_resume.py tests/test_lifecycle.py tests/test_orchestrator.py -q
python -m pytest tests_audit/test_graph_resume_matrix.py tests_audit/test_orchestrator_loop_rigor.py -q
```

Phải pass cụ thể (đây là bằng chứng cho từng invariant — map test ↔ invariant):

| Test (file:line) | Bảo chứng điều gì | Invariant |
|---|---|---|
| `tests/test_state.py` | codec round-trip + serializable contract | I10 |
| `tests/test_resume.py`, `tests/test_lifecycle.py` | resume qua restart; đóng lifecycle một lần | I11, I12 |
| `tests/test_orchestrator.py` | facade run/resume hành xử đúng | I11, I12 |
| `test_resume_completed_run_does_not_call_llm_again` (`test_graph_resume_matrix.py:139`) | resume run đã xong **không** gọi LLM lại | I11 |
| `test_crash_after_effect_does_not_replay_effect_on_resume` (`:153`) | resume **không** replay side-effect đã chạy | I11 |
| `test_resume_interrupted_run_continues_from_sqlite_to_completion` (`test_orchestrator_loop_rigor.py:278`) | nối tiếp từ SQLite tới hoàn tất | I11 |
| `test_run_checkpoint_on_writes_sqlite_and_langgraph_projection` (`:89`) | bật checkpoint ghi cả SQLite + projection | I11 |
| `test_resume_reproduces_task_identity_across_process_boundary` (`:307`) | identity giữ nguyên qua restart | I11 |

Smoke (no LLM/network): `python run_smoke.py` → in `CORE_AGENT_SMOKE_OK`. Toàn bộ chạy offline với scripted LLM client.

## 8. Vì sao tổ chức thế này giúp kiểm soát

Ba ràng buộc khóa nhau thành "resume an toàn":

- **Serializable-contract** (`AgentState` chỉ-primitive + codec một-special-case). State *là* checkpoint. Khi state chỉ chứa primitive, "lưu" và "khôi phục" là phép sao chép không mất mát — không có đối tượng sống nào lén vào file rồi restore sai. Service runtime bind qua `partial` lúc compile, nên chúng không thể rò vào checkpoint kể cả khi vô ý.
- **SQLite-truth** (một nguồn sự thật, projection chỉ-đọc). Có **đúng một** chỗ để resume, và một chỗ khác *chỉ* để nhìn. Tách bạch này diệt cả một lớp bug "debug nhầm file" / "sửa tay vô tác dụng" — projection sai cũng không làm hỏng tiến trình thật.
- **Đóng-một-lần** (topology + `_route` + lifecycle gate). Mọi nhánh hội tụ về `finish`/`fail`, đóng lifecycle đúng một lần. Cộng với `run_id == thread_id`, resume biết chính xác đang ở node nào và còn việc gì — chạy lại đúng phần chưa xong, không lặp side-effect.

Bài học: **resume an toàn không phải tính năng, mà là hệ quả của tổ chức.** Bạn không viết code "resume cẩn thận"; bạn dựng state serializable, một nguồn sự thật, một điểm đóng — và resume trở thành đúng *miễn phí*. Tổ chức giữ quyền kiểm soát thay cho kỷ luật thủ công.

---
*Điều hướng: ← [Phase 3](phase-3-toolbox-safety.md) · → [Phase 5](phase-5-skills-rag.md)*
