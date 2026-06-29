---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Discovery Brief — Giáo trình "xây quốc gia" để hiểu luồng `core_agent`

**Date:** 2026-06-26
**Status:** finalized

---

## 1. Problem framing

Người học (chủ project, junior) **không lần được luồng chạy** của codebase: kernel, session,
kernel session, delegation, loop, gate, kiểm tra state, hook (before/after) — tất cả cảm giác
dính chùm vào nhau. Thực tế: **lõi rất nhỏ** (1 cánh cửa + 5 class), nhưng **6 lớp epic xếp chồng
quanh nó** che mất cái lõi, nên ai nhìn vào cũng thấy "rối rắm".

Cần một **hành trình học progressive**: bắt đầu từ nhu cầu cơ bản nhất → sinh ra kernel + execute_tool
→ gặp vấn đề → sinh thêm từng class/method/helper để giải. Class/logic quá khó được tách thành
"lát cắt" (slice) giải riêng rồi mới ghép vào. Mỗi chặng có câu đố để người học tự nghĩ, giải xong
mới mô hình hoá bằng **HTML tương tác (khối + mũi tên chuyển động)**. Cuối cùng đúc kết thành 1 skill.

**Root cause:** chưa có tài liệu onboarding *theo trình tự nhu cầu*. Docs hiện có
(`docs/reference/runtime-flow.md`, `MAP.md`) mô tả *hiện trạng* tốt nhưng không *dạy từ số 0* — đọc
xong vẫn cần biết trước mới hiểu.
**Current impact:** chủ project không tự tin sửa/mở rộng vì không nắm luồng; mọi thay đổi đều rủi ro.
**Deadline / urgency:** không gấp; là khoản đầu tư hiểu hệ thống.

---

## 2. Hard constraints

| Constraint | Type | Notes |
|---|---|---|
| Sư phạm needs-driven: mỗi chương = 1 nhu cầu → 1 thứ ra đời | pedagogy | Không lôi class khó ra trước; khái quát trước, sâu sau |
| Class/logic khó → tách "slice" giải riêng, hiểu xong mới ghép | pedagogy | VD: middleware onion, path-jail, finish-gate, resume |
| Mỗi class chính phải giải thích **biến trong `__init__()`/dataclass fields** | pedagogy | Lập bảng từng biến: tên → vai trò. **Gồm cả field nội bộ** (`_frozen`/`_closed`/`_middlewares`) vì chúng kể vòng đời |
| Mỗi chương có **câu đố** trước, rồi mới lộ đáp án | pedagogy | Người học suy nghĩ trước khi xem hình |
| Trực quan hoá = **HTML/SVG/JS thuần** (khối + mũi tên chuyển động) | tech | **Không build step, không CDN**; 1 file self-contained/chương, mở browser là chạy. Animation = CSS/JS nhẹ |
| Bắt đầu bằng **toàn cảnh map** (Chương 0) rồi mới needs-driven | pedagogy | Quyết định của user (ngã rẽ #2) |
| Đầu ra cuối = **1 skill tái-tạo giáo trình cho codebase bất kỳ** | scope | **Generator**, không phải viewer (quyết định user); build sau khi nội dung repo này ổn — xem risk §7 |
| Markdown chỉ nằm trong `plans/` hoặc `docs/`; **HTML đặt trong `docs/explanation/learn/`** | policy | CI invariant — `harness/rules/documentation-management.md`; khớp nhánh Diátaxis đang restructure |
| Ngôn ngữ đầu ra: tiếng Việt (`harness/data/output.yaml` → `vi`); evidence (file:line) giữ nguyên | policy | Áp humanizer chống AI-tell |
| Bám code thật, không bịa; cite `file:line` | quality | Code là nguồn sự thật, không phải trí nhớ |

---

## 3. Evidence summary

**Research report:** [SKIPPED — đây là bài toán *hiểu codebase nội bộ*, không phải research ngoài.
Evidence = code + docs hiện có, cite trực tiếp bên dưới.]

Phát hiện chính (đã verify trực tiếp trên code):

- **Cả hệ thống đứng trên MỘT cánh cửa:** `AgentKernel.execute_tool` ([core/kernel.py:63](../../core/kernel.py)).
  *Mọi* hành động — kể cả gọi LLM (`llm.chat`) — đều đi qua đây; không có đường tắt
  ([docs/reference/runtime-flow.md:15-22](../../docs/reference/runtime-flow.md)).
- **Lõi chỉ là 5 thứ:** `AgentKernel`, `KernelSession`, `CapabilityRegistry`, `EventBus`,
  protocol `ToolMiddleware`. Mọi epic khác chỉ là *plugin cắm quanh 5 thứ này*.
- **Tách substrate vs per-run rất rạch ròi:** kernel **frozen + shared** (chỉ giữ registry/events/
  config/middlewares); state + vòng đời task thuộc `KernelSession`
  ([core/kernel.py:33-55](../../core/kernel.py), [core/session.py:49-57](../../core/session.py)).
- **"Hook / before_chat-after_chat" = middleware onion:** `ToolMiddleware(request, nxt)` bọc quanh
  chokepoint; đăng ký order ngoài→trong, bọc `reversed` ([core/middleware.py:11](../../core/middleware.py),
  [core/kernel.py:24-30,136-138](../../core/kernel.py)). Đây là **slice khó** — có cả bẫy late-binding closure.
- **HAI chokepoint tách biệt có chủ đích:** (1) `execute_tool` cho tool+LLM; (2)
  `DelegationServicePort.delegate` cho delegation — delegation **không** phải method của kernel, nên có
  node `delegate` riêng trong graph ([docs/reference/runtime-flow.md:15-36](../../docs/reference/runtime-flow.md)).
- **"Loop để chạy" nằm NGOÀI kernel:** graph (`orchestrator/loop.py`, `graph/runtime.py`,
  `graph/nodes.py`) gọi cửa lặp lại; topology `guard→agent→tool|delegate|finish|fail`
  ([docs/reference/runtime-flow.md:49-83](../../docs/reference/runtime-flow.md)).
- **Thứ tự build epic = thứ tự nhu cầu tự nhiên:** E01 kernel → E03 LLM → E02 discipline →
  E04 observability → E06 tools+safety → E05 loop → E07 skills → E08 RAG → E09 roles → E10 multi-agent
  → E21 control plane ([docs/roadmap/dependency-map.md:10-54](../../docs/roadmap/dependency-map.md)).
  **Đây chính là xương sống giáo trình.**
- **Delegation có rào an toàn:** scope con phải là **tập con** scope cha, empty set = "cấm tất"
  (không phải "kế thừa") ([core/session.py:160-164](../../core/session.py)) — slice khó.
- **Resume thật chạy trên SQLite**, `checkpoint.json` chỉ là projection cho UI
  ([docs/reference/runtime-flow.md:104-123](../../docs/reference/runtime-flow.md)) — slice capstone.
- **Rủi ro đã ghi nhận:** `tool.requested` log **raw args** vào `events.jsonl` → secret/PII có thể lọt
  ([docs/reference/runtime-flow.md:100-102](../../docs/reference/runtime-flow.md)). (Liên quan tới chương safety.)

---

## 4. Option space

Option space ở đây là **chiến lược sư phạm + hình dạng đầu ra** — đã được user chốt trực tiếp qua 2 ngã rẽ
(mạnh hơn brainstorm). Ghi lại trung thực để plan thấy đường đã loại:

| # | Approach | Pros | Cons | Complexity |
|---|---|---|---|---|
| A | **Spine-first** (5 class lõi trước, rồi mở rộng) | Vững gốc; nhẹ nhất | Chưa thấy "toàn cảnh", dễ mất phương hướng | low |
| B | **Map-first → needs-driven** (bản đồ trước, rồi xây dần theo nhu cầu) | Vừa có định hướng vừa hiểu sâu; khớp thứ tự epic | Dài hơn; cần kỷ luật giữ Chương 0 ở độ cao | medium |
| C | **Follow-one-flow** (bám 1 request end-to-end) | Rất "thật"; thấy mọi lớp một lần | Dễ nhảy cóc khái niệm; khó cho người chưa có nền | medium |

Hình dạng đầu ra (ngã rẽ #1): **"Theo đúng chuẩn discover"** — ra brief này trước (mục lục giáo trình),
rồi `/hs:plan` → `/hs:cook` build trọn bộ HTML + skill như một dự án có theo dõi. (Loại: "học ngay tại
terminal" và "lai brief-ngắn".)

---

## 5. Chosen direction + rationale

**Chosen direction:** **Option B — Map-first → needs-driven**, đầu ra theo chuẩn discover
(brief → plan → cook → skill).

**Why:**
1. User chốt trực tiếp cả 2 ngã rẽ — đây là quyết định của người học, không phải suy đoán.
2. Map-first (Chương 0) chống "lạc" — thấy quốc gia trước khi xây từng ngôi nhà; needs-driven (Chương 1→N)
   cho hiểu *tại sao* mỗi thứ tồn tại, không học vẹt.
3. Thứ tự epic E01→E21 đã là một dòng "nhu cầu → giải pháp" có sẵn trong repo
   ([docs/roadmap/dependency-map.md](../../docs/roadmap/dependency-map.md)) → giáo trình bám nó là khớp code 100%.
4. Slice technique trị đúng chỗ đau: mấy mảnh khó (middleware onion, path-jail, finish-gate, resume) được
   gỡ ra giải riêng thay vì nhồi vào dòng chính.

**Accepted trade-off:** Giáo trình dài (≈13 chương) và mỗi chương có HTML riêng → tốn công build; chấp
nhận vì mục tiêu là *hiểu thật*, không phải tóm tắt nhanh. Chương 0 phải giữ ở độ cao (không sa đà chi tiết)
— rủi ro kỷ luật, sẽ nêu ở §7.

**DEC recorded:** none — đây là quyết định sư phạm/tài liệu, không phải kiến trúc.

---

### 5b. Mục lục giáo trình (cốt lõi của brief — input trực tiếp cho hs:plan)

Mỗi chương theo cùng một **nhịp**: *Nhu cầu* → *Thứ ra đời* → *Bảng biến `__init__`* → *Câu đố* → *(slice nếu
khó)* → *HTML tương tác*. Cột "Epic" neo vào dependency-map để giữ thứ tự đúng.

| Ch. | Nhu cầu (đứa trẻ cảm nhận) | Thứ ra đời | Class/file chính | Slice khó | Epic |
|---|---|---|---|---|---|
| **0** | "Cho tôi xem cả quốc gia trước đã" | Bản đồ + 1 cánh cửa + 5 class lõi + 6 lớp quanh nó | `execute_tool` là tâm; 2 chokepoint | — | (toàn cảnh) |
| **1** | "Tôi ra lệnh, có thứ thi hành" | Kernel + execute_tool + Registry + envelope | `AgentKernel`, `CapabilityRegistry`, `ToolRequest`/`CapabilityResult` | deep_freeze config | E01 |
| **2** | "Mỗi lần chạy phải có bộ nhớ riêng" | Session + State + Factory + Identity | `KernelSession`, `StateStore`, `SessionFactory`, `SessionIdentity` | substrate vs per-run | E01 |
| **3** | "Cài hành vi quanh cửa mà không sửa cửa" | Middleware (hook before/after) | `ToolMiddleware`, `use()`, `_wrap`+`reversed` | **onion + late-binding closure** | E01/E06 |
| **4** | "Cho LLM nói chuyện được" | LLM là một capability | `features/llm_chat.py`, `llm/adapter.py` | — | E03 |
| **5** | "LLM trả rác / lặp / báo xong khi chưa xong" | Discipline gates | `json_gate`, `budget`, `finish_gate` | **finish-gate logic** | E02 |
| **6** | "Tôi không thấy chuyện gì đã xảy ra" | Observability | `EventBus`, `EventLogger`, `inspect` CLI | lineage fields | E04 |
| **7** | "Cho đụng file/terminal thật, nhưng an toàn" | Toolbox + Safety | `toolbox/*`, `SafeToolPort`, `PolicyGate` | **path-jail (sandbox)** | E06 |
| **8** | "Ai bấm chuông cửa lặp đi lặp lại?" | Loop / Graph (NGOÀI kernel) | `orchestrator/loop.py`, `graph/runtime.py`, `graph/nodes.py` | topology guard→agent→… | E05 |
| **9** | "Giao việc cho đứa con, phạm vi hẹp hơn" | Delegation (chokepoint #2) | `SessionFactory.create_child`, `delegation/manager.py` | **scope ⊆ parent** | E09 |
| **10** | "Một đội nhiều agent + người điều phối/phán xử" | Roles + Supervisor multi-agent | `roles/*`, `supervisor/orchestrator.py`, `broker`, blackboard | Agent O + blackboard | E09/E10 |
| **11** | "Người thật ngồi xem, can thiệp realtime" | Control plane | `control/*` (events, emitter, commands, checkpoint, permission, redaction) | redaction boundary | E21 |
| **12** | "Lỡ sập giữa chừng thì chạy tiếp thế nào?" | Resume + persistence (capstone) | `orchestrator/checkpoint.py`, SQLite vs `checkpoint.json` | **resume = SQLite truth** | E05+ |
| **★** | "Lần sau gặp repo lạ cũng hiểu nhanh" | 1 skill **tái-tạo giáo trình cho codebase bất kỳ** (generator) | (skill mới trong harness) | quét code → suy nhu cầu → sinh HTML | meta |

> Chương 8 và 12 nên dùng lại trực tiếp [docs/reference/runtime-flow.md](../../docs/reference/runtime-flow.md)
> làm nguồn — nó đã verify trên code.

---

## 6. Decisions + open questions

**Đã chốt (user, 2026-06-26):**

- ✅ **HTML tech** = HTML/SVG/JS thuần, không build step, không CDN — 1 file self-contained/chương.
- ✅ **Vị trí** = `docs/explanation/learn/` (khớp nhánh Diátaxis đang restructure).
- ✅ **Nhịp build** = cook Chương 0–3 trước (lõi), chốt template + lấy feedback, rồi nhân bản 4–12.
- ✅ **Skill cuối** = **generator** (tái-tạo giáo trình cho codebase bất kỳ), không phải viewer.
- ✅ **Độ sâu `__init__`** = gồm cả field nội bộ (`_frozen`/`_closed`/`_middlewares`).

**Còn mở (do quyết định "generator" mở ra — trả lời khi plan tới phần ★):**

- [ ] **Generator quét bằng gì?** Heuristic tĩnh (AST/regex tìm class + `__init__`) hay LLM-driven
      (đọc code → tự suy "nhu cầu")? Heuristic = rẻ/đoán-được; LLM = linh hoạt nhưng tốn token + rủi ro bịa.
- [ ] **Generator đỡ ngôn ngữ nào?** Chỉ Python (như repo này) hay đa ngôn ngữ? Đề xuất: Python trước, mở rộng sau.
- [ ] **Generator suy "thứ tự nhu cầu" thế nào** khi repo lạ KHÔNG có sẵn dependency-map như repo này?
      (Đây là phần khó nhất của generator — repo này "may mắn" có `docs/roadmap/dependency-map.md`.)

---

## 7. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Chương 0 sa đà chi tiết → mất tác dụng "định hướng" | medium | high | Giới hạn Chương 0 ở mức khối + mũi tên; cấm nhắc tên biến |
| 13 HTML build xong mới phát hiện sai format/gu | medium | high | Cook 0–3 trước, chốt template HTML rồi nhân bản |
| Code đổi → giáo trình lệch (drift) | medium | medium | Cite `file:line`; chương 8/12 trỏ về `runtime-flow.md`; thêm note "verify lại nếu sửa file X" |
| Slice khó (onion/closure, path-jail) giải hụt → hiểu sai bản chất | medium | high | Mỗi slice có câu đố + ví dụ chạy được (snippet tối giản) trước khi ghép |
| Scope phình: thêm epic tương lai (E11–E14) vào giáo trình | low | medium | Khoá ở 11 lớp đã có code; epic park-with-trigger → BACKLOG, không vào giáo trình |
| HTML "đẹp nhưng sai" (AI-slop visual) | low | medium | Visual phải khớp evidence; review bằng `hs-viz` guideline |
| **Skill generator phình to / over-engineer** — "tái-tạo cho repo bất kỳ" là bài toán mở, dễ thành dự án riêng | high | high | Build generator **chỉ sau** khi giáo trình repo này xong; phase ★ tách hẳn, có thể tự thành discovery riêng. Generator v1 chỉ Python + heuristic, không LLM |
| Generator suy sai "nhu cầu" trên repo lạ (không có dependency-map) | medium | high | v1 yêu cầu repo có file build-order/map; repo thiếu thì fallback "spine-first" thay vì đoán bừa |

---

## 8. Explicitly OUT of scope

- **Không** viết/sửa code runtime của `core_agent` — đây là tài liệu học, không đụng logic.
- **Không** dạy epic *chưa có code* (E11 Departments, E12 Router, E13 Factory, E14 Ledger — đang
  park-with-trigger, xem [dependency-map.md:82-95](../../docs/roadmap/dependency-map.md)).
- **Không** đi sâu RAG/Qdrant infra (E08) quá mức 1 chương khái quát — nó là nhánh phụ, không nằm trên
  đường găng hiểu luồng.
- **Không** build skill generator (★) *trong* thread plan đầu — chỉ sau khi giáo trình repo này ổn; phase ★
  tách hẳn (có thể cần discovery riêng vì "generator cho repo bất kỳ" là bài toán mở).
- **Không** thay thế `docs/reference/runtime-flow.md` — giáo trình *bổ sung* (dạy từ 0), không trùng lặp.

_(Mọi thứ không liệt kê ở đây là chưa quyết, không phải đã duyệt.)_

---

## Handoff -> hs:plan

Brief này là input cho `hs:plan`. Khi gọi plan:
```
/hs:plan /Users/uspro/Desktop/Namson/hex_agent/plans/260626-0143-project-flow-explainer/discovery-brief.md
```
**Nhớ `/clear` trước** để tránh context discovery làm lệch planning
(`harness/rules/workflow-handoffs.md` #5).
