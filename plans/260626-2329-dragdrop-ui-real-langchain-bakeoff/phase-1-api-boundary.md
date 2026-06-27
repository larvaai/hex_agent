---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 1 — API boundary substrate-agnostic (topology CRUD + run-from-topology + multi-run)

> Anchors re-verified against `server.py` @ 482 LOC (Slice-6b verifier wired in: `server.py:35,70-144,237-249`). Builder pattern này ĐÃ được chứng minh bởi `tests/e2e/test_topology_to_server.py:39-51` (topology→`build_runtime`→Run 3-tuple), nhưng CHƯA expose qua HTTP — server vẫn chỉ một default run (`server.py:326-328`). Phase này mở cửa đó.

**Mục tiêu:** Server đọc-ghi topology, dựng run TỪ topology đã post, giữ nhiều run + một LLM **factory** (không shared instance). Core dragzero KHÔNG đụng.

**Files:**
- Modify: `drag_from_zero/dragzero/server.py` (`App` + `Run`), `drag_from_zero/run_server.py`
- Create: `drag_from_zero/tests/test_authoring_api.py`
- **KHÔNG tách `server_app.py`** round này (DEC: giữ một file, chấp nhận ~580 LOC — file-ownership ổn định xuyên phase 1/3; SRP-split = nợ ghi, không YAGNI giờ). Cập nhật module-map plan.
- KHÔNG đụng: `orchestrator.py`, `read_model.py`, `events.py`, `topology.py`, `wiring.py`, `roster.py`, `contracts.py`, `agent.py`, `llm.py`, `tools.py`, `verifier.py`

## Requirements

**Functional:**
- `GET /api/topology` → list `{id}` đã lưu; `GET /api/topology/{id}` → topology JSON đầy đủ. Seed 1 example (`examples/topology.json`).
- `POST /api/topology` body=topology JSON → `Topology.from_dict` + `validate()` (topology.py:80); lỗi → **422** `{errors:[...]}`; OK → store in-memory → `{id}`.
- `POST /api/runs` body=`{topology_id|topology, task}` → `App.create_run` → run mới, register `App.runs[id]` → `{id}`. `TopologyError`/`ValueError` → **422** `{errors}`.
- Multi-run: `App` registry + counter; `GET /api/runs/{id}`, `/start`, `/reset`, `/artifacts`, `/artifact`, WS `/events` (server.py:395-408,414-421) chạy nguyên với run mới.
- **Back-compat (must-keep):** 5 call site `make_server(run, static_dir=…)` (run_server.py:116, test_slice6a_server.py:50, e2e/test_entrypoints_smoke.py:74, e2e/test_topology_to_server.py:58, e2e_browser/conftest.py:23) PHẢI tiếp tục chạy không sửa. `make_server`+`App` nhận `llm_provider`/`tool_catalog` là **kwargs optional** default `lambda: FakeLLM(...)` + `default_tool_catalog()`. `/api/session` default vẫn 200.

**Non-functional:**
- **LLM = factory, KHÔNG shared instance** (sửa mâu thuẫn plan cũ + race red-team): `llm_provider` là callable 0-arg, gọi MỘT lần mỗi `create_run` (và mỗi join ở P3) → mint LLM tươi per-run. `OpenAICompatLLM.complete`/`RecordedLLM._i`/`FakeLLM.calls` đều mutate state không khoá → hai run-thread share một instance sẽ phá determinism. Forbid shared.
- Core untouched ⇒ chỉ thêm reader/factory.
- `create_run` builder **re-runnable** (fresh sandbox+orch mỗi `reset()`), mirror `_builder` (e2e/test_topology_to_server.py:39-51): `FsSandbox(mkdtemp)` → `build_runtime(topology, llm_provider(), tool_catalog=tool_catalog, sandbox=sb)` → `(rt.orchestrator, rt.entry, sb)`. Dùng `default_tool_catalog()` (catalog dict cho `build_runtime`), KHÔNG `build_fs_tools()` (registry cho Orchestrator demo).
- `Run.__init__` nhận `llm_provider` optional (lưu `self._llm_provider`) — P3 join cần mint agent. create_run luôn truyền; run_server demo cũng truyền (để inject-from-UI demo chạy).

## Tests Before (đỏ) — `tests/test_authoring_api.py`

Mirror stdlib HTTP harness (test_slice6a_server.py:47-83 / e2e/test_topology_to_server.py:54-83):
- **Back-compat:** `make_server(run, static_dir=...)` kiểu CŨ (không kwargs) → `/api/session` 200 + graph render-able (giữ field UI đọc: done_when/children/depends_on/goal/mu/verdict — server.py:115-124).
- `POST /api/topology` hợp lệ → 200 + id; `GET /api/topology/{id}` round-trip == posted (kể cả `ui` top-level key — DEC-A3, topology.py:31,34).
- `POST /api/topology` thiếu agent node → **422** + "no agent nodes" (topology.py:102); edge trỏ node lạ → 422 + "edge from unknown node" (topology.py:95). ≥2 loại lỗi pinned.
- `POST /api/runs {topology_id, task}` → 200 + id MỚI ≠ default → `/start` → `_await_done` → status done; graph ≥2 node (planner→coder).
- `POST /api/runs {topology}` inline với tool lạ → **422** (build_runtime raise TopologyError, wiring.py:58).
- **Artifacts wiring (nice-to-have→bắt buộc):** topology mà agent ghi file → `/start`→done → `GET /api/runs/{id}/artifacts` chứa file + `/artifact?path=` đọc được (bắt lỗi 3-tuple arity sandbox; mirror test_topology_to_server.py:160-168).
- Multi-run: 2 POST /api/runs → 2 id khác, graph độc lập.
- **Provider = factory:** 2 run → LLM object khác nhau (`id()` khác) — pin forbid-shared.

## Implement

1. **`App.__init__` (server.py:325):** thêm params `llm_provider=None`, `tool_catalog=None`; default `llm_provider = lambda: FakeLLM(_default_responder)` (responder mặc định trong run_server hoặc server), `tool_catalog = default_tool_catalog()`. Thêm `self.topologies: dict`, `self._run_seq:int`. Seed example topology.
2. **`App.create_run(topology_dict, task, done_when=None) -> str`:** `topology=Topology.from_dict(topology_dict)`; builder closure capture `(topology, self.llm_provider, self.tool_catalog)` theo pattern test_topology_to_server.py:39-51; `rid=f"run-{seq}"`; `Run(rid, title, task, build, llm_provider=self.llm_provider, done_when=done_when or {})`; register; return rid. `TopologyError` propagate → 422.
3. **`Run.__init__` (server.py:198):** thêm `llm_provider=None` → `self._llm_provider`. (Không đổi hành vi cũ; chỉ lưu.)
4. **`_api_get` (server.py:392):** route `GET /api/topology`, `GET /api/topology/{id}`.
5. **`do_POST` (server.py:411):** route `POST /api/topology` (validate→store|422), `POST /api/runs` (create_run|422). Map `TopologyError`+`ValueError` → `_json({"errors":[...]}, 422)`; còn lại → 500 (giữ except server.py:425).
6. **`make_server` (server.py:478):** thêm kwargs `llm_provider=None, tool_catalog=None` → forward vào `App`. 5 call site cũ không truyền → default.
7. **`run_server.py`:** main wire `llm_provider = (lambda: OpenAICompatLLM(...)) if --real else (lambda: FakeLLM(_demo_responder))`; truyền vào `make_server` + `Run(..., llm_provider=llm_provider)`. `--ui-dir` resolve `app/dist` nếu tồn tại else `ui/` (chuẩn bị P2; app/ chưa cần tồn tại).

## Tests After / Regression Gate

- `python -m pytest drag_from_zero/tests/test_authoring_api.py -q` xanh.
- `python -m pytest drag_from_zero/tests -q` **toàn bộ xanh** — đặc biệt test_slice6a_server.py + e2e/test_topology_to_server.py + e2e/test_entrypoints_smoke.py + integration/test_server_translation.py + test_slice6b_verifier.py (5 call site back-compat).
- `git diff --stat` chỉ chạm `server.py`, `run_server.py`, test mới.

## Success Criteria

- [ ] `POST /api/topology` valid→200/id, invalid→422 (≥2 lỗi loại khác pinned).
- [ ] `POST /api/runs` từ topology → run mới chạy thật tới done, graph ≥2 node, artifacts đọc được.
- [ ] ≥2 run đồng thời, id + graph + LLM-object độc lập (factory).
- [ ] 5 `make_server` call site cũ + toàn bộ suite xanh; `git diff` không chạm core.

## Risk

| Risk | L×I | Mitigation |
|---|---|---|
| `make_server`/`App` đổi signature phá 5 call site | high×regress | kwargs optional + default; red test dựng kiểu CŨ; liệt kê 5 site, không sửa site nào |
| Shared LLM instance race giữa run-thread | high×nondeterminism | factory callable, mint per-run; pin `id()` khác; forbid shared |
| `build_runtime` trả Runtime (.orchestrator/.entry), KHÔNG tuple — `orch,entry=build_runtime(...)` → TypeError | med×bug | dùng `rt=build_runtime(...); rt.orchestrator, rt.entry` (wiring.py:89); sandbox tự tạo + truyền `sandbox=` (wiring.py:36), capture local (rt.orchestrator.sandbox cũng reachable nhưng capture local sạch hơn) |
| 422 vs 500 lẫn lộn | med×UX | bắt TopologyError+ValueError→422; còn lại 500 |
