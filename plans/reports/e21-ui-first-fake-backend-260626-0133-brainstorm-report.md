---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Brainstorm — E21 Control-plane UI dựng trước trên fake backend

**Ngày:** 2026-06-26 · **Skill:** hs-think:brainstorm (diverge→converge) · **DEC:** DEC-6
**Yêu cầu gốc:** "Xem S21, làm UI trước, thử với fake backend; sau này UI xong chỉ sửa chút, đấu nối vào backend là được."

---

## 0. TL;DR

Ý tưởng UI-first **khả thi** và không mâu thuẫn hợp đồng — nhưng câu "sau này chỉ sửa chút" chỉ đúng nếu fake backend **nói đúng tiếng backend thật**. Chốt: fake = **HTTP/SSE server Python dùng lại dataclass trong `control/`** (fidelity bảo đảm bằng cấu trúc, đổi backend = đổi URL), stack **React+Vite+TS**, lát 1 = **full T1 + prompt/Send**. Một chặn-trước bắt buộc: **2/5 shape UI cần tiêu thụ (`TaskLoopSnapshot`, `CommandAck`) chưa có dataclass** — phải tạo trước khi viết UI, nếu không seam còn lỗ.

Vì sao quan trọng (giải thích cho người mới): UI vẽ lên *hình dạng dữ liệu* (data shape). Nếu fake bịa hình dạng khác backend thật, lúc đấu nối UI không "sửa chút" — nó render sai field, vỡ cả màn Graph/Inspector. Toàn bộ giá trị kế hoạch nằm ở chỗ chọn *cái seam* (đường nối) cho fake và real **chung một hình dạng**.

---

## 1. Quyết định đã chốt (DEC-6)

| # | Quyết định | Lý do ngắn |
|---|---|---|
| 1 | Fake nói **đúng hợp đồng E21 thật** (SSE `ui_payload` có seq/Last-Event-ID, `GET /api/snapshot`→`TaskLoopSnapshot`, `POST /api/commands`→ACK) | đấu nối sau = đổi *nguồn*, không đổi *shape* |
| 2 | Seam = **Hướng B**: fake server Python reuse `control/` dataclass + adapter UI mỏng | fidelity by-construction, không phải by-discipline |
| 3 | **Tạo `TaskLoopSnapshot` + `CommandAck` dataclass TRƯỚC** khi viết UI (dataclass-only, không wire runtime) | bịt 2/5 lỗ shape |
| 4 | Stack **React + Vite + TS** (React Flow + tanstack-virtual) | reader junior cần ecosystem/ví dụ |
| 5 | Lát 1 = **full T1**: Graph + Timeline + Inspector + Approval modal + Wait-command + **prompt box & Send** | giao việc → xem tiến trình → điều phối |
| 6 | **Console cũ `ui/server.py` để yên**, dựng mới song song (vd `ui/control-plane/`) | KISS/YAGNI, console cũ khác transport |
| 7 | Done = **demo tương tác trên fixtures + contract-seam test** (UI chỉ đọc `ui_payload`, không đọc `payload` raw) | đảm bảo drop-in |

> Đảo thứ tự so với discovery brief (`plans/260626-0037-e21-control-plane-v1/discovery-brief.md` chọn "spine-backend-first"), **nhưng không xây trên facade**: fake chạy `Redactor().apply()` thật → secret không rò kể cả lúc demo (trị thẳng rủi ro #1 của brief).

---

## 2. Cái seam: 5 mảnh shape, 2 mảnh chưa tồn tại

UI tiêu thụ đúng 5 hình dạng. Agent đọc `control/` thật:

| Shape | Trạng thái | Evidence |
|---|---|---|
| `RuntimeEvent` (envelope, split `payload`/`ui_payload`) | ✅ dataclass | `control/events.py:113-190`; `as_dict` `:153-170`; split `:131-132`; "SSE streams only ui_payload" `:7-9` |
| `RuntimeCommand` | ✅ | `control/commands.py:52-97`; `as_dict` `:74-84`; `idempotency_key` non-empty `:57,64`; `parse_command` `:100-110` |
| `RuntimeCheckpoint` (lifecycle waiting→approved) | ✅ | `control/checkpoint.py:27-93`; status enum `:18`; `with_status()` chỉ cho waiting→terminal `:57-68` |
| `Permission` | ✅ | `control/permission.py:19-73`; `effective_from` default `next_checkpoint` `:16,27`; `patched()` `:38-50` |
| **`TaskLoopSnapshot`** (Graph/Inspector vẽ lên) | ❌ **chỉ trong spec** | shape ở `docs/spec/active/E21-realtime-control-plane/01_BACKEND_STANDARDIZATION_BEFORE_UI.md:20`; suy từ `TaskLoopState` `supervisor/state.py:80-116` |
| **`CommandAck`** (response POST /api/commands) | ❌ **không dataclass** | AC S21.15 chỉ mô tả chữ: `acceptance.md:62` |

**Phụ trợ (nguồn enum cho UI):**
- Redaction: `SECRET_KEYS` `control/redaction.py:16-33`; `Redactor.apply()` `:65-73`; hằng UI phải khớp `REDACTED = "[REDACTED]"` `:34`.
- 15 command types: `config/runtime_command_types.yaml` (`PauseWorkflow, ResumeWorkflow, ApproveCheckpoint, RejectCheckpoint, AddAgentToLoop, UpdateAgentPermission...`), `apply_at`/`requires_permission` per type.
- ~40 event types: `config/runtime_event_types.yaml` (`session.*, agent.*, tool.*, checkpoint.reached, approval.*, command.*`), có `visibility`/`durable`/`redact_for_ui`.
- `seq` cấp bởi `SessionSeq.next()` `events.py:193-208` — monotonic per-session, đây là field gắn `Last-Event-ID`.

**Hệ quả:** chốt #3 (tạo 2 dataclass trước) không phải "nice-to-have" — nó là điều kiện để câu "drop-in" đúng cho **cả 5** shape thay vì 3.

---

## 3. Kiến trúc seam — vì sao Hướng B

| Tiêu chí | A. Adapter TS thuần | **B. Fake server Python reuse `control/`** (chọn) |
|---|---|---|
| Fidelity | by-discipline (TS tự dựng object) | **by-construction** (serialize từ dataclass thật → không thể lệch field) |
| Drop-in cost | 1 dòng factory | **0 dòng UI — đổi URL** |
| reconnect / `Last-Event-ID` | tự mô phỏng `EventSource` trong TS → dễ bỏ sót | browser `EventSource` thật tự gửi `Last-Event-ID` |
| seq / dedup / redaction | tay | dùng `SessionSeq.next()` + `Redactor` thật |
| "fake quá sạch → vách đá" | **rủi ro cao** | **thấp** (chạy đúng đường ống) |
| effort lúc đầu | thấp | trung bình (viết HTTP server nhỏ — đã có pattern `ui/server.py`) |

**Chốt B + adapter UI mỏng (~30 dòng).** Adapter **không** phải lớp swap transport (server lo việc đó) — nó chỉ gom mọi `fetch`/`EventSource` vào một chỗ để test được. Đây là điểm bám cho contract-seam test (§7). Không phình thành "Hướng C" (adapter + server đều làm việc swap) vì trả 2 lần effort cho cùng fidelity — vi phạm YAGNI.

Cốt lõi (Feynman): cách duy nhất để "đấu nối chỉ sửa chút" *đúng thật* chứ không phải lời hứa, là cho fake chạy **cùng đường ống** với real. Khác đường ống thì mọi cái khó (reconnect, dedup, redaction, latency) bị giấu tới phút cuối.

---

## 4. Type-fidelity: giữ UI types == Python contract

Generate **TS từ dataclass** (single source of truth = `control/`), không hand-write TS (drift im lặng). Vì dataclass không dùng pydantic (`events.py:3-4`) nên không có `.model_json_schema()` sẵn — viết một script nhỏ duyệt `control/*.py`, mỗi dataclass đã có `as_dict` liệt kê field tường minh → sinh `.d.ts` (hoặc JSON Schema → `json-schema-to-typescript`).

**Drift-guard rẻ:** CI chạy generator + `git diff --exit-code` trên file TS sinh ra. Dataclass đổi field → TS đổi → PR đỏ nếu quên regen. Biến type-fidelity từ by-discipline → by-CI.

YAGNI: **không** generate runtime validator (zod) ở v1 — runtime validate là việc của fake server (đã có `__post_init__` thật trong dataclass).

---

## 5. Framework: React + Vite + TS

Reader junior → trọng số docs/ecosystem/ví dụ-copy-được.
- **Graph (S21.18):** React Flow `@xyflow/react` chín hơn Svelte Flow (Svelte Flow mới "reached feature parity" — [xyflow blog](https://xyflow.com/blog/why-svelte-flow)). Cả hai **không tự layout DAG** → thêm `dagre` hoặc `elkjs` cho auto-layout (giống nhau ở cả 2 framework).
- **Timeline virtualized (S21.19, hàng nghìn event):** `@tanstack/react-virtual` (headless, docs tốt).
- **SSE/commands:** dùng `EventSource` native — **không cần MSW** làm fake chính (đã có fake server Python). MSW chỉ là dev-dep cho component test lẻ; kéo MSW vào làm transport fake = đúng cái "fake quá sạch" TS-side mà §3 cảnh báo. MSW v2.12+ có hỗ trợ SSE ([mswjs.io/docs/sse](https://mswjs.io/docs/sse/)) nhưng ở đây không dùng.

Đánh đổi: Svelte nhẹ/ít boilerplate hơn, nhưng ecosystem nhỏ + ít ví dụ agent-graph → junior dễ kẹt ở vấn đề ít người trả lời. Với surface này (graph + virtualization + modal), maturity của React Flow thắng.

---

## 6. Fixtures: hand-authored dưới dạng `events.jsonl`, replay-ready

Bắt đầu bằng **scenario viết tay BẰNG dataclass thật**, xuất ra format `events.jsonl` (mỗi dòng = `RuntimeEvent(...).as_dict()` đã qua `Redactor().apply()`). Lý do:
- Chạy được NGAY (backend chưa emit — emitter default `None`, discovery brief).
- Fake server **đọc & replay `events.jsonl`** → hand-authored và real-capture (tương lai, qua `EventLogger` JSONL `ports.py`) **dùng chung một code path replay**. Backend bắt đầu emit thật → drop file thật vào cùng folder, không đổi UI/fake-server.
- **Tránh scenario-DSL** ở v1 (YAGNI).

Kịch bản tối thiểu phủ T1: O chọn A,B,C → A `done` → B `running` → C `pending` → tool `risk_level=high` → `checkpoint.reached` waiting → (chờ command) → `ApproveCheckpoint` → `approval.approved` → B `finished`. Khớp AC S21.9/S21.18/S21.21.

Điểm mấu chốt: fixtures **sinh qua dataclass thật**, không phải JSON viết tay — cùng nguyên lý by-construction.

---

## 7. Map T1 surface → stories (để plan bám)

| Màn UI | Story | Shape tiêu thụ |
|---|---|---|
| Agent Graph (node status realtime, click→inspector) | S21.18 | `TaskLoopSnapshot.agents[]`, event `agent.*` |
| Event Timeline (virtualized, filter type/agent/tool) | S21.19 | stream `RuntimeEvent.ui_payload` theo `seq` |
| Agent Inspector (role, context redact, allowed_tools, last output, permission) | S21.20 | `TaskLoopSnapshot` + `Permission` |
| Checkpoint/Approval modal (risk + diff + Approve/Reject) | S21.21 | `RuntimeCheckpoint`, gửi `ApproveCheckpoint`/`RejectCheckpoint` |
| Prompt box & Send (giao việc, Wait-command) | S21.15 + locked | `POST /api/commands` → `CommandAck` |

**Contract-seam test (định nghĩa Done):** assert UI (1) chỉ đọc `ui_payload`, **không bao giờ đọc `payload`** raw; (2) render `[REDACTED]` đúng `redaction.py:34`; (3) Approve gửi `RuntimeCommand` thật qua POST, không mutate state UI-side; (4) reconnect dùng `Last-Event-ID` catch-up.

---

## 8. Rủi ro + giảm thiểu

| Rủi ro | Mức | Mitigation |
|---|---|---|
| **R1 — 2 shape (`TaskLoopSnapshot`,`CommandAck`) chưa có dataclass → drift/vách đá tại điểm nối** | **cao** (lớn nhất, không phải framework) | tạo `control/snapshot.py` + `CommandAck` TRƯỚC khi viết UI; derive từ `TaskLoopState` `supervisor/state.py:80` + spec `01_BACKEND...md:20` |
| R2 — "fake quá sạch" che reality (reconnect, idempotency `commands.py:57`, latency, re-resolve guard `checkpoint.py:64`) | cao | fake server chủ động inject: random latency, drop SSE ép reconnect (AC S21.16 `acceptance.md:66`), duplicate `event_id`, duplicate `idempotency_key` |
| R3 — discovery brief risk #1: UI trên facade → rò secret + approval giả | cao nếu bỏ qua | fake **bắt buộc** chạy `Redactor().apply()` thật + chỉ stream `ui_payload`; `visibility=secret` → không stream; Approve gửi command thật, `with_status()` thật |
| R4 — UI mới + console cũ phân kỳ, không ai hợp nhất | thấp-tb | DEC-6 chốt "song song"; ghi nợ hợp nhất vào BACKLOG, không phình lát 1 |

---

## 9. Câu hỏi mở (chốt ở hs:plan)

- [ ] **`CommandAck` trả gì** ngoài `command_id`? (status `accepted`? `seq` của `command.received`?) — cần định shape để fake và real khớp. AC S21.15 nói ACK <300ms kèm `command_id`, `applied` đến sau qua SSE.
- [ ] **Auth/token v1 (S21.15 401/403):** fake có mô phỏng token reject không, hay no-auth, thêm khi nối thật? (ảnh hưởng path Send.)
- [ ] **`TaskLoopSnapshot` field cuối cùng:** chốt danh sách field theo `supervisor/state.py:80-116` + spec `01_BACKEND...md:20` — cái nào vào v1, cái nào sau?
- [ ] **Generate-TS:** sinh `.d.ts` trực tiếp hay qua JSON Schema trung gian? (ảnh hưởng độ phức tạp script + CI guard.)
- [ ] **Ring-buffer SSE** fake giữ tối đa bao nhiêu event/session trước khi fallback đọc JSONL? (đồng bộ với spine sau.)

---

## 10. Next step

Brief đã hội tụ + DEC-6 ghi. Đề xuất: **`/hs:plan`** cho lát 1 (full T1 + fake server + 2 dataclass mới), nhánh `--tdd` vì có contract-seam test là load-bearing. Trước khi gọi plan, nên `/clear` để tránh bias mang từ brainstorm (`harness/rules/workflow-handoffs.md` #5).

**Phạm vi plan đề xuất:** (1) `control/snapshot.py` + `CommandAck` dataclass; (2) script generate TS + CI drift-guard; (3) fake server Python (replay `events.jsonl`, inject reality R2); (4) fixtures scenario T1; (5) React+Vite scaffold + adapter mỏng; (6) 4 màn T1 + prompt/Send; (7) contract-seam test.

---

_Nguồn ngoài:_ [xyflow/xyflow](https://github.com/xyflow/xyflow) · [Why Svelte Flow](https://xyflow.com/blog/why-svelte-flow) · [MSW SSE docs](https://mswjs.io/docs/sse/)
