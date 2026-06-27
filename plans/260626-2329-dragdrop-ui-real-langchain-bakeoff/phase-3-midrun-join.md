---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 3 — Mid-run join: inject agent cho role trống giữa phiên, từ UI

> Anchors re-verified @ server.py 482 LOC. Runtime đã làm được (`join_agent`→`_wake_waiting`→resume, orchestrator.py:66-87). Thiếu: (a) Run giữ trạng thái parked-không-done, (b) endpoint join, (c) frame `agent_joined` + `await_role` (cả hai HIỆN không tới WS), (d) FE affordance, (e) cancel/shutdown an toàn.

**Mục tiêu:** Kịch bản chuẩn root→plan→**delegate role TRỐNG**→`task_waiting`→UI **await_role**→inject→**resume**→child **done**, từ UI.

**Files:**
- Modify: `drag_from_zero/dragzero/server.py` (Run lifecycle awaiting + `_join_evt` + `join` + `close` + `/api/runs/{id}/join` + `/cancel` + `translate_event` thêm `agent_joined`/`await_role` + `_ws` keep-alive), `drag_from_zero/run_server.py` (shutdown hook)
- Modify: `drag_from_zero/app/**` (FE inject affordance)
- Create: `drag_from_zero/tests/test_midrun_join.py`
- KHÔNG đụng: `orchestrator.py` (bất biến — join_agent đã đủ), core khác

## Chẩn đoán đúng (sửa chẩn đoán sai của bản trước)

Sealed-room OVERTURN: hiện một run parked bị báo **done**, KHÔNG phải "blocked". `Run._run` (server.py:264-276) gọi `run_until_idle()` một lần → khi child park (`_waiting`, orchestrator.py:237-241) `_ready` cạn → return → `_final_status` chạy: root status = **DELEGATED** (read_model.py:59-61), KHÔNG WAITING → rơi xuống catch-all `return "done"` (server.py:143). ⇒ run báo **thành công** trong khi chờ inject — misreport tệ hơn "blocked". (Bản trước viết "root WAITING → _final_status blocked server.py:98" — sai cả status, cả dòng.) Fix: Run phân biệt **awaiting** (`waiting_count()>0`, orchestrator.py:121) với done thật, KHÔNG để root DELEGATED-có-child-parked rơi catch-all done.

## Requirements

**Functional:**
- **Run lifecycle (while-loop):** lặp `run_until_idle()`; nếu `waiting_count()==0` → break → `_final_status` → done thật. Nếu `waiting_count()>0` → status=**awaiting**, KHÔNG mark done; chờ `_join_evt` (re-emit `await_role`/snapshot mỗi <60s để WS không timeout); khi join → re-drive. `run_end`/`_final_status` CHỈ chạy khi `waiting_count()==0`. Timeout `_join_evt.wait` → re-emit await_role, lặp lại (KHÔNG rơi xuống run_end), bounded bởi `_closed`.
- **`POST /api/runs/{id}/join` body=`{role,[id]}`** → `Run.join` → `Agent(id|role, role, self._llm_provider())` → `orch.join_agent(agent, resume=False)` → `_join_evt.set()` → `{ok, woke}`. Join khi không-awaiting → `{ok:true, woke:false}` no-op (200).
- **`POST /api/runs/{id}/cancel`** → `Run.close()` → wake parked thread, emit `cancelled`, KHÔNG run_end giả-done.
- **`reset()`/`start()` guard:** early-return khi `status in ("running","awaiting")` (server.py:219,229 hiện chỉ chặn "running" → second /start lúc awaiting sẽ rebuild orch, orphan thread parked). Awaiting = busy.
- **WS frame mới (translate_event, server.py:155):**
  - `AGENT_JOINED` → `agent_joined` (HIỆN không có case → trả `[]`, server.py:185; AGENT_JOINED log tại orchestrator.py:68 nhưng chưa tới WS). Thêm: `E("agent_joined", node_id=None, payload={"role":p.get("role"),"agent":ev.agent_id})`.
  - `TASK_WAITING` → đổi `block` (server.py:167-168) thành `await_role` `payload={"role":p.get("target")}`. (Legacy ui/ có `case "block"` dormant — DEC-A2 retired, TASK_WAITING chưa từng tới nó; an toàn.)
- **`_ws` keep-alive (server.py:464-468):** `except Empty: if run.done: break` (continue khi parked) — hiện break sau 60s → mất stream trước khi user inject (park có thể >60s).
- **FE:** node awaiting hiện nút "Inject agent for role X" → `POST /join` → cùng WS resume tới child done.

**Non-functional:**
- orchestrator.py BẤT BIẾN; mọi thay đổi ở Run/_Handler/run_server (server.py + run_server.py).
- `_llm_provider` đến từ P1 (Run lưu nó). Run demo/6a dựng trực tiếp cũng phải nhận provider (P1 đã wire run_server; test tự cấp `lambda: FakeLLM(...)`).
- Thread-safety: join tới khi thread parked (`_join_evt.wait()`, KHÔNG trong `_process_one`) → `join_agent` mutate roster + `_wake_waiting` tuần tự, không đồng thời mutate. **Single-user-local (constraint brief §2)** ⇒ join đồng thời = OUT scope; ghi assumption, không thêm lock vào orchestrator bất biến.

## Tests Before (đỏ) — `tests/test_midrun_join.py`

Fixture chung (nice-to-have): topology park-on-empty-role (entry planner, KHÔNG node "specialist", read/write tool) + responder planner→delegate target="specialist", specialist→solo (mirror test_slice3_workqueue.py:21-26). create_run nhận custom llm_provider cho test này.
- **Unit (Run, không HTTP):** start → `_await` status **awaiting** (KHÔNG done), `waiting_count()==1`. `run.join("specialist")` → tiến tới **done**; log có `agent_joined` GIỮA `task_waiting` và child `task_completed` (orchestrator.py:68; trace README:96-97).
- **Diagnosis-pin:** TRƯỚC fix, run parked → `_final_status==done` (chứng minh bug báo done); SAU fix → status awaiting tới khi join. (Pin để cook không implement theo chẩn đoán sai.)
- **Timeout cycle:** park qua 1 chu kỳ `_join_evt.wait` → status vẫn **awaiting**, `await_role` re-emit, KHÔNG run_end.
- **HTTP:** `POST /api/runs` topology-park → `/start` → poll awaiting → `POST /join {role:"specialist"}` → poll done; graph child done.
- **WS:** frames có `await_role`(role=="specialist") + `agent_joined` TRƯỚC `verdict`/`run_end`.
- **No-op + guard:** join khi done → `{woke:false}`; second `/start` lúc awaiting → no-op (không orphan, orch object không đổi — pin bằng `id()`).
- **Cancel/shutdown:** `/cancel` lúc awaiting → thread thoát, status cancelled, KHÔNG run_end done-giả; fixture đóng run trước `httpd.shutdown()`.
- **Regression:** topology không-park (6a demo) → done trực tiếp, KHÔNG kẹt awaiting.

## Implement

1. **`Run.__init__`:** thêm `self._join_evt=Event()`, `self._closed=False`. (provider `self._llm_provider` đã có từ P1.)
2. **`_run` (server.py:251):** refactor body:
   ```python
   self.orch.log.subscribe(sub)
   try:
       while True:
           self.orch.run_until_idle()
           if self.orch.waiting_count() == 0:
               break
           self._set_status("awaiting"); self._emit_snapshot()
           while self.orch.waiting_count() > 0 and not self._closed:
               woke = self._join_evt.wait(timeout=30); self._join_evt.clear()
               if self._closed: break
               if woke: break
               self._emit_snapshot()          # heartbeat < 60s WS
           if self._closed:
               self._set_status("cancelled"); self._emit({"type":"run_cancelled"}); return
       status = _final_status(self.orch.log, self.sandbox, self.done_when, self._activated_at)
   except Exception as exc: ...
   ```
   `clear()` SAU `wait()` (lost-wakeup an toàn — set-before-wait OK).
3. **`Run.join(role, id=None) -> bool`:** như §Requirements; return woke.
4. **`Run.close()`:** `self._closed=True; self._join_evt.set()`.
5. **`App.close()`:** gọi `close()` mọi run. `make_server` expose; `run_server.py` main `finally: httpd.app.close()`.
6. **`reset`/`start` guard:** `if self.status in ("running","awaiting"): return`.
7. **`translate_event`:** thêm case `AGENT_JOINED`, đổi `TASK_WAITING`→`await_role`.
8. **`_ws`:** `except Empty: if run.done: break` (else continue).
9. **`do_POST`:** route `/join` + `/cancel`.
10. **FE (`app/src/live/`+`api/client.ts`):** `joinAgent(runId,role)`; node awaiting → nút inject; cùng socket resume.

## Tests After / Regression Gate

- `python -m pytest drag_from_zero/tests/test_midrun_join.py -q` xanh.
- `python -m pytest drag_from_zero/tests -q` **xanh** (đặc biệt test_slice6a_server.py + test_slice3_workqueue.py + e2e/test_topology_to_server.py + test_authoring_api.py).
- e2e (P2 spec mở rộng): author topology-park → Run → UI await_role → inject → tree done.
- `git diff drag_from_zero/dragzero/orchestrator.py` = **rỗng**.

## Success Criteria

- [ ] Run park đúng (awaiting, KHÔNG done) khi `waiting_count()>0`; resume tới done sau join.
- [ ] `agent_joined` GIỮA `task_waiting`/`await_role` và child `task_completed` (log + WS).
- [ ] `POST /join` HTTP + UI → child done; second /start lúc awaiting no-op; `/cancel` thoát sạch.
- [ ] Park >60s không rớt WS (keep-alive); timeout cycle giữ awaiting.
- [ ] orchestrator.py diff rỗng; topology không-park không regress.

## Risk

| Risk | L×I | Mitigation |
|---|---|---|
| Refactor `_run` while-loop sai → run không-park kẹt awaiting / happy-path regress | high×regress | break khi `waiting_count()==0`; test regression topology-không-park + diagnosis-pin bắt buộc; orchestrator bất biến |
| Thread treo nếu không inject | med×hang | inner-while bounded bởi `_closed`; `/cancel` + `App.close()` lúc shutdown; daemon thread |
| WS rớt giữa park (60s) | med×UX | `_ws` continue-while-not-done + heartbeat snapshot 30s |
| second /start|/reset lúc awaiting orphan thread | high×corrupt | guard `status in (running,awaiting)`; pin orch `id()` không đổi |
| join đồng thời mutate roster | low×corrupt(single-user) | join chỉ tới khi parked (thread ở `_join_evt.wait`); single-user-local ⇒ concurrent join OUT scope, ghi assumption |
| đổi TASK_WAITING vocab phá consumer | low×break | 6a/integration test KHÔNG assert block-cho-waiting; pin await_role; legacy ui/ dormant + retired (DEC-A2) |
