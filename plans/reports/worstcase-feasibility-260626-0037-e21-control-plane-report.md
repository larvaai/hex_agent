---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# E21 Realtime Control Plane — Worst-case + Feasibility (evidence report)

**Ngày:** 2026-06-26 · **Nhánh:** main @ `593a931` · **Nguồn:** đối chiếu docs `docs/rebuild_from_zero/E21_realtime_control_plane/` với code thật + một vòng săn worst-case đa-agent (39 agent, 32 candidate → 10 sống sót verify + 3 critic moi thêm).

> Báo cáo này là *bằng chứng bền* cho `discovery-brief.md`. Evidence (file:line) giữ nguyên văn, không dịch.

---

## 0. Trạng thái triển khai thật (không phải docs nói)

| Phần | Trạng thái | Bằng chứng |
|---|---|---|
| Phase A · S-CONTRACT (S21.1–S21.7) | ✅ có trong `control/` | `control/{events,commands,checkpoint,permission,redaction,event_registry,command_registry,emitter,ports}.py` + `config/runtime_{event,command}_types.yaml` |
| Phase B · B1 EventEmitter | ✅ code có | `control/emitter.py` |
| Phase B · B2 snapshot projection | ⚠️ **trên feature branch, KHÔNG trong main** | agent verify: `find . -name snapshot.py` → không có trong working tree main |
| B3–B11, transport, UI, reliability | ❌ chưa | — |
| **Hợp đồng `control/` được NỐI vào runtime thật** | ❌ **chưa nối** — facade | xem §2 (SEC-02/SEC-03/LIVE-3) |

---

## 1. Bản đồ khả thi (feasibility) + tier

Ký hiệu: ✅ khả thi v1 đồng bộ, hợp đồng có sẵn, chỉ cần nối · ⚠️ khả thi nhưng cần mảnh backend chưa có (store mới / phải nối) · ⛔ cần async (đã hoãn).

**Nguyên lý phân tuyến:** loop đồng bộ dừng tự nhiên ở **biên giữa các turn**. Tính năng nào sống trên biên (đọc state · xếp lệnh · áp tại điểm dừng · ghi log) → khả thi đồng bộ. Tính năng nào phải thò vào GIỮA một turn đang chạy (huỷ generation, stream token) → cần async → để sau.

| Năng lực | Tính năng | Khả thi | Backend dựa lên | Tier |
|---|---|---|---|---|
| Observe | Agent Graph (status sống/agent) | ✅ | B2 snapshot + B1 + ~4 event status | T1 |
| Observe | Event Timeline | ✅ | B1 + SSE (JSONL đã có) | T1 |
| Observe | Agent Inspector | ✅ | B2 + B6 redaction | T1 |
| Observe | AC status passed/missing/failed | ✅ | B2 (`acceptance_checks` đã có) | T1 |
| Command | `POST /api/commands` + authz | ✅ | B3 queue+idempotency + B9 | T1 |
| Command | Pause / Resume | ✅ | B3 + B4 | T1 |
| Command | Approve / Reject checkpoint | ⚠️ | B4 — executor chưa nối + timeout | T1 |
| Command | Kéo-thả thêm agent | ✅ | B7 `pending_human_commands`→O | T1.5 |
| Command | Sửa instruction / system prompt | ✅ | B7 (O-mediated, áp ở checkpoint) | T1.5 |
| Command | Sửa quyền agent | ⚠️ | B5 permission store mới (`effective_from`) + B4 | T1.5 |
| Safe-intervene | Áp tại checkpoint (Wait) | ✅ | B4 drain point (hiện **thiếu**) | T1 |
| Safe-intervene | Approval-gate tool nguy hiểm | ⚠️ | B4 + checkpoint trước `run_tool` + expiry | T1 |
| Audit/Replay | Event log + audit có actor | ✅ | B8 + B1 (caveat durability) | T1 |
| Audit/Replay | Redaction | ⚠️ | B6 — **phải NỐI** (dead code); nên allowlist | T1 |
| Audit/Replay | Replay session | ✅ | đọc JSONL/SQLite | T1.5 |
| Audit/Replay | Causal "vì sao X" | ✅ | B8 đầy đủ | T1.5 |
| Interrupt | Wait mode | ✅ | B3 + B4 | T1 |
| Interrupt | Ask mode (popup 5s → Wait) | ✅ | B4 + UI | T1.5 |
| Interrupt | Agent node trong graph | ✅ | B2 | T1 |
| Interrupt | Nút Stop (Stop-now) | ⛔ | B10 cancellation = async | T2 |
| Interrupt | Cửa sổ Stream token | ⛔ | B11 `call_llm(stream=True)` + token-sink | T2 |

**Tóm tắt tier:**
- **T1** (spine v1: observe + Wait-command + approval, đồng bộ): B1, B2, B3, B4, B6, B8, B9 + SSE/snapshot API + UI Graph/Timeline/Inspector/Approval-modal.
- **T1.5** (breadth, vẫn đồng bộ, cần cơ-bắp-backend mới): B5 permission, B7 add-agent-qua-O, replay, causal, instrumentation breadth (S21.27–31), artifact versioning, + **các nhát chặn gốc** ở §3.
- **T2** (async + phân tán): B10 Stop-now, B11 token-stream, adapter Kafka/Redis/Postgres/WebSocket sau Port.

---

## 2. Phát hiện nền tảng: control plane là FACADE chưa nối vào runtime

Đây là khám phá quan trọng nhất. Tầng hợp đồng `control/` đẹp nhưng loop thật **không nghe lời nó**.

- **SEC-02** — Emitter mặc định `None` ([supervisor/graph.py:47](../../supervisor/graph.py)) và **không nơi nào ngoài test dựng nó**. Kernel/delegation/session phát event bằng `bus.publish(topic, dict)` thô ([core/kernel.py:80](../../core/kernel.py), [delegation/manager.py:148](../../delegation/manager.py)). → `EventEmitter` là dead code trên runtime thật.
- **SEC-03 / STRUCT-6** — Redactor là denylist key-name (`control/redaction.py:16-33,50-63`); secret trong *value* tự do (`error`, `message`, tool-result) lọt. Hơn nữa Redactor **không nằm trên đường UI thật**: tool args/error → `events.jsonl` → SSE **không redact** ([core/kernel.py:159](../../core/kernel.py) → [observability/event_log.py:105](../../observability/event_log.py) → [ui/server.py:359](../../ui/server.py)). Cờ `redact_for_ui`/`visibility` là metadata không ai đọc. (Giảm nhẹ: UI localhost no-auth → rò trên máy, không phải exfil mạng.)
- **LIVE-3** — `RuntimeCheckpoint`/`RuntimeCommand` là dataclass **trơ**, không người tiêu thụ trong `_drive` ([supervisor/loop.py:153](../../supervisor/loop.py)). Approval-gate "Wait at next checkpoint" — feature headline v1 — có hợp đồng nhưng **không executor**. Tool nguy hiểm chạy không qua cổng. `checkpoint.py` không có field `deadline`/`expiry`; status `expired` có trong enum nhưng **không code nào sinh**.

---

## 3. 10 worst-case sống sót + 3 critic → gom về 4 căn bệnh

Tất cả là một bệnh gốc: **nhiều bản sao sự thật (Blackboard / SQLite / JSONL / snapshot / metrics), không kỷ luật reconciliation.** Lưu ý: happy-path bình thường ỔN; mấy cái này cắn khi (a) crash+resume, (b) lỗi IO, (c) thêm feature theo thời gian.

### Bệnh 1 — Xương sống quan sát nói dối bằng im lặng (SD-6, LIVE-1, AUD-04, critic#2)
EventBus nuốt mọi exception sink: `try/except Exception: pass` ([core/events.py:27](../../core/events.py)). JSONL ghi lỗi → event biến mất không tiếng động → SQLite vẫn tiến (`ctx.save` vô điều kiện [supervisor/loop.py:206](../../supervisor/loop.py)). "Vì sao agent X được thêm" (S21.41) thành không trả lời được, không ai biết đã mất. Cờ `durable=true` không ai cưỡng chế; S21.40 "critical never drop" chưa implement. Metric counter + JSONL là **hai lần ghi riêng** trong cùng sink ([observability/event_log.py:110](../../observability/event_log.py)) → lệch hai chiều → `summary.json` ≠ `events.jsonl` vĩnh viễn.

### Bệnh 2 — Resume tách state/log/danh-tính, cộng dồn mỗi crash (SD-3, DE-1, critic#1)
- Kill giữa `delegate()` blocking ([supervisor/graph.py:175](../../supervisor/graph.py)): `events.jsonl` đã có `delegation.started` nhưng Blackboard chối → resume re-run → `delegation.started` lần hai + **effect tool chạy lần hai** (`run_tool` không save sau tool, không guard dedup — [supervisor/graph.py:213](../../supervisor/graph.py)). Stack single-agent chống được; `_drive` supervisor thì không (`by_design_only`).
- **critic#1 (đòn chí mạng):** resume đẻ `seq=0` mới + `trace_id` mới. Cùng `events.jsonl`, cùng `session_id` → **hai chuỗi seq đâm nhau** + chuỗi nhân-quả đứt. Hệ toạ độ thứ tự/dedup reset mỗi crash. `encode_taskloop_state` không lưu seq/trace ([supervisor/state.py:114](../../supervisor/state.py)). N lần resume = N chuỗi chồng = timeline không đọc được = rối-tung-do-tích-luỹ.

### Bệnh 3 — Cái treo không nhìn thấy (LIVE-2, nửa LIVE-3)
Sink fan-out đồng bộ, không timeout ([control/emitter.py:59](../../control/emitter.py) → [core/events.py:26](../../core/events.py) gọi inline). Sink chậm/kẹt (runs-dir NFS, hoặc sink Kafka/token-stream tương lai) đóng băng `_drive` giữa hai round; triệu chứng duy nhất: digest SSE đứng im → UI vẽ "vẫn chạy", không phải "treo". Approval-gate nếu nối ngây thơ + không expiry → chờ người duyệt **treo vĩnh viễn**.

### Bệnh 4 — Bệnh tăng trưởng: namespace không chủ, desync mỗi feature (STRUCT-6, critic#3)
`event_type` là namespace chuỗi mở xuyên **năm** registry (registry yaml · visibility yaml · call-site `ctx.emit(topic:str)` [supervisor/graph.py:55](../../supervisor/graph.py) · thang `if/elif` đếm metric · switch UI). Không chỗ buộc lại. Quên một trong năm → **không lỗi, âm thầm xuống cấp** (redaction sai mức / không đếm / không render). Qua N feature, năm mặt phẳng lệch đơn điệu → "control plane mâu thuẫn nội bộ về việc event nào tồn tại" = định nghĩa cấu trúc của rối tung.

---

## 4. 13 phát hiện = 4 nhát chặn gốc

| Nhát chặn | Giết bệnh | Gốc rễ |
|---|---|---|
| **1. Một đường ghi, fail-closed, cho kênh durable/audit** — durable event hoặc persist hoặc degrade *nhìn thấy* (counter + flag `summary.json`), không route qua bus nuốt-lỗi | Bệnh 1, nửa critic#2 | nhầm audit log là observer |
| **2. Nối control plane vào runtime — hoặc đừng gọi nó là control plane** — redact tại biên sink JSONL (chokepoint mọi event đi qua) + drain checkpoint/command trong `_drive` ở biên round; chưa nối thì đừng ship badge UI hứa | Bệnh 4 + facade (§2) | hợp đồng `control/` chưa tích hợp |
| **3. Resume khôi phục *danh tính*, không chỉ state** — lưu `{last_seq, trace_id, in_flight_turn}` vào `TaskLoopState`; seed emitter/trace khi resume; `in_flight` = đã-bắt-đầu (idempotency) | Bệnh 2 | resume vứt hệ toạ độ event stream |
| **4. Metric + UI-projection *dẫn xuất* từ event log, không lần-ghi/switch song song** — fold `events.jsonl` ra counter; một event-descriptor buộc {visibility+đếm?+UI+permission} + assertion lúc boot (fail-closed) | critic#2, critic#3, STRUCT-6 | nhiều nguồn sự thật, không reconcile |

---

## 5. Câu hỏi chưa giải

- B2/`control/snapshot.py` có được merge vào main không, hay phải dựng lại? (hiện chỉ trên branch)
- 4 nhát chặn gốc: làm trong T1 (an toàn từ đầu) hay chấp nhận nợ + flag, trả ở T1.5? (riêng nhát #2-redaction phải T1: UI hiện event = rò ngay nếu chưa redact)
- `idempotency_key` ai sinh, scope per-session hay global? (chưa đặc tả)
- `auto_approve` cho checkpoint `risk=low`: mặc định bật/tắt? Token `POST /api/commands`: per-session hay same-origin? Ring-buffer SSE giữ bao nhiêu event/session?
