---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Roadmap sống — 6 epic tương lai thành living note (có critique)

Report · 2026-06-25 23:08 · nguồn: workflow `roadmap-living-notes` (7 agent, bám code thật)
Bổ trợ DEC-1 (cấu trúc docs/) · phục vụ `docs/roadmap/future/`

> Mỗi note trả lời 3 câu user yêu cầu: **tồn tại để giải vấn đề gì** · **vì sao chưa đấu nối được** · **ngưỡng đo-được nào báo "giờ đấu nối"**. Kèm critique YAGNI + verdict. Evidence (file:line) giữ verbatim.

---

## TL;DR — bảng trạng thái

| Epic | Verdict | Cổng vào | Cổng ra | Ngưỡng rã đông (rút gọn) | Tầng thứ tự |
|---|---|---|---|---|---|
| **E11** Departments | park-with-trigger | 🟢 E09/E06/E08 done | 🔴 chờ E12 | dept distinct ≥4 (nay 2) HOẶC role ≥8 (nay 4) HOẶC E12 thiết kế | 1 (minimal) |
| **E12** IntentRouter | park-with-trigger | 🔴 chờ E11+E13 | — | E11 có ≥2 template + ≥3 loại task + ≥1 request "mixed" | 3 (hội tụ) |
| **E13** Software Factory | park-with-trigger | 🟢 E09/E10 done | 🔴 chờ E12 | owns_validation:false ≥3 (nay 1) HOẶC E12 khởi động | 2 (minimal) |
| **E14** Ledger & Memory | park-with-trigger | 🟢 E06/E08 done | 🔴 chờ E12 | run >500 (nay 0) HOẶC resume-call-site >0 (nay 0) HOẶC E12 cần lịch sử | 4 |
| **E15** Self-eval | **merge-into-other** | 🟡 chờ E21 | — | ≥2 tác nhân chấm chéo HOẶC incident "AC passed nhưng sai" HOẶC E21 vượt Phase B | 0 (vào E21) |
| **E20** Labs | park-with-trigger | ⚪ cổng-thời-điểm | — | ≥3 utility feature trùng lặp HOẶC cần profile labs-vs-prod | 5 (cuối) |

**Một câu xuyên suốt**: `deps 🟢` = *được phép* làm, KHÔNG phải *nên* làm. Một field ghi-mà-không-đọc (vd `.department`, read-sites = 0) là tín hiệu YAGNI, không phải tín hiệu sẵn sàng.

---

## E11 — Departments · `park-with-trigger`

**Giải vấn đề gì khi tồn tại**: đơn vị tổ chức trung gian giữa "1 role" và "cả company". Cho E12 một trục định tuyến cấp-phòng-ban (fan-out theo team thay vì hard-code danh sách role); cho phép áp policy/scope/ngân sách theo department thay vì lặp trên từng role; nâng separation-of-duties lên cấp tổ chức.

**Vì sao chưa đấu nối**: chưa có thứ tiêu thụ `department`. Định tuyến chạy thuần theo role qua `may_route_to` (`roles/spec.py:49`, `roles/agent.py:53`); grep `department` trong delegation/orchestrator/supervisor/control/core = **rỗng**. Library 4 role / 2 phòng ban (engineering×3, product×1) — string là đủ. Consumer thật (E12) chưa bắt đầu.

**Neo hiện tại**: `roles/spec.py:19` (department là field bắt buộc) · `roles/spec.py:45` (`department: str` string trần) · `roles/spec.py:104` (parse `str(...).strip()`, không validate) · `roles/library/{code,test,reviewer}.yaml:3` = engineering, `business_analyst.yaml:3` = product · read-sites của `.department` ngoài test = **0**.

**Ngưỡng rã đông** (chạm 1 trong số): (1) dept distinct ≥4 (nay 2); (2) role ≥8 khiến `may_route_to` phình O(n²); (3) **E12 vào thiết kế cần trục route theo team** — trigger mạnh nhất; (4) cần policy theo nhóm khiến 1 rule copy ≥3 lần.

**Phác đấu nối**: nâng `department: str` (`roles/spec.py:45`) → value object/`DepartmentRegistry` cạnh `roles/registry.py`, validate tại `roles/spec.py:104`; thêm hàm derive role-theo-department cho E12 fan-out; policy cấp-department cắm vào hợp nhất scope `roles/spec.py:53-63` giữ "forbidden wins". Bắt đầu nhỏ: registry+validate trước.

**Critique**: YAGNI mạnh ở dạng "hạ tầng". Field bắt buộc từ E09 mà 0 read-site = tính năng đầu cơ điển hình. Rẻ hơn: giữ string, chỉ thêm registry khi E12 gọi. **Build sớm** = đóng băng abstraction sai cho 2 phòng ban (rủi ro over-engineer hierarchy/policy-engine). **Bỏ hẳn** = `may_route_to` phình O(n²), SoD kẹt ở role↔role, nợ đẩy sang E12.

---

## E12 — IntentRouter / GlobalSupervisor · `park-with-trigger`

> ⚠ `supervisor/` HIỆN TẠI là **E10** (TaskLoop, Agent O), KHÔNG phải E12.

**Giải vấn đề gì**: dispatcher toàn cục cho nhiều LOẠI request. `classify(request) → RouteDecision → safety gate → chọn template (E11) → giao 1 task cho TaskLoop E10` (`supervisor/loop.py:70`); request "mixed" → plan nhiều bước. Tách vai rõ với Agent O: E12 quyết "ai làm", O quyết "làm thế nào". Entrypoint thôi giả định mọi prompt cùng loại.

**Vì sao chưa đấu nối**: cổng 🔴 chặn cứng bởi E11 ⬜ + E13 ⬜ (`01_BUILD_ORDER_AND_DEPENDENCIES.md:22`, `PRD.md:26`). E12 là vỏ "chọn rồi giao": cần tập template (E11 chưa có) + spec→handoff (E13 chưa có). Với 4 role / 2 dept / 1 entrypoint, một if/heuristic 5 dòng còn rẻ hơn IntentRouter có confidence + LLM fallback.

**Neo hiện tại**: `roles/spec.py:45` (department parse-rồi-bỏ) · `roles/spec.py:49` (`may_route_to` khai báo nhưng chưa engine đọc) · `supervisor/loop.py:70` (`run_task_loop` — seam E12 sẽ gọi, chưa ai gọi từ tầng trên) · KHÔNG có symbol intent/router/classify/RouteDecision nào trong app.

**Ngưỡng rã đông** (đồng thời): (1) E11 ship — ≥2 template chọn-được-bằng-code (nay 0); (2) ≥3 loại task phân biệt ở `ui/server.py`; (3) ≥1 request "mixed" cần ≥2 TaskLoop (cần E13). Phụ: >8 role qua ≥4 dept khiến bảng route phẳng sai-route đủ thường.

**Phác đấu nối**: package mới `router/` (KHÔNG động supervisor/): `IntentRouter.classify → RouteDecision` rule-based + LLM fallback khi confidence thấp; `GlobalSupervisor.run` chạy safety gate → đọc `department`+`may_route_to` chọn template → gọi `run_task_loop` (`supervisor/loop.py:70`). Đấu vào `ui/server.py` (~238/271). Emit RouteDecision qua `control/emitter.py:53` cho Control Tower E21.

**Critique**: dạng đầy đủ PRD = over-design. Cần sớm chỉ là seam "một-cửa nhận request" trong GlobalSupervisor; hoãn confidence calibration tới khi có dữ liệu route-sai. **Build sớm** khi E11 chưa có template = route vào hư-không, mock đông cứng thành interface sai. **Bỏ hẳn** = khoá vào 1 loại task, `may_route_to` chết vĩnh viễn.

---

## E13 — Software Factory · `park-with-trigger`

**Giải vấn đề gì**: dây chuyền xác định, lặp-lại-được: spec → BA làm rõ → code → test → reviewer, theo thứ tự CỐ ĐỊNH có cổng handoff, thay vì để Agent O chọn tuyến tự do mỗi vòng. Biến SoD (đang là quy ước yaml) thành pipeline thật có artifact bàn giao + audit per-chặng. Cùng spec chạy lại đi đúng cùng đường — thứ TaskLoop hiện không đảm bảo.

**Vì sao chưa đấu nối**: chưa đủ "tải". Library 5 vai trò, chỉ DUY NHẤT `code` không-tự-validate (`roles/library/code.yaml:18-19` owns_validation:false, must_handoff_to:test) → chuỗi handoff bắt buộc dài **1 cạnh** (code→test). Định tuyến đa-role ĐÃ chạy qua E10: Agent O phát `next_agent_calls` mỗi vòng (`supervisor/contracts.py:48-55`), `_drive` lặp tới terminal (`supervisor/loop.py:153-199`). "Đi qua nhiều role" không bị chặn — chỉ chưa cố-định-hóa.

**Neo hiện tại**: DAG handoff tĩnh trong yaml (`business_analyst.yaml:7-9`, `code.yaml:13-19`, `test.yaml:11-13`, `reviewer.yaml:12-14`) · enforcement per-role không có orchestrator dây chuyền (`roles/agent.py:31-34`, `:56-68` guard_finish) · "spec" hiện chỉ là per-call `DelegationSpec` (`core/schemas.py:135-137`) + per-round `AgentAssignment` (`supervisor/contracts.py:40-44`) · tên "Factory" duy nhất = `SessionFactory` (`core/session.py:104`, KHÔNG liên quan).

**Ngưỡng rã đông**: (a) owns_validation:false ≥3 (nay 1) → chuỗi handoff ≥3 cạnh; (b) cùng spec chạy lại ≥10 lần theo thứ tự cố định; (c) cần audit "chặng nào tạo artifact nào" mà `delegation.finished` (`delegation/manager.py:52-61`) chỉ cho artifact_count phẳng; (d) **E12 khởi động** (map E12→E13).

**Phác đấu nối**: định nghĩa `FactorySpec` cạnh `core/schemas.py` (KHÔNG nhồi vào DelegationSpec); driver tái dùng `compose_team`/`_drive` (`supervisor/loop.py:147-199`) nhưng đọc thứ tự stage TỪ `may_route_to`/`must_handoff_to` (`roles/spec.py:48-50`); mỗi chuyển-chặng qua `DelegationManager.delegate` (`delegation/manager.py:63`) giữ scope-⊆-parent; thêm `stage_id` vào event để audit.

**Critique**: mục tiêu cốt lõi ("task qua nhiều role có SoD") ĐÃ đạt bằng E10 + role guards, miễn phí. E13 chỉ thêm giá khi cần tính XÁC ĐỊNH của tuyến, không phải khả năng đi nhiều role. Rẻ hơn: cờ `pin_route` ~50 dòng trong supervisor/ khoá o_decide vào tuyến cố định. **Build sớm** = 2 đường định tuyến song song phải bảo trì. **Bỏ hẳn** = E12+E16 khai báo phụ thuộc E13 → phải tái định nghĩa "đơn vị factory" sau. *Lý do duy nhất không bỏ: E13 mở khóa E12.*

---

## E14 — Ledger & Memory · `park-with-trigger`

**Giải vấn đề gì**: 1 lớp lưu bền vững xuyên-run cho (1) "work ledger" truy-vấn-được (agent đã làm gì qua các run) thay cho đống file rời `var/agent_runs/<run_id>/`; (2) "long-term memory" để agent recall run TRƯỚC khi xử task MỚI (episodic, khác KB tĩnh E08). Cho resume/audit cross-run, dedup việc lặp, để E12 quyết dựa lịch sử.

**Vì sao chưa đấu nối**: chưa có consumer đọc lịch sử cross-run. Resume/recall đang CỐ Ý tắt: `orchestrator/checkpoint.py:26` ("not used to resume a graph"), `:139` ("Resume intentionally does not call this"). SQLite truth per-run (`:31-32`). Index toàn cục `observability/event_log.py:95-98` chỉ ghi `{run_id, status}`. RAG = KB tĩnh: collection cố định "agent_kb" (`rag/ports.py:42`), default backend "memory" reset mỗi process (`rag/stores.py:30`, `rag/feature.py:32`). Consumer tự nhiên (E12) chưa bắt đầu.

**Neo hiện tại**: `orchestrator/checkpoint.py:31-32,26,139` (per-run, recall tắt) · `observability/event_log.py:95-98` (index chỉ status) · `rag/ports.py:42` (agent_kb tĩnh) · `rag/stores.py:30` (ephemeral) · grep "ledger|episodic|cross-run" non-test = 0.

**Ngưỡng rã đông**: (a) E12 in-progress VÀ logic route cần đọc ≥1 run trước; (b) run trong `var/agent_runs/` >500 + nhu cầu "agent đã làm task X chưa?"; (c) ≥1 call-site `load_checkpoint()` để RESUME (nay 0, `checkpoint.py:139`); (d) yêu cầu "nhớ giữa phiên". Đo được: consumer-cross-run >0 HOẶC run >500 HOẶC resume-call-site >0.

**Phác đấu nối**: (1) ledger ghi — bám `attach_to_bus()` (`observability/event_log.py:102`) thêm subscriber ghi SQLite global (`runs_dir()/ledger.sqlite`), tái dùng `open_checkpointer` pattern; (2) memory đọc — mở rộng `VectorStorePort` (`rag/ports.py:31-36`) namespace per-agent, write-back sau `finish()` (`event_log.py:80`); (3) `LedgerPort/MemoryPort` cho graph node query trước khi xử task. Port-first.

**Critique**: YAGNI ở quy mô hiện tại. 80% giá trị "ledger" đã có qua `var/agent_runs/<run_id>/` + CLI `inspect.py`; "memory" tĩnh đã có qua RAG. Rẻ hơn (90% mục tiêu): chỉ làm **B1** — đổi index.jsonl → SQLite global query-được (1 ngày, không phải epic). **Build sớm** = lock-in schema sai + 3 nguồn truth lệch (langgraph.sqlite + taskloop.sqlite + ledger.sqlite). **Bỏ hẳn** = agent vô-trí-nhớ cross-run, chặn trần năng lực "multi-agent durable".

---

## E15 — Self-eval & Governance · `merge-into-other` ⚠

**Giải vấn đề gì**: đóng lỗ "honor-system" của acceptance hiện tại. Hôm nay Agent O tự khai AC, code chỉ kiểm evidence resolve được trên Blackboard chứ KHÔNG kiểm evidence có CHỨNG MINH tiêu chí (`supervisor/graph.py:238` — `claimed=="passed" and evidence and all(e in state.artifacts...)`). Một AC `passed` chỉ cần trỏ tới artifact tồn tại, kể cả rác. E15 đưa người chấm độc lập (judge ≠ doer) + governance "ai chấm, dựa gì, theo policy nào".

**Vì sao chưa đấu nối**: chưa đủ áp lực cần người chấm thứ hai. (1) Pipeline single-loop 1 Agent O, chưa có worker song song mâu thuẫn. (2) Phần governance/audit đã bị **E21 hút**: S21.33 (`E21.../stories.md:57`, `acceptance.md:123`) siết `judge_acceptance` bằng evidence types {artifact, tool_result, reviewer_report, diff, test_result} + bắt sinh "AC report". (3) E16 đã gộp vào E21, mới ship Phase A + B B1; checkpoint contract có (`control/checkpoint.py:28`) nhưng chưa có runtime PAUSE — chưa có cửa cho self-eval cắm vào.

**Neo hiện tại**: `supervisor/graph.py:229,238` (honor-system) · `supervisor/state.py:36` (`is_satisfied` = status==passed + có evidence_ids, không điểm/người chấm) · `supervisor/loop.py:172` (gate finish duy nhất) · `supervisor/orchestrator.py:1` (judge và doer CÙNG tác nhân) · `control/checkpoint.py:28` (seam approval nhưng chưa producer tự động) · `observability/event_log.py:53` (metrics int thuần, chưa chiều chất lượng).

**Ngưỡng rã đông**: (1) ≥2 loại tác nhân sinh output cần chấm chéo (loop >1 worker HOẶC E13 handoff); (2) ≥1 incident "AC passed nhưng output sai" trong event log; (3) checkpoint `waiting` được duyệt-tay >N/ngày đủ phiền; (4) E21 vượt Phase B, có runtime PAUSE thật ở `before_acceptance_review`.

**Phác đấu nối**: node `self_eval` NGAY TRƯỚC `judge_acceptance` (`supervisor/loop.py:171/179/182`), verifier dùng ChatLLM riêng (`supervisor/llm.py`) → doer≠judge; mở rộng `AcceptanceCheck` (`supervisor/state.py:29`) thêm `confidence`/`reviewer`; dưới ngưỡng → phát `RuntimeCheckpoint("acceptance_review")` (`control/checkpoint.py:28`) cho E21 PAUSE; tái dùng "AC report" S21.33 thay vì log riêng.

**Critique**: ứng viên YAGNI mạnh — **không nên là epic riêng**. Governance/audit đã bị E21 S21.33 nuốt. Phần còn lại (judge≠doer) chỉ có giá nếu thật tách verifier; nếu vẫn cùng Agent O tự chấm = honor-system đắt hơn. Rẻ nhất (80%): siết `judge_acceptance` (`graph.py:238`) đòi evidence tự-verify-được (test_result chạy được, diff áp được) — **làm ngay trong E21, không cần epic E15**. **Verdict: merge-into-other (E21).**

---

## E20 — Labs · `park-with-trigger`

**Giải vấn đề gì**: nơi đặt "tiện ích dùng chung" thử nghiệm (scratchpad, fixtures, harness mock offline, demo tools) đóng gói thành feature-plugin bật/tắt qua config, thay vì rải rác trong core. Tách đồ-chơi khỏi đường găng kernel; cho dev bật bộ "labs" thí nghiệm prompt/role/skill mà vẫn qua đúng chokepoint + safety + observability. *Thùng chứa có kỷ luật, không phải hạ tầng mới.*

**Vì sao chưa đấu nối**: cơ chế "utility cắm vào kernel" ĐÃ CÓ và đang chạy → chưa có gì để đấu. Loader `features/loader.py:10` đọc config → import → `install(kernel)`; pattern chuẩn hóa quanh `FeatureDescriptor`+`install` (`features/example_echo.py:23`, `features/llm_chat.py:35`, `toolbox/feature.py:27`). 4 feature enabled (`config/features.yaml:1-13`). Thiếu không phải hạ tầng mà là NHU CẦU cụ thể. Cổng ⚪ "sau S5" (`project-roadmap.md:153`), mà S4/S5 chưa bắt đầu.

**Neo hiện tại**: `features/loader.py:10` (install_configured_features) · `core/schemas.py` FeatureDescriptor dùng tại `features/example_echo.py:9-13,23` · `toolbox/feature.py:27`, `features/llm_chat.py:35`, `rag/feature.py` · `config/features.yaml:1-13` (4 enabled) · chưa có stub doc / test (`project-roadmap.md:171`).

**Ngưỡng rã đông**: (1) ≥3 utility-feature trùng lặp helper ở ≥2 module `features/*`; (2) ≥1 feature "experimental" cần bật dev / tắt mặc định prod (cần profile labs-vs-prod); (3) >1 dev cần workspace scratch chung; (4) S5 đóng (cổng "sau nền vững" mở).

**Phác đấu nối** (cực rẻ, seam sẵn): tạo `features/labs/`, mỗi tool theo pattern FeatureDescriptor+install như `features/example_echo.py:23`; đăng ký qua `config/features.yaml` với `enabled:false` mặc định (loader `:14-16` đã honor cờ); nếu cần, overlay `features.labs.yaml` không sửa loader; mọi tool tự qua `execute_tool` (`core/kernel.py:63`) → "mock offline" đạt không cần đường tắt.

**Critique**: nhiều khả năng KHÔNG cần như epic. Mọi thứ E20 hứa đã làm được hôm nay: thêm 1 file vào `features/` + bật config. Không mở khoá năng lực mới — chỉ là CÁI TÊN/THƯ MỤC. YAGNI điển hình. **Build sớm** = cám dỗ xây "labs runtime/registry" song song loader → trùng đường nạp + nguy cơ đường tắt vòng qua chokepoint (thủng safety). **Bỏ hẳn** = gần như không mất gì; rủi ro duy nhất (feature thử nghiệm bật nhầm prod) giải bằng quy ước `enabled:false` + profile, 1 PR nhỏ.

---

## Thaw Protocol — giao thức "rã đông" một món roadmap

Biến một `wiring_threshold` bị chạm thành plan thực thi, KHÔNG bỏ bước đánh-giá-lại-phụ-thuộc.

**Bước 0 — Phát hiện ngưỡng (Detect)**. Đo định kỳ (mở sprint / thêm role/feature):
```bash
grep -h '^department:' roles/library/*.yaml | sort -u | wc -l    # E11/E12 dept distinct
ls roles/library/*.yaml | wc -l                                  # E11/E12 role count
grep -rl 'owns_validation: false' roles/library/*.yaml | wc -l   # E13 chuỗi handoff
ls var/agent_runs/ 2>/dev/null | wc -l                           # E14 run count
grep -rn 'load_checkpoint(' --include=*.py | grep -v def         # E14 resume-call-site
# + status E12/E21 trong docs/project-roadmap.md (trigger consumer của E11/E13/E15)
```
Ghi vào sổ ngưỡng kèm ngày đo. Ngưỡng "chạm" khi METRIC vượt, không cảm tính.

**Bước 1 — Xác nhận trigger**. `future → triggered` khi ≥1 điều kiện `wiring_threshold` xác nhận bằng số đo + evidence. Verdict `merge-into-other` (E15): KHÔNG thành epic riêng → mở backlog-item trong epic chủ. Trigger "consumer khởi động": xác nhận consumer thật đã in-progress (PR/branch), không phải dự định.

**Bước 2 — Đánh giá lại phụ thuộc (BẮT BUỘC)**. Mở `dependencies` + đối chiếu bảng `01_BUILD_ORDER`. Kiểm: (1) gate-in mọi dep còn Done? (2) vòng chờ chéo? (vd E11↔E12) → áp "mồi phá vòng": rã đông MỨC TỐI THIỂU đủ cho consumer thiết kế. (3) map drift? → sửa bảng trước. Output: `{proceed-full | proceed-minimal | block-on:<epic>}`.

**Bước 3 — Chọn altitude (YAGNI)**. Đọc `critique.is_it_needed`, chọn bản RẺ NHẤT: E11→registry+validate · E12→GlobalSupervisor rule-based · E13→cờ pin_route ~50 dòng · E14→B1 SQLite global · E15→siết judge_acceptance trong E21.

**Bước 4 — Plan**. `/hs:plan` với input = `wiring_sketch` (đã có seam file:line). Plan PHẢI: dùng seam sẵn (không subsystem song song) · gắn AC vào E19 · khai báo ranh giới epic lân cận. `triggered → planned` khi duyệt.

**Bước 5 — Cook → Done**. `/hs:cook`; `planned → active`. AC xanh E19 → `active → done`; cập nhật roadmap 🔴→🟢, bảng phụ thuộc, gỡ trigger phụ. **Hậu-kiểm**: chạy lại Bước 0 cho note downstream (rã đông E11 thường chạm trigger "consumer khởi động" của E12).

---

## Dàn ý `docs/roadmap/README.md`

1. **Roadmap là gì** — KHÔNG phải backlog "sẽ làm hết"; là tập living note có điều kiện rã đông. Triết lý "deps 🟢 = được phép, không phải nên".
2. **Nguồn sự thật** — project-roadmap.md, 01_BUILD_ORDER, architecture-map. Note↔bảng lệch → bảng là nguồn cấu trúc, note là nguồn ý-định; sửa bảng rồi tiếp.
3. **Cách đọc 1 note** — `verdict` → `wiring_threshold` → `dependencies` → `wiring_sketch`. `current_anchors` lệch (file/line đổi) = note cần refresh.
4. **Vòng đời**:
   ```
   future ─(ngưỡng chạm)─▶ triggered ─(deps re-eval OK + plan duyệt)─▶ planned ─(/hs:cook)─▶ active ─(AC xanh E19)─▶ done
   ```
   + nhánh `merge-into-other` (E15 → vào E21, không qua planned/active độc lập); nhánh `block-on:<epic>` (triggered nhưng deps thiếu → về future).
5. **Trạng thái hiện tại** — bảng: Epic | verdict | trạng-thái-vòng-đời | trigger gần nhất | block-on | ngày-đo-cuối. Hôm nay cả 6 ở `future`.
6. **Bảo trì (anti-rot)** — chạy Thaw Bước 0 định kỳ; refresh khi seam đổi; sửa mâu thuẫn map↔note → ghi `docs/decisions.md`.

---

## Thứ tự rã đông gợi ý (sequencing)

- **Tầng 0 — E15 (vào E21, sớm nhất)**: siết `judge_acceptance` (`graph.py:238`) đòi evidence tự-verify trong E21 S21.33. Việc DUY NHẤT tiến hành được không cần consumer mới.
- **Tầng 1 — E11 minimal**: DepartmentRegistry+validate (`roles/spec.py:104`) khi E12 vào thiết kế. Ngưỡng riêng (dept≥4/role≥8) chưa chạm; rã đông theo trigger-consumer, mức registry-only.
- **Tầng 2 — E13 minimal**: cờ `pin_route` ~50 dòng. Gate-in 🟢, là dep E12, trên critical path `E10→E13→E12`. Phải sẵn TRƯỚC E12.
- **Tầng 3 — E12**: GlobalSupervisor rule-based khi đồng thời E11 có ≥2 template + ≥3 loại task + ≥1 mixed. Điểm hội tụ, cuối critical path. Hoãn IntentRouter+LLM tới khi có dữ liệu route-sai.
- **Tầng 4 — E14**: B1 (index.jsonl→SQLite global). Gate-in 🟢, không trên critical path, chạm ngưỡng SAU khi E12 sinh workload.
- **Tầng 5 — E20**: cuối, cổng-thời-điểm. Khi chạm: thêm `features/labs/` + entry config.

**Mấu chốt**: KHÔNG bên nào tự rã đông tới mức đầy đủ; mỗi tầng chỉ build phần tối thiểu đủ mở tầng kế.

---

## Mâu thuẫn / nhất quán phát hiện (cross-note)

1. **MAP DRIFT (E15)** — bảng `01_BUILD_ORDER_AND_DEPENDENCIES.md:23` vẫn ghi `E15 → E04, E10, E16` trong khi header cùng file + note nói E16 đã gộp E21. Nguồn sự thật tự mâu thuẫn → cần sửa `:23` thành `E04, E10, E21`.
2. **DEADLOCK NGƯỠNG E11↔E12** — E12 chờ E11 ship; nhưng trigger mạnh nhất của E11 lại là "E12 in-progress". Áp máy móc → không bên nào rã đông. Cần mồi phá vòng: E11 rã đông mức tối thiểu KHI E12 vào thiết kế.
3. **CHỒNG LẤN E11↔E12 (cùng metric)** — cả hai dùng ~"role≥8/dept≥4" làm trigger. Khi chạm phải quyết E11 trước (cung registry E12 tiêu thụ), tránh kích cả hai lặp việc.
4. **RANH GIỚI E12↔E13 (ai sở hữu multi-step)** — E12 nói "plan nhiều bước cho mixed", E13 là "dây chuyền cố định" + "tránh đụng E12". Chưa có định nghĩa chốt. Cần câu load-bearing: *multi-step trong-1-task = E13 · dispatch nhiều-task = E12*.
5. **CHỒNG LẤN E14↔E15 (audit/ledger)** — E15 dùng "AC report" S21.33; E14 dựng work-ledger SQLite. Tách trục: governance-evidence per-AC (E15/E21) ≠ cross-run work-ledger (E14). Đừng để E15 score ghi vào ledger E14 trước khi E14 tồn tại.
6. **VERDICT KHÔNG ĐỒNG NHẤT** — 5/6 `park-with-trigger`, E15 `merge-into-other`. README vòng đời cần nhánh riêng cho `merge-into-other` (không thành epic, chảy vào epic chủ).
7. **E20 cổng-THỜI-ĐIỂM, không phải cổng-hạ-tầng** — deps kỹ thuật 🟢 hết; ghi rõ để không ai tưởng E20 bị chặn kỹ thuật.
8. **NHẤT QUÁN ĐÚNG** — E11/E13/E14 đều "gate-in 🟢 / gate-out 🔴 (chờ E12)". Khung nhất quán, giữ làm nguyên tắc xếp thứ tự.

---

## Câu hỏi mở (cần người dùng quyết — ảnh hưởng plan)

1. **Sửa map drift E15**: đổi `01_BUILD_ORDER...:23` `E16`→`E21` + cập nhật project-roadmap? (khuyến nghị: có — sửa lỗi factual)
2. **E15 có là note roadmap riêng?**: verdict `merge-into-other` → đề xuất gỡ khỏi `future/`, chuyển backlog-item trong E21. Hay giữ làm note `future` theo dõi phần judge≠doer?
3. **Phá vòng E11↔E12**: chấp nhận nguyên tắc "E11 rã đông mức tối thiểu khi E12 vào thiết kế"?
4. **Ranh giới E12 vs E13**: chốt "multi-step-1-task = E13 / dispatch-nhiều-task = E12"?
5. **Sổ ngưỡng**: `docs/roadmap/THRESHOLDS.md` (ghi kết quả lệnh đếm theo ngày) hay nhúng `last_measured` vào mỗi note?
6. **Tần suất đo + hook**: đo mỗi sprint / mỗi PR thêm role / cron? Có wire hook `.claude/settings.json` nhắc đo khi `roles/library/` đổi?
7. **Định nghĩa "E12 khởi động"** (trigger của E11/E13/E14): branch/PR E12 / thiết kế duyệt / có call-site thật?
8. **Cổng thời-điểm E20**: "nền vững" = E21 integration xong, hay cả cụm P4 (E12/E13/E14) done?
