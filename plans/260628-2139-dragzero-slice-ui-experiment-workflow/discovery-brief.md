---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Discovery brief — Playbook xây slice + UI cho drag_from_zero

- Ngày: 2026-06-28 21:39 +07
- Slug: `dragzero-slice-ui-experiment-workflow`
- Trọng tâm (user chốt): **trộn runtime + UI**; nghi thức **phân tầng** (spike nhanh, full-gate chỉ khi đụng hard stage)
- Mục tiêu của brief: trả lời "prompt thế nào, dùng skill gì, từng bước" để thử nghiệm nhiều slice + UI mà **không bị loạn**.

---

## 1. Vấn đề (framing)

User muốn xây/thử nghiệm **nhiều** vertical slice + tính năng UI trên `drag_from_zero/dragzero` (agent event-sourced đang sống), nhưng mất phương hướng vì repo chứa 3 codebase và harness có ~50 skill. Hai ẩn số quấn vào nhau:

1. **Quy trình** — chuỗi skill + mẫu prompt nào cho một vòng slice (gồm cả UI) trong harness này.
2. **Cái gì** — slice/feature/UI nào đáng thử trước.

Brief này coi (1) là sản phẩm chính (một playbook lặp lại được), (2) là ví dụ cụ thể để bám (3 việc đầu).

**Không phải vấn đề:** harness thiếu quy trình. Quy trình đã có, đã chặt; user chỉ chưa có bản đồ một-trang để theo.

---

## 2. Bằng chứng (research = scout repo, 3 agent song song)

Web research bỏ qua — câu hỏi là về chính harness + repo. Bằng chứng neo file:

- **Chuỗi skill chuẩn:** `plan → cook → test → code-review → git/ship`, `cook⇄test` là vòng sửa — [skill-chains.yaml:12-23](harness/data/skill-chains.yaml). Gate đọc artifact JSON trên đĩa, chặn cứng ở hard stage — [gate_stage.py](harness/hooks/gate_stage.py), [stage-policy.yaml:19-30](harness/data/stage-policy.yaml). Handoff + isolation — [workflow-handoffs.md](harness/rules/workflow-handoffs.md). TDD 100%-pass là gate — [tdd-discipline.md:13-21](harness/rules/tdd-discipline.md). Evidence phải neo file:line/SHA, verdict ở JSON không phải prose — [verification-mechanism.md:8-21](harness/rules/verification-mechanism.md).
- **Khuôn slice của dragzero:** mỗi slice = `EventType` mới → emit ở [orchestrator.py](drag_from_zero/dragzero/orchestrator.py) → fold ở [read_model.py:59](drag_from_zero/dragzero/read_model.py) → (UI) `translate_event` ở [server.py:165](drag_from_zero/dragzero/server.py) → `tests/test_sliceN_*.py`. Nguyên tắc "tắt feature = byte-identical". **326 test** (`pytest -q`; `browser`/`real_llm` opt-in — [pyproject.toml:22-31](drag_from_zero/pyproject.toml)).
- **UI là stdlib thuần:** WS broadcast trong [server.py](drag_from_zero/dragzero/server.py) + `ui/Agent IDE.dc.html` vanilla — **không React build**. Verify UI bằng `preview_*` (screenshot/console/network), KHÔNG dùng `ui-styling`/`frontend-development`.
- **Seam mở rộng đã biết chỗ:** `CHECK_VOCAB` [verifier.py:239](drag_from_zero/dragzero/verifier.py) · `ToolRegistry` [registries.py:46-64](drag_from_zero/dragzero/registries.py) · `EventType` [events.py:12-44](drag_from_zero/dragzero/events.py) · eval `scorer` [eval/scorers.py](drag_from_zero/dragzero/eval/scorers.py) · topology node [topology.py:15-16](drag_from_zero/dragzero/topology.py).
- **Frontier đang dở:** multi-lens ~75% xong nhưng **chưa commit** (4 file mới `??` + 7 file core dirty) — [plan.md](plans/260628-0152-multi-lens-advisory-consult-lenses/plan.md); recursion-without-AC mới có brief, chưa code — [260628-1129-recursion-without-ac](plans/260628-1129-recursion-without-ac/); D1 triage đã commit (`5e24e32`) nhưng **chưa có UI** (SLICE-D3 hoãn). Kỷ luật cần giữ khi lớn lên — [design-lessons report §11-14, §anti-bài-học](plans/reports/design-lessons-260626-1528-worth-learning-from-hex-agent-report.md).

---

## 3. Playbook — quy trình lặp lại được (phần chính)

### 3.0. Luật bất biến của mọi slice dragzero

Một slice = **một lớp additive** chạm đúng 5 chỗ. Học thuộc 5 chỗ này là hết loạn:

```
1. events.py        + EventType.X = "x"            (từ vựng mới)
2. orchestrator.py  self.log.append(Event(type=X)) (phát ở chokepoint)
3. read_model.py    reduce(): nhánh xử lý X         (gập vào cây — projection)
4. server.py        translate_event(): X → UI event (chỉ khi có mặt UI)
5. tests/test_sliceN_X.py                            (cổng: test cũ vẫn xanh)
```

Bất biến: **tắt feature → event stream byte-identical slice trước**. Nếu test cũ đỏ khi feature TẮT → bạn làm sai additive.

### 3.1. Hai tầng nghi thức (chọn theo độ chín của slice)

| | **Tầng A — Spike** (thử nghiệm, throwaway-friendly) | **Tầng B — Feature** (giữ lại, sẽ push/PR) |
|---|---|---|
| Khi nào | Dò một ý, chưa chắc giữ | Slice "tốt nghiệp", đụng hard stage (push/pr/ship) |
| Skill | sửa thẳng + TDD đỏ→xanh (theo [primary-workflow.md:7-26](harness/rules/primary-workflow.md)) | `/hs:plan → /hs:cook → /hs:test → /hs:code-review → /hs:git → /hs:ship` |
| Gate | chỉ **TDD 100% pass** + verify chạy thật (không bỏ qua được) | đủ 3 artifact: `verification.json` PASS + `review-decision.json` PASS + `plan-approval.json` |
| Bỏ qua được | plan, approval, review, ship | không — `gate_stage.py` exit-2 nếu thiếu artifact ở hard stage |

**Luật phân tầng:** mọi thứ bắt đầu ở Tầng A. Một slice **chỉ** lên Tầng B khi (a) bạn quyết giữ nó VÀ (b) sắp `push`/`pr`. Đừng full-gate một spike — phí.

### 3.2. Vòng Tầng A (spike runtime) — từng bước

1. **(tùy chọn) Định vị seam.** Lệnh: `/hs:scout tìm chỗ thêm <event/check/tool> trong dragzero và file nào phải sửa`. Bỏ qua nếu đã biết (bạn có §3.0).
2. **Viết test đỏ trước.** `tests/test_<slug>.py` mô tả hành vi mới + 1 assert "tắt feature = byte-identical".
3. **Sửa 5 chỗ** (§3.0). Giữ stdlib, standalone, không import `decompose_agent`.
4. **Xanh:** `cd drag_from_zero && python -m pytest -q` → 100% pass (gồm test cũ).
5. **Chạy thật (nếu cần model):** `python run_local.py --sandbox ./work --task "..."` hoặc `python demo.py`.

### 3.3. Nhánh UI (khi slice có mặt UI) — verify bằng preview_*

Sau bước runtime, nếu event cần hiện lên Agent-IDE:

6. Thêm nhánh `translate_event()` ([server.py:165](drag_from_zero/dragzero/server.py)) map EventType → UI vocab; (nếu state-bearing) thêm field trong `build_graph()` [server.py:106-137](drag_from_zero/dragzero/server.py).
7. Render trong `ui/Agent IDE.dc.html` (vanilla).
8. **Verify hành vi (không tự đoán):** `preview_start` → mở `http://127.0.0.1:8000` → click Run → `preview_console_logs` (0 lỗi) + `preview_snapshot`/`preview_screenshot` (event mới hiện đúng) + `preview_network` (WS frame). Đây là evidence cho `verification.json` ở Tầng B.
9. (tùy chọn) `pytest -m browser` nếu muốn pin deterministic bằng Playwright.

### 3.4. Lên Tầng B (khi giữ + sắp push)

1. `/hs:plan` — gói slice thành plan có phase + acceptance. Prompt: *"Plan slice <tên>; --tdd; gate trên drag_from_zero/tests/; stdlib-only standalone."*
2. **Duyệt (người)** — autonomy dừng ở đây. `/clear` trước cook (carryover plan làm lệch cook — [workflow-handoffs.md:24-30](harness/rules/workflow-handoffs.md)).
3. `/hs:cook </abs/path/plan.md>` — TDD đỏ→xanh theo phase, sinh `verification.json` + `review-decision.json`.
4. `/hs:test` — 100% pass gate.
5. `/hs:code-review` — verdict vào `review-decision.json` (phải **đúng** PASS; PASS_WITH_RISK không qua hard stage).
6. `/hs:git` → `/hs:ship official` — gate 3-artifact + duyệt người.

### 3.5. Cheatsheet prompt (copy-paste)

| Bước | Gõ |
|---|---|
| Định vị | `/hs:scout chỗ thêm <X> trong dragzero + file phải sửa + test liên quan` |
| Spike | (gõ thẳng) `Thêm EventType <X>, emit ở orchestrator, fold ở read_model, test_<x>.py đỏ trước rồi xanh; tắt feature phải byte-identical; chạy pytest -q` |
| UI | `Map <X> qua translate_event ở server.py, render ở Agent IDE.dc.html; verify bằng preview_* (console 0 lỗi + snapshot)` |
| Lên plan | `/hs:plan slice <X>; --tdd; gate drag_from_zero/tests/; stdlib standalone` |
| Cook | `/clear` rồi `/hs:cook </abs/path/plan.md>` |
| Review→ship | `/hs:test` → `/hs:code-review` → `/hs:git` → `/hs:ship official` |
| Phân vân slice nào | `/hs-think:brainstorm <ý tưởng slice>` · còn mơ hồ: `/hs-research:discover <ý tưởng>` |

---

## 4. Không gian lựa chọn (đã cân nhắc)

- **Nghi thức:** (A) full-gate mọi slice — an toàn, chậm, phí cho spike. (B) **phân tầng** ✅ — spike rẻ, gate chỉ khi push. (C) tối giản — chỉ TDD, gom nhiều slice mới ship; rủi ro trôi quá xa không review. → Chọn **B** (YAGNI; khớp [primary-workflow.md:30](harness/rules/primary-workflow.md) "review khi high-risk/cross-module/public-contract").
- **Thứ tự candidate:** 14 ứng viên trong backlog (mục 6). Cụm theo 4 theme: *land frontier dở · làm loop quan sát được · gia cố gate · pivot verdict*. Trộn runtime+UI → ưu tiên cụm "frontier dở" + "loop quan sát được".

---

## 5. Hướng chọn — 3 việc đầu (ví dụ chạy thật của playbook)

Trộn runtime + UI, phân tầng. Làm đúng thứ tự:

### Việc 1 — Hoàn tất + COMMIT multi-lens (runtime, Tầng A→B)
**Vì sao trước:** 75% xong, xanh, nhưng nằm uncommitted trên 7 file core — trạng thái dễ vỡ nhất repo. Phase 4 nhỏ: loader `lenses.yaml` → `load_lenses`, nhánh adapter `request:"lens"` (OpenAICompat/Recorded), key-by-lens-id cho determinism ([plan.md:96](plans/260628-0152-multi-lens-advisory-consult-lenses/plan.md)).
**Bước:** §3.2 (test phase-4 đỏ→xanh) → `pytest -q` 326+ xanh → vì đã có plan duyệt, đi thẳng `/hs:cook` phase còn lại → `/hs:git` commit cả slice. **S.**

### Việc 2 — Recursion-without-AC slice 1: chỉ 3 bug fix (runtime hardening, Tầng A)
**Vì sao:** 3 bug nằm trong engine *gated đang chạy*, sửa là lời bất kể có làm nhánh ungated hay không: `_decomp_sig` re-key cho `done_when` rỗng; `_close_parent` FAIL-on-failed-child cho nhánh ungated-decomposed; `record_step()` ở entry ungated ([brief §3,§7](plans/260628-1129-recursion-without-ac/); `orchestrator.py:35-41,571-574`). Tách hẳn khỏi fork sản phẩm chưa chốt ở §6 của brief đó.
**Bước:** §3.2, test đỏ tái hiện từng bug → xanh. **M.** Không lên Tầng B vội (chưa push).

### Việc 3 — Đưa D1 triage lên UI (UI, Tầng A + nhánh preview)
**Vì sao:** D1 ship event+projection, **không UI** (SLICE-D3 hoãn) → luồng người-dùng-thật ("gõ input → worker phân loại → task-box hiện") đang vô hình. `reduce_inbox()` đã có; chỉ là plumbing phía consumer, không đụng core.
**Bước:** §3.3 (translate `task_box_created`/`answer_produced`/`task_box_rejected` → UI; render; `preview_*` verify console 0 lỗi + task-box hiện). **M.**

> Cố ý KHÔNG đưa vào top-3: **supervisor-LLM verdict (DEC-16)** — đòn bẩy cao nhất nhưng L-size, đổi bản chất core; để sau khi eval phủ path mới (xem mục 7). **Burr spike** — off-spine, chờ được.

---

## 6. Backlog ứng viên (rút gọn, đủ 14 ở scout)

Frontier dở: lens phase 4 (S) · commit lens (S) · recursion bug-fix (M) · recursion ungated branch (M) · AC merge-back (M). Loop quan sát được: D1→UI (M) · lens lines→UI (S) · eval cho lens/decompose (M) · lens telemetry (S). Gia cố gate: safety always-ON audit (S) · structural-validation dùng chung gated/ungated (S) · live cycle re-check (M). Pivot: supervisor-LLM verdict (L). Off-spine: Burr FSM spike (M).

---

## 7. Câu hỏi mở

1. **Fork sản phẩm recursion-without-AC:** scaffold throwaway hay sản phẩm AC-free vĩnh viễn? Chặn slice 2/4 ([brief §6](plans/260628-1129-recursion-without-ac/)). Cần chốt trước khi vượt bug-fix.
2. **Thời điểm pivot supervisor-LLM (DEC-16):** trước hay sau khi có eval phủ lens/decompose? Khuyến nghị: eval (#8) trước, vì pivot cần đo "code-gate FAIL vs supervisor PASS".
3. **K tuning** (K=3 phẳng hay scale theo `done_when_count`) — [design-lessons open-q](plans/reports/design-lessons-260626-1528-worth-learning-from-hex-agent-report.md).
4. **Lens monoculture/echo:** chỉ log để đo sau, hay cần detector? (user đã nhận rủi ro).

---

## 8. Ngoài phạm vi (OUT)

- Hệ root hex_agent cũ (`core/ control/ graph/ …`) — đã bỏ, đừng đụng.
- React/Tailwind UI, `ui-styling`, `frontend-development` — UI là stdlib vanilla.
- Import chéo `decompose_agent/` — dragzero standalone, stdlib-only.
- Async/multi-process/work-stealing — target một-process.
- Mở rộng brief thành mọi feature tương lai — scope creep → thêm vào backlog (mục 6), không phình brief.

---

## Next step

- **Proceed:** `/clear` rồi `/hs:plan` cho **Việc 1** (lens phase 4) — hoặc bỏ qua plan, đi thẳng `/hs:cook` plan multi-lens đã duyệt sẵn.
- **Revise:** nói nếu muốn đổi trọng tâm/nghi thức hoặc thứ tự 3 việc.
- Nhắc: `/clear` trước khi planning (carryover discovery làm lệch plan — [workflow-handoffs.md:39](harness/rules/workflow-handoffs.md)).
