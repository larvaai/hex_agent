---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Discovery Brief — E21 Realtime Control Plane (v1 spine, tiered)

**Date:** 2026-06-26
**Status:** draft

---

## 1. Problem framing

Vòng lặp đa-agent (Agent O + worker, E10) chạy "kín": người dùng không thấy O đang gọi ai, ai pending/running, và không can thiệp được giữa chừng một cách an toàn. UI hiện chỉ quan sát (polling-diff snapshot), không kênh điều khiển, không contract chuẩn cho event/command, không redaction, không audit. E21 là lớp hợp nhất E16 (review gate) + E17 (live control) + E18 (UI) cộng phần contract/observability còn thiếu.

**Root cause (đã verify):** tầng hợp đồng `control/` (Phase A) đã có nhưng **chưa được nối vào runtime thật** — emitter mặc định `None` và không nơi nào ngoài test dựng nó; Redactor + RuntimeCheckpoint là dead code trên đường chạy. Tức "control plane" hiện là *facade*.
**Current impact:** chưa ai điều khiển/quan sát được run thật; nếu xây tiếp UI lên facade này thì rò secret (redaction inert) và approval-gate không cưỡng chế (tool nguy hiểm chạy không cổng).
**Deadline / urgency:** không có deadline cứng; đây là epic nền P4. Ưu tiên là *cắt một lát mỏng chạy được* trước khi mở rộng bề mặt.

---

## 2. Hard constraints

| Constraint | Type | Notes |
|---|---|---|
| **Wait-only** ở v1 — KHÔNG cancel giữa generation; lệnh áp tại checkpoint kế | decision (đã chốt phiên discover) | gỡ refactor sync→async; Stop-now/token-stream sang T2 |
| **Right-size hạ tầng**: SQLite/JSONL/in-process EventBus đặt sau Port; KHÔNG Kafka/Redis/Postgres/WebSocket ở v1 | decision (đã chốt, PRD) | contract giữ nguyên, chỉ transport/storage là T2 |
| Execution model **đồng bộ blocking** | technical | `delegate()` blocking [supervisor/graph.py:175](../../supervisor/graph.py); `call_llm` không stream [llm/adapter.py:67](../../llm/adapter.py) |
| Local, đơn tiến trình, một người dùng | technical | concurrency thu về producer/consumer qua SQLite (HTTP thread ghi command, loop thread đọc ở checkpoint) |
| Hợp đồng S-CONTRACT (S21.1–S21.7) **đã tồn tại** trong `control/` | technical | tái dùng, không viết lại |
| Mỗi AC (Given/When/Then) → ≥1 test trong E19 (`tests/` + `tests_audit/`) | policy | DoD epic |
| `core/supervisor` không import trực tiếp transport/storage (phải sau Port) | policy | DoD file 00 §6 |
| Markdown chỉ trong `plans/` hoặc `docs/` | policy | CI invariant |

---

## 3. Evidence summary

**Research report:** `/Users/uspro/Desktop/Namson/hex_agent/plans/reports/worstcase-feasibility-260626-0037-e21-control-plane-report.md`
**Bổ trợ:** `/Users/uspro/Desktop/Namson/hex_agent/plans/reports/architecture-map-260625-2009-hex-agent-report.md`

Phát hiện chính (đã verify đối kháng, 39 agent, 32 candidate → 10 sống sót + 3 critic):
- **Tính năng bạn muốn KHẢ THI** — và hai cái duy nhất không khả thi gọn trong v1 (Stop-now, token-stream) đúng là hai cái đã tự cắt. Đường ranh khả thi = "sống trên biên turn" (đồng bộ) vs "phải chui vào trong turn" (async).
- **Control plane là facade chưa nối** (SEC-02/SEC-03/LIVE-3): emitter `None` mặc định [supervisor/graph.py:47](../../supervisor/graph.py); Redactor inert → tool args/error rò ra `events.jsonl`+SSE; approval-checkpoint trơ, không executor trong `_drive`.
- **4 căn bệnh gốc** (nhiều bản sao sự thật, không reconcile): (1) bus nuốt lỗi sink → audit hole im lặng [core/events.py:27](../../core/events.py); (2) resume tách state/log/danh-tính, đẻ seq+trace mới → đâm nhau, cộng dồn mỗi crash; (3) sink fan-out đồng bộ không timeout → treo vô hình; (4) `event_type` namespace mở xuyên 5 registry, không chủ → desync mỗi feature.
- **Happy-path bình thường ỔN.** 4 bệnh cắn đúng 3 chế độ: crash+resume, lỗi IO, thêm feature theo thời gian — tức chế độ "phát triển lên", đúng nỗi sợ rối tung.
- **13 phát hiện = 4 nhát chặn gốc**, không phải 13 việc rời (xem report §4).

---

## 4. Option space

| # | Approach | Pros | Cons | Complexity |
|---|---|---|---|---|
| A | **Thin spine trước** — T1 = observe + Wait-command + approval-gate (chỉ "xem + duyệt"), nối redaction; T1.5 breadth; T2 async | Ship được sớm thứ chạy thật; ép cắt 52-story; trị facade ngay phần UI chạm tới | Hoãn add-agent/edit-permission sang T1.5 (chưa "điều khiển đầy đủ" ở lần ship đầu) | medium |
| B | **Backend-standardization-first** — làm trọn B1–B11 rồi mới UI | Đúng "đừng bắt đầu bằng UI"; nền chắc | Lâu thấy giá trị; dễ "xây contract mãi không ra UI"; B10/B11 đã cắt nên B1–B9 là đủ rồi | medium-high |
| C | **Full breadth** — bám 52 story + 20-feature map | Phủ trọn PRD Control Tower | Mâu thuẫn "MVP dễ nhất"; coupling tổ-hợp (Bệnh 4) nổ sớm | high |

---

## 5. Chosen direction + rationale

**Chosen direction:** Option A — **Thin spine trước, phân tuyến T1/T1.5/T2.**

Tier (chi tiết bản đồ ở report §1):
- **T1 — spine v1 (observe + Wait + approval, đồng bộ):** B1 envelope, B2 snapshot, B3 command-queue+idempotency, B4 intervention/approval-drain + timeout, B6 redaction (**nối + allowlist**), B8 audit, B9 authz; transport `POST /api/commands` + SSE redacted + `GET /api/snapshot`; UI Graph + Timeline + Inspector + Approval-modal. → ship được "xem + duyệt".
- **T1.5 — breadth (vẫn đồng bộ):** B5 permission-store + Permission Editor, B7 add-agent-qua-O + edit-instruction, Replay, Causal "vì sao X", instrumentation breadth (S21.27–31), artifact versioning. Kèm **3 nhát chặn gốc còn lại** (durability fail-closed, resume-identity, derived-metrics/event-descriptor).
- **T2 — async + phân tán:** B10 Stop-now, B11 token-stream; adapter Kafka/Redis/Postgres/WebSocket sau Port.

**Why:**
1. **Khả thi đã được chứng minh khớp với đường ranh đồng bộ.** Mọi thứ T1/T1.5 sống trên biên turn → loop đồng bộ làm gọn; chỉ T2 cần async. Cắt theo đường ranh tự nhiên của kiến trúc, không cưỡng ép.
2. **Trị facade ở đúng nơi UI chạm tới.** Spine bắt buộc nối redaction (B6) + drain checkpoint (B4) — nếu không, UI hiện event = rò secret + badge "approve" nói dối. Thà cắt nhỏ mà thật.
3. **Hợp đồng đã có** (Phase A) → T1 phần lớn là *nối dây + vài store mới*, không phát minh kiến trúc. Rủi ro thấp.
4. **Ép kỷ luật chống rối tung từ sớm** thay vì để 52-story coupling nổ (Option C).

**Accepted trade-off:**
- Lần ship đầu chỉ "xem + duyệt", chưa kéo-thả agent/sửa quyền (sang T1.5) — vì add-agent (B7) + permission-store (B5) là cơ-bắp-backend mới, nặng hơn spine, và không chặn giá trị "quan sát + approve" đầu tiên.
- 3/4 nhát chặn gốc (durability, resume-identity, derived-metrics) để T1.5 — vì chúng chỉ cắn khi crash/IO-fault/tăng-feature, không chặn happy-path T1; **nhưng phải flag là nợ có ý thức**, không quên.

**DEC recorded:** none yet — hai quyết định nền (Wait-only; right-size sau Port) là architecture-level, **nên ghi DEC** qua `harness/scripts/decision_register.py` trước/trong hs:plan (xem Open questions).

---

## 6. Open questions

- [ ] B2 `control/snapshot.py` có merge vào main không, hay dựng lại? (hiện chỉ trên feature branch)
- [ ] 4 nhát chặn gốc: cái nào T1, cái nào T1.5? (đề xuất: chỉ B6-redaction là T1 bắt buộc; durability/resume-identity/derived-metrics → T1.5 nhưng flag nợ)
- [ ] `idempotency_key` ai sinh (UI hay server), scope per-session hay global?
- [ ] `auto_approve` cho checkpoint `risk=low`: mặc định bật hay tắt?
- [ ] Token `POST /api/commands`: per-session sinh lúc start run, hay chỉ same-origin guard cho v1 local?
- [ ] Ring-buffer SSE giữ tối đa bao nhiêu event/session trước khi fallback đọc JSONL?
- [ ] Lane phân tách lệnh (runtime-enforced vs O-mediated) — chốt ở plan: Pause/Approve/Permission = Lane A (tất định); AddAgent/EditInstruction = Lane B (qua O)?
- [ ] Có ghi 2 DEC (Wait-only; right-size-sau-Port) trước khi cook không?

---

## 7. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Xây UI lên facade chưa nối → rò secret + approval giả | high (nếu bỏ qua) | high (lộ secret, hành động nguy hiểm không cổng) | B6 redaction + B4 drain là **điều kiện T1**, không phải tuỳ chọn |
| Resume cộng dồn seq/trace đâm nhau → timeline rối tung | medium (mỗi crash+resume) | high (mất khả năng audit theo thời gian) | nhát chặn #3 (resume-identity) — flag T1.5, làm trước breadth |
| Bus nuốt lỗi sink → audit hole im lặng | low-medium (cần IO-fault) | high (un-auditable, không ai biết) | nhát chặn #1 (durable fail-closed) — T1.5 |
| Namespace event desync khi thêm feature | medium (tăng theo số story) | medium-high (rối tung cấu trúc) | nhát chặn #4 (event-descriptor + boot assertion) — T1.5, trước khi mở breadth |
| Approval-checkpoint không expiry → treo loop đồng bộ | medium | high (run chết, phải kill process) | thêm field `deadline`/`expiry` + auto `expired→reject` — trong B4 (T1) |
| Scope creep ngược về 52-story | medium | medium | brief này chốt tier; mọi thứ ngoài T1 vào BACKLOG, không phình spine |

---

## 8. Explicitly OUT of scope

- **Stop-now** (cancel giữa generation) — cần B10 async. → T2.
- **Token streaming / cửa sổ Stream** — cần B11 async-ish, đụng hot path adapter. → T2.
- **Kafka / Redis / Postgres / outbox / WebSocket** — sau Port, multi-node. → T2.
- **Multi-user RBAC đầy đủ** — v1 chỉ authz tối thiểu cho kênh mutate.
- **Logic sinh plan/proposal** (E13/E15) — E21 chỉ review/điều khiển, không sinh.
- **Logic work-management** (E13/E14) — E21 chỉ phát event + link `task_id`.
- **Soi sâu cách build từng mảnh backend** — brief này chỉ tới mức "dựa lên cái gì"; thiết kế chi tiết backend là việc của hs:plan.

_(Mọi thứ không liệt kê ở đây là chưa quyết, không phải đã duyệt.)_

---

## Handoff -> hs:plan

Brief này là input cho `hs:plan`. Khi gọi:
```
/hs:plan /Users/uspro/Desktop/Namson/hex_agent/plans/260626-0037-e21-control-plane-v1/discovery-brief.md
```
**Nhớ `/clear` trước** để tránh bias mang sẵn từ discovery/critique (`harness/rules/workflow-handoffs.md` #5). Đề xuất phạm vi plan đầu tiên: **chỉ T1 spine** (B1–B4,B6,B8,B9 + transport + UI Graph/Timeline/Inspector/Approval), để T1.5/T2 thành plan kế.
