---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Discovery Brief — Drag-drop UI thành thật (authoring half) + LangChain bakeoff

**Date:** 2026-06-26
**Status:** finalized

---

## 1. Problem framing

Muốn `drag_from_zero` có **UI kéo-thả agent thật** + xem process chi tiết, và thử hướng **langchain**. Scout lộ ra khoảng cách giữa hình dung và thực tế trên đĩa:

- **Process-view (Đồ thị 2) ĐÃ chạy** end-to-end — Slice 6a: `server.py` stream execution-tree qua WS, browser-verified ([README:199-202](../../drag_from_zero/README.md)).
- **Authoring (Đồ thị 1) chưa có một dòng nào** ở cả hai phía. Server chỉ phục vụ **một run đúc sẵn read-only** (`App.runs = {one default}`, builder hard-code, `project-data.js` = project giả "taskflow"); REST không có endpoint tạo/sửa topology hay roster ([server.py:258-273, 325-359](../../drag_from_zero/dragzero/server.py)). `join_agent` (mid-run injection, Slice 3a) **có trong runtime nhưng không expose endpoint**. UI thật là **dc-runtime** (`x-dc`/React qua `window.React`), `support.js` *generated từ `dc-runtime/src/*.ts` không có trong repo* — **không phải React Flow**; grep `drag|drop|topology` trong HTML = 0 hit.

Tóm: "làm UI kéo-thả thành thật" = **xây nửa authoring** (chưa tồn tại), không phải nối nốt một UI gần xong.

**Root cause:** Slice 1→6a build "truth-first" đúng kỷ luật — runtime + event model + live-view; authoring (Đồ thị 1) cố tình hoãn tới sau. Giờ tới lượt nó.
**Current impact:** Không kéo-thả được agent; không inject giữa phiên từ UI; demo chỉ chạy 1 kịch bản cứng.
**Deadline / urgency:** Không có; đây là experiment slice.

---

## 2. Hard constraints

| Constraint | Type | Notes |
|---|---|---|
| Python core + TS UI, nối qua event stream | technical | Khóa từ session trước (Stack Q1) |
| Substrate hiện tại = **event-sourced**, event log là source-of-truth | technical | UI/eval/CLI đều là projection của log (`read_model.reduce`) |
| Backend hiện **zero external dep** (stdlib `http.server` + WS hand-rolled) | policy | Bakeoff langchain/langgraph sẽ phá invariant này — đó là cái giá đang đo |
| `drag_from_zero` = project chính, **commit standalone vào repo này** | policy | Q3; hex_agent cũ chỉ còn là prior-art |
| Không regress Slice 6a (live-view + WS + 8a invariants) | technical | Core untouched; chỉ thêm endpoint/adapter |
| `mu`/`done_when` đang **stub** (verifier = Slice 6b, plan riêng) | technical | Authoring UI **không được** phụ thuộc verdict thật |
| Single-user / 1-process / local | technical | Không authz/multi-tenant (DEC-11 context) |

---

## 3. Evidence summary

**Research report:** [SKIPPED — chain nén] · nền bằng chứng = 3 prior-art report đã có (research+brainstorm coi như đã chạy; trích dẫn thay vì re-derive, theo lệnh token-efficiency):
- [codebase-map-260626-2229-drag-from-zero](../reports/codebase-map-260626-2229-drag-from-zero-report.md) — bản đồ runtime + danh sách gap.
- [design-260626-1502-drag-drop-composition-layer](../reports/design-260626-1502-drag-drop-composition-layer-report.md) — idiom config-driven composition + invariant chịu lực.
- [brainstorm-260626-1615-greenfield-dragdrop-engine](../reports/brainstorm-260626-1615-greenfield-dragdrop-engine-report.md) — DEC-11, substrate build-vs-rent.

Key findings:
- **Boundary đã gần sẵn, chỉ chưa expose.** Slice 5 (`topology.py`) làm Đồ thị 1 thành JSON round-trip + `validate()`; Slice 3a cho `join_agent()` pause→inject→resume thật. Thiếu = **REST/WS surface** để UI đọc-ghi chúng.
- **dc-runtime là cục nợ ẩn.** UI live-view chạy nhưng source build (`dc-runtime/src/*.ts`) không có trong repo → mở rộng tại chỗ khó; React Flow (lời hứa session trước) = vapor.
- **DEC-11 đang bị lật ngầm.** DEC-11 chốt *generic n8n-builder, bỏ event-sourcing, THUÊ Burr*. 3 câu trả lời vừa rồi chọn `drag_from_zero` (event-sourced, tự xây) → ngược DEC-11. LangChain-bakeoff = **mở lại câu hỏi substrate** DEC-11 đã đóng bằng "Burr". Substrate table của DEC-11 **không có** langchain/langgraph → đó là lỗ hổng bakeoff phải lấp.
- **3 vòng đời state** (per-run / conversation-ledger / display-stream) là footgun chí mạng nếu sau này thêm chat/turn — gộp = budget bleed + mất history khi resume ([brainstorm:60-65](../reports/brainstorm-260626-1615-greenfield-dragdrop-engine-report.md)). Ghi sẵn cho plan.

---

## 4. Option space

Hướng lớn đã khóa bởi 3 câu trả lời (UI-first · bakeoff · standalone). Option-space = **cách thực thi**, tách 2 trục độc lập.

### Trục 1 — Frontend cho authoring canvas (critical path của "UI thật")

| # | Approach | Pros | Cons | Complexity |
|---|---|---|---|---|
| A | Mở rộng dc-runtime tại chỗ (thêm panel kéo-thả vào `Agent IDE.dc.html`) | Reuse live-view + WS đang chạy; zero build-toolchain | **Source dc-runtime không có trong repo** → không rebuild sạch; không phải React Flow; canvas tự chế | high (ngược dòng) |
| B ✅ | **React Flow app mới** ăn cùng boundary backend | Canvas kéo-thả thật, đúng requirement; React Flow là đúng tool cho node-graph; FE/BE tách sạch | Thêm Vite/TS toolchain + LOC; cầu sang WS stdlib | medium |
| C | Fork canvas platform (Flowise/Langflow) | Canvas free | DEC-11 đã loại (UI-lock/license, abstraction lệch) | high |

### Trục 2 — Substrate orchestrator (langchain question = bakeoff, OFF critical path)

| # | Candidate | Vai trò trong bakeoff |
|---|---|---|
| Z ✅ | **Zero-dep hiện tại** (baseline, đang thắng mặc định) | Đã thỏa boundary + mid-run injection; burden of proof nằm ở kẻ thách thức |
| L | **LangGraph** orchestrator sau cùng boundary | Đo: StateGraph compiled có nhận inject giữa phiên sạch không (giả thuyết: KHÔNG — đúng lý do zero-dep ra đời) |
| Bu | **Burr** (DEC-11 đã nominate) | Tái dùng phân tích DEC-11 thay vì relitigate; cyclic-FSM + SQLite persist |

---

## 5. Chosen direction + rationale

**Chọn:** **B (React Flow) trên một API-boundary substrate-agnostic**, langchain xử lý bằng **bakeoff Z·L·Bu — phase cuối của CÙNG một plan** (gộp, không tách spike riêng).

Trình tự (phase trong 1 plan, bakeoff đứng cuối nên UI không chờ nó):
1. **Khóa API boundary** (substrate-agnostic): `topology-in` / `roster-mutate` / `event-stream-out` / `join-mid-run`. Phần lớn = expose cái Slice 5 + Slice 3a **đã làm**, qua endpoint mới trên `server.py` (`GET/POST /api/topology`, `POST /api/runs` từ topology, `POST /api/runs/{id}/join`). Core untouched.
2. **Xây React Flow authoring canvas** ăn boundary đó → đây là "UI thật". Kéo agent/tool/router → topology JSON → POST → run → xem Đồ thị 2 stream (đã có) → inject role thiếu giữa lúc parked.
3. **Bakeoff** (phase cuối, sau khi UI slice xanh): cài cùng boundary bằng L (LangGraph) và Bu (Burr), chạy **kịch bản chuẩn** (root→plan→delegate role-trống→`task_waiting`→inject→resume→child done), quyết bằng số. Tách thành phase riêng để không nhiễm critical-path của UI.

**Why:**
1. **Boundary-first cho UI không chờ bakeoff.** Zero-dep đang thỏa boundary và chạy → UI build ngay; bakeoff chỉ trả lời "có bao giờ thay orchestrator không", không chặn.
2. **React Flow là đúng tool** cho node-graph kéo-thả; dc-runtime thiếu source nên mở rộng tại chỗ là ngược dòng.
3. **Ports-and-adapters đã sẵn** — LLM port, Tool port, topology-as-data. Thêm "orchestrator sau boundary" là cùng kỷ luật; bakeoff = swap adapter, không đụng UI.
4. **Burden of proof đặt đúng chỗ:** langchain phải **thắng** baseline ở trục mid-run-injection + observability, không chỉ ngang bằng. Đúng tinh thần verified-work-per-token.

**Accepted trade-off:**
- Thêm Vite/TS toolchain (phá "single static file") vì React Flow đáng giá cho canvas thật.
- Bakeoff tốn token để có thể kết luận "zero-dep vẫn thắng, không thay" — chấp nhận, vì đó là cách đóng vĩnh viễn câu hỏi langchain thay vì để nó ám.

**DEC recorded:** chưa — brief này **lật/sửa DEC-11**. Đề xuất register một DEC mới (hoặc `--append-alloc` vào DEC-11) lúc/sau khi plan chốt substrate. Không tự ghi vì `docs/decisions.md` là file commit.

---

## 6. Open questions

- [ ] **FE seam:** React Flow app riêng (B) — confirm bỏ hẳn dc-runtime cho authoring, hay giữ dc-runtime cho live-view + bolt React Flow cho canvas? (blocking cho UI slice)
- [ ] **Canvas-contract:** React Flow export JSON == `topology.json` luôn, hay 1 canvas-format compile sang topology spec? ([brainstorm:85](../reports/brainstorm-260626-1615-greenfield-dragdrop-engine-report.md))
- [ ] **Mid-run join UX:** UI biểu diễn "inject agent cho role X khi parked" thế nào? WS cần frame báo "parked, waiting role X" (hiện chỉ có `block` chung). Endpoint `POST /api/runs/{id}/join {agent}` → `_wake_waiting`.
- [ ] **Bakeoff scope:** đã chốt gồm Burr (Z·L·Bu). Cần research nhẹ lấp lỗ langchain/langgraph trong substrate table DEC-11 (local? license? headless? mid-run mutation?) trước phase bakeoff.
- [ ] **Multi-run:** authoring tạo run mới mỗi topology → `App.runs` đã là dict (có chỗ), nhưng builder đang hard-code 1 — cần factory từ posted topology.
- [ ] **LangChain entry-point:** Q1=bakeoff frame **orchestrator-swap**, không phải adapter-behind-port (Q1 option a user KHÔNG chọn). Confirm bakeoff so substrate điều phối, không phải chỉ LLM adapter.

---

## 7. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| "UI thật" phình âm thầm thành cả React Flow app + backend CRUD + gỡ dc-runtime | high | trượt slice | Vertical slice: 1 topology, author→run→observe→inject, trước mọi polish |
| Bakeoff tràn vào critical path / relitigate DEC-11 mãi | medium | đốt token vô định | Bakeoff = phase CUỐI plan (chỉ chạy sau UI slice xanh), time-box, PASS-criteria đo được |
| dc-runtime source thiếu → kẹt nếu chọn mở rộng tại chỗ | medium | rework | Chốt FE = B (app mới) sớm, đừng cố sửa support.js generated |
| langchain/langgraph chưa đo trên trục local/headless/mid-run | medium | bakeoff thiếu cơ sở | Research nhẹ lấp substrate table trước phase bakeoff |
| Gộp 3 vòng đời state khi thêm chat/turn sau | low (chưa tới) | murder-to-undo | Ghi invariant vào plan: ledger ngoài graph, reset per-run, display ephemeral |
| Authoring lệ thuộc verdict thật (mu/done_when stub) | medium | UI hiện sai trạng thái | UI tolerate stub; verdict thật = Slice 6b plan riêng |

---

## 8. Explicitly OUT of scope

- **Slice 6b verifier** (μ thật + `done_when` + verdict có evidence) — plan riêng đã approved: [`plans/260626-1528-decompose-agent-recursion-slice/`](../260626-1528-decompose-agent-recursion-slice/plan.md) (package `decompose_agent`). UI chỉ cần tolerate stub.
- **Generic n8n-style workflow builder** (DEC-11 vision) — không theo; `drag_from_zero` là domain multi-agent, không domain-agnostic.
- **Thay orchestrator** trước khi bakeoff ra số — baseline zero-dep giữ nguyên tới khi có bằng chứng.
- **Multi-user / authz / remote / persistence cross-session** — single-user-local.
- **Plugin sandbox / trust model** cho community node-pack — defer.
- **Schema migration** cho saved topology — defer (sẽ cần khi user tích flow trên đĩa; ghi nợ).
- **Adapter-behind-port langchain** (Q1 option a) — user chọn bakeoff orchestrator-swap, không phải nhét langchain làm LLM adapter.

_(Mọi thứ không liệt kê ở đây là chưa quyết, không phải đã duyệt.)_

---

## Handoff -> hs:plan

Brief này là input cho `hs:plan` → **1 plan gộp**, phase order: (1) khóa API boundary → (2) React Flow authoring canvas → (3) wire mid-run join → (4) bakeoff Z·L·Bu. Bakeoff đứng cuối nên UI không chờ; DEC lật-DEC-11 register trong/sau plan.
```
/hs:plan plans/260626-2329-dragdrop-ui-real-langchain-bakeoff/discovery-brief.md
```
**Nhớ `/clear` trước khi plan** — discovery carry-context lệch planning ([workflow-handoffs #5](../../harness/rules/workflow-handoffs.md)).
