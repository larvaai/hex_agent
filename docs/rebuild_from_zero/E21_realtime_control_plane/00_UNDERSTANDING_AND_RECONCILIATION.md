# E21 — Realtime Control Plane · Bản hiểu & Hoà giải (đọc trước khi triển khai)

> Mục đích của file này: **chứng minh tôi nắm đúng ý bạn**, rồi **chiếu thiết kế đó lên codebase thật** (không bê nguyên kiến trúc cloud vào một harness chạy local), và đề xuất cách hợp nhất với các epic đã có (E16/E17/E18).
>
> File song hành: [`01_BACKEND_STANDARDIZATION_BEFORE_UI.md`](01_BACKEND_STANDARDIZATION_BEFORE_UI.md) — danh sách **những thứ phải chuẩn hoá ở backend TRƯỚC khi đụng UI** (đúng phần bạn dặn trong ngoặc). · [`02_FULL_FEATURE_MAP.md`](02_FULL_FEATURE_MAP.md) — bản đồ phủ trọn 20 Feature của PRD "Production Control Tower" + phân tầng T1/T2. · [`03_INTERRUPT_AND_INJECT_MODEL.md`](03_INTERRUPT_AND_INJECT_MODEL.md) — mô hình ngắt/chen ngang (Wait/Stop-now/Ask + nút Stop). · PRD/stories/AC: [`PRD.md`](PRD.md) · [`stories.md`](stories.md) · [`acceptance.md`](acceptance.md).

---

## 1. Tôi hiểu bạn muốn gì (tóm tắt có kiểm soát)

Bạn muốn một **mặt phẳng điều khiển realtime** cho vòng lặp đa-agent (Agent O + worker), với 4 năng lực và 1 luật bất biến:

1. **Quan sát (observe):** UI thấy Agent O đang gọi ai; agent nào `pending / waiting / running / done / failed`; tool/hook/skill/permission/checkpoint trước-và-sau khi chạy; acceptance criteria nào `passed/missing/failed`.
2. **Can thiệp (command):** từ UI gửi lệnh realtime — pause/resume, approve/reject, kéo-thả thêm agent, sửa quyền, sửa instruction.
3. **Áp dụng tại checkpoint an toàn (safe intervention):** thay đổi **không** áp dụng giữa lúc agent đang sinh token, mà tại điểm dừng an toàn (before_round, after_agent_result, before_tool_call, before_acceptance_review, when_blocked).
4. **Audit/replay:** mọi thay đổi sinh event, có redaction, idempotency, replay được để trả lời "vì sao agent X được thêm, ai thêm, round nào, quyền lúc đó là gì".

**Luật bất biến (tôi coi đây là cốt lõi của thiết kế):**

> **UI không bao giờ sửa state trực tiếp.** UI chỉ phát *command*. Runtime kiểm policy → Agent O nhận *command đã validate, có cấu trúc* (không phải text thô) → tại checkpoint, O biến nó thành `AgentInvocation`/áp dụng → UI thấy workflow đổi **qua event stream**. Agent không tự vượt quyền; mọi state-transition quan trọng đều có event tương ứng.

Đây chính là tinh thần hexagonal mà repo đang theo: **năng lực nằm sau port; lõi không phình to.** Bản thiết kế của bạn không mâu thuẫn với repo — nó chỉ cần được *right-size* về đúng hạ tầng.

---

## 2. Trạng thái thật của codebase (cái gì đã có, đặt tên seam chính xác)

| Vai trò trong thiết kế của bạn | Đã hiện hữu trong repo? | Ở đâu |
|---|---|---|
| `TaskLoopSnapshot` (state quan sát được) | **Một phần** — đã có Blackboard serializable | `TaskLoopState` [supervisor/state.py:80](../../../supervisor/state.py); status enum [:14](../../../supervisor/state.py) |
| Vòng lặp Agent O (orchestrator/judge) | **Có** | `_drive()` [supervisor/loop.py:141](../../../supervisor/loop.py); `o_decide` [supervisor/graph.py:88](../../../supervisor/graph.py) |
| "Checkpoint an toàn" để áp dụng thay đổi | **Có điểm dừng, nhưng chưa phải approval-gate** | `ctx.save(state)` mỗi round [supervisor/loop.py:183](../../../supervisor/loop.py) và sau mỗi turn [supervisor/graph.py:189](../../../supervisor/graph.py) |
| Event bus | **Có, nhưng tối giản** | `EventBus.publish` fire-and-forget, nuốt exception [core/events.py:22](../../../core/events.py) |
| Event store durable + replay | **Có, dạng file** | `EventLogger` JSONL + `summary.json` + `index.jsonl`, có `seq` đơn điệu/run [observability/event_log.py:41](../../../observability/event_log.py) |
| Snapshot → UI realtime | **Có, dạng polling-diff** | SSE `_stream` băm snapshot mỗi 0.75s [ui/server.py:517](../../../ui/server.py) |
| Permission/scope cho worker | **Có, theo từng turn** | `DelegationPolicy.allowed_capabilities` do O đặt [supervisor/graph.py:155](../../../supervisor/graph.py) |
| Policy gate chặn tool | **Có** | `PolicyGate` deny-list chokepoint [middleware/policy.py:9](../../../middleware/policy.py) |
| Authority check (agent phải được chọn) | **Có** | `run_round` [supervisor/graph.py:122](../../../supervisor/graph.py) |
| State checkpoint / resume | **Có** | `SqliteTaskLoopStore` [supervisor/checkpoint.py:22](../../../supervisor/checkpoint.py); `resume_task_loop` [supervisor/loop.py:103](../../../supervisor/loop.py) |

### Cái gì **chưa** có (phải dựng mới)
- **`RuntimeCommand`** — không tồn tại. Không có command queue, không idempotency, không command channel ghi.
- **Approval-checkpoint** — `SqliteTaskLoopStore` là *state* checkpoint (để resume), **không phải** điểm "dừng chờ người duyệt hành động nguy hiểm". Khái niệm "pause → human approve → resume" chưa có.
- **`pending_human_commands` vào input của O** — `_state_view` [supervisor/graph.py:105](../../../supervisor/graph.py) hiện không chứa lệnh người. O chưa "nghe lệnh có cấu trúc".
- **Permission do người chỉnh** (session+agent, `effective_from=next_checkpoint`) — hiện scope chỉ do O đặt per-turn, người không sửa được qua một bản ghi bền.
- **Redaction** — payload event chưa hề được redact trước khi ra UI/SSE (UI chỉ chặn *file* nhạy cảm, không chặn *event payload*).
- **Per-agent live status** (`pending/waiting/running`) + `orchestrator.last_decision` + `pending_agent_calls` — Blackboard có `selected_agents`/`turns` nhưng chưa phóng chiếu ra trạng thái sống mà graph-view cần.
- **Command channel + authz** — `ui/server.py` chạy localhost **không xác thực**, chỉ có `POST /api/runs` để *bắt đầu* run, không có kênh gửi lệnh điều khiển.
- **Audit trail có actor** — `events.jsonl` có nhưng chưa cấu trúc thành audit (ai-làm-gì, command/permission/approval).

---

## 3. Quyết định cần bạn chốt: **right-size hạ tầng** (đây là ngã ba lớn nhất)

Bản bạn dán đề xuất **Postgres + Kafka + Redis Streams + outbox relay + WebSocket**. Với một harness **local, đơn tiến trình, một người dùng**, bê nguyên cụm này vào sẽ:
- phá nguyên tắc "core thin" (thêm 3 hệ phân tán + adapter cho mỗi cái),
- 10x bề mặt vận hành cho thứ chạy trên máy bạn,
- và **mâu thuẫn với chính lời bạn**: "không để core phình to", "MVP dễ nhất".

**Đề xuất của tôi (mặc định tôi sẽ dùng nếu bạn không phản đối): giữ nguyên *contracts* của thiết kế, nhưng chiếu *hạ tầng* về đúng stack hiện có, và đặt sau Port để sau này thay được mà không đụng core/supervisor.**

| Vai trò (thiết kế gốc) | MVP local (đề xuất) | Đường nâng cấp sau (sau Port, không đụng core) |
|---|---|---|
| Kafka — durable backbone/replay | `EventLogger` JSONL + `seq` toàn cục + replay từ JSONL/SQLite | `EventSinkPort` → Kafka adapter |
| Redis Streams — live fanout | `EventBus` in-process + ring-buffer bound theo session; SSE tail sẵn | `LiveBusPort` → Redis adapter |
| Postgres — source of truth query | **SQLite** (mở rộng `SqliteTaskLoopStore`: thêm bảng `commands`, `checkpoints`, `permissions`, `audit`) | `ControlStorePort` → Postgres adapter |
| WebSocket — command channel | `POST /api/commands` (auth + idempotency) trên server SSE hiện có | nâng lên WS khi cần hai chiều thật |
| Outbox relay | Không cần (đơn tiến trình): kỷ luật **"ghi event trước, gây side-effect sau" + idempotency** là đủ | bật outbox khi tách tiến trình |

> Những phần **đáng giá và độc lập hạ tầng** của thiết kế — *envelope, command, checkpoint, permission, redaction, registry, "UI chỉ gửi command"* — tôi giữ **nguyên vẹn**. Chỉ phần transport/storage là right-size. Nếu sau này bạn thật sự cần multi-node/multi-user, ta gắn adapter Kafka/Redis/Postgres vào đúng các Port ở trên mà không phải viết lại lõi.

**Nếu bạn muốn ngược lại** (làm thẳng Postgres/Kafka/Redis ngay từ MVP), nói một câu, tôi sẽ viết docs theo hướng nặng đó — nhưng tôi khuyến nghị không, cho giai đoạn này.

---

## 4. Hoà giải với epic đã có (E16/E17/E18)

Ba epic hiện tại đang **mỏng và rời**:
- **E16 Human Review Gate** = approve/deny/annotate plan & diff → chính là *approval-checkpoint* trong thiết kế của bạn.
- **E17 User Live Control** = directive inbox giữa run → chính là *command channel + pending_human_commands*.
- **E18 UI Dashboard** = xem process/log/state → chính là *UI Control Tower* (graph/timeline/inspector).

Thiết kế "Realtime Control Plane" của bạn **là lớp hợp nhất** của cả ba, cộng thêm phần *contract/observability* còn thiếu (envelope chuẩn, redaction, command idempotency, checkpoint engine).

**Đề xuất tổ chức:** gom thành **một epic E21 — Realtime Control Plane**, và coi E16/E17/E18 là *các slice* bên trong nó (giữ số hiệu cũ làm cross-reference). Cụ thể:
- E21·S-Contract → envelope + command + checkpoint + permission + redaction + registry (mới).
- E21·S-Control (⊇ E17) → command channel + queue + `pending_human_commands` vào O.
- E21·S-Gate (⊇ E16) → approval-checkpoint engine + pause/resume.
- E21·S-UI (⊇ E18) → Control Tower panels.

> Nếu bạn không thích số **E21** hay cách gộp này, đổi tên/tách lại trước khi tôi viết PRD/stories/AC chi tiết.

---

## 5. Thứ tự triển khai đề xuất (đúng tinh thần "đừng bắt đầu bằng UI")

```
Phase A — Contracts (không I/O)
   RuntimeEvent envelope · RuntimeCommand · Checkpoint · Permission · Redaction
   + event-type registry + command-type registry  → contract tests
Phase B — Backend chuẩn hoá (xem file 01)
   nâng EventBus→envelope · SQLite control store · command queue + idempotency
   · checkpoint/intervention points trong _drive · permission record · redaction boundary
   · pending_human_commands vào _state_view · audit log · authz tối thiểu
Phase C — Transport
   POST /api/commands (auth) · SSE phát envelope đã redact · Last-Event-ID resume
Phase D — UI Control Tower
   Graph · Timeline · Inspector · Checkpoint modal · Permission editor · Replay
Phase E — Reliability/replay/chaos (right-size)
   resume tại approval-checkpoint · reconnect · degrade khi sink lỗi
```

**Phase B là điều kiện cần để bắt đầu UI** — chi tiết ở [`01_BACKEND_STANDARDIZATION_BEFORE_UI.md`](01_BACKEND_STANDARDIZATION_BEFORE_UI.md).

---

## 6. Definition of Done (kế thừa của bạn, đã neo vào repo)

Một slice chỉ "done" khi: có contract/schema rõ · có validation · có permission check nếu đụng user/agent/tool · **mọi state-transition quan trọng đều phát event qua envelope chuẩn** · có audit cho command/permission/checkpoint/tool/artifact · có redaction nếu payload có thể lên UI · có test duplicate/idempotency cho command · có failure behavior · **không để core phụ thuộc trực tiếp transport/storage (phải sau Port)** · **UI không sửa state trực tiếp** · agent không tự bypass runtime gate.

---

## 7. Tôi cần bạn xác nhận trước khi viết PRD/stories/AC vét cạn

1. **Hạ tầng:** đồng ý right-size về SQLite/JSONL/EventBus + Port (mục 3) hay làm thẳng Postgres/Kafka/Redis?
2. **Tổ chức epic:** gộp về **E21** và coi E16/E17/E18 là slice (mục 4) — ok không?
3. **Command channel MVP:** `POST /api/commands` trên server hiện có là đủ cho v1, hay bạn muốn WebSocket ngay?

Trả lời 3 câu này xong, tôi sẽ viết `PRD.md` + `stories.md` + `acceptance.md` (Given/When/Then, map thẳng E19) cho E21 — theo đúng format các epic khác trong `rebuild_from_zero/`.
