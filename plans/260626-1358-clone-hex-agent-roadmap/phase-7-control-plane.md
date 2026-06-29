---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 7 — Realtime control plane (E21)

> Epic: E21 · Cổng vào: Phase 6 + observability · Trạng thái: **đang xây** (contracts + EventEmitter shipped; transport/UI/reliability pending) · Rời phase với: một control plane chạy ABOVE kernel, mọi event đi qua một envelope duy nhất, secret bị mask ở biên trước khi tới UI, và authz tách khỏi attribution.

## 1. Mục tiêu & ranh giới

Bạn cho con người **quan sát và can thiệp** một run multi-agent đang chạy realtime — mà không rò secret, không cho ai leo quyền chỉ bằng cách "tự khai mình là ai".

Ranh giới cứng (đừng phá):

- **Contracts-first, layer ABOVE kernel, no I/O.** `control/` ngồi trên kernel/supervisor đúng như `supervisor` ngồi trên kernel. Các dataclass trong `control/` **không** mở socket, không ghi file, không gọi HTTP. Chúng chỉ là *hình dạng* + *validation*. Transport (HTTP/SSE) và storage sống sau `control/ports.py`.
- **Một envelope cho mọi event.** UI, audit, replay, mọi sink đọc cùng một format: `RuntimeEvent` (`control/events.py:113`).
- **Secret chết ở biên.** Không payload thô nào tới UI. `Redactor` (`control/redaction.py:37`) tách `payload` (thô, nội bộ) khỏi `ui_payload` (đã mask). UI **chỉ** đọc `ui_payload`.
- **Attribution ≠ authz.** `issued_by`/`Actor` là *ai tự khai mình đã làm* (audit), KHÔNG phải bằng chứng quyền. Quyền do `requires_permission` + checkpoint quyết, không do claim của issuer (DEC-8).

Vì sao "control plane sits ABOVE kernel like supervisor": kernel chỉ biết chạy một agent. Supervisor (Phase 6) điều phối nhiều agent. Control plane (Phase 7) là *tầng giám sát* trên cả hai — nó *quan sát* event mà chúng phát và *bơm* command mà người gửi xuống, mà không *là* logic chạy. Đúng quan hệ supervisor→kernel: tầng trên không trộn vào tầng dưới, chỉ định khung và đọc/ghi qua seam.

Cái KHÔNG thuộc phase này: logic agent (Phase 6), LLM ports (Phase 2). Phase 7 chỉ lo *vỏ điều khiển* quanh chúng. Một dấu hiệu bạn đang phá ranh giới: import `requests`/`socket`/`open()` vào bất kỳ file nào trong `control/`. Nếu thấy, dừng lại — cái đó thuộc transport, sống sau `control/ports.py`.

## 2. Bạn sẽ xây gì (bản đồ module) + cái gì ĐÃ XONG vs SẼ LÀM

| Module | Vai trò (cái neo) | Trạng thái |
|---|---|---|
| `control/events.py` | `RuntimeEvent` envelope + `Actor`/`TraceContext`/`RedactionInfo` + `SessionSeq` | **đã chạy** |
| `control/event_registry.py` | allowlist event-type (load `config/runtime_event_types.yaml`) | **đã chạy** |
| `control/commands.py` | `RuntimeCommand` + `IssuedBy` + `CommandAck` + `parse_command` | **đã chạy** |
| `control/command_registry.py` | allowlist command-type (`apply_at`, `requires_permission`) | **đã chạy** |
| `control/checkpoint.py` | `RuntimeCheckpoint` — cổng phê duyệt cho hành động rủi ro | **đã chạy** (contract) |
| `control/permission.py` | `Permission` — hồ sơ năng lực per-agent, human sửa được | **đã chạy** (contract) |
| `control/redaction.py` | `Redactor.apply()` mask ~14 secret key, KHÔNG mutate gốc (I16) | **đã chạy** |
| `control/emitter.py` | `EventEmitter` — đường publish duy nhất: gate → seq → redact → fan-out | **đã chạy** (B1) |
| `control/authz.py` | predicate attribution≠authz (DEC-8, I17) | **đã chạy** (predicate thuần) |
| `control/replay.py` | `EventReplayBuffer` — ring buffer SSE stream + resync từ đó | **đã chạy** |
| `control/snapshot.py` | `TaskLoopSnapshot` read-model UI render (đọc `ui_payload`) | **đã chạy** |
| `control/ports.py` | `EventSinkPort` — seam transport/storage cắm sau | **đã chạy** (Protocol) |
| `tools/fake_control_server.py` | fake HTTP/SSE backend reuse `control/` (DEC-6) | **đã chạy** |
| `ui/control-plane/` + `ui/ide/` | React+Vite+TS UI + live backend reuse `control/` | **một phần** (UI build, IDE live; chưa là default runtime path) |
| Authz **enforcement** call-site (`command_bridge`) | nơi áp `requires_permission`/checkpoint trước khi apply command | **SẼ LÀM** — predicate có, call-site VẮNG (DEC-7/DEC-8) |
| Supervisor live-wiring | mọi event runtime đi qua envelope mặc định | **SẼ LÀM** — emitter opt-in, default `None` (`supervisor/graph.py:48`) |
| Reliability (at-least-once, resync end-to-end) | hardening transport thật | **SẼ LÀM** — mô phỏng trong fake/replay, chưa production |

Honest line: contracts + emitter + redaction + fake backend + read-model **đã chạy và có test**. Phần *thực thi quyền* và *biến envelope thành đường mặc định của runtime live* là thiết kế chưa wire.

**Registry không chỉ chặn tên — nó mang policy.** Mỗi event-type trong `config/runtime_event_types.yaml` khai `visibility` / `durable` / `redact_for_ui` / `checkpoint_candidate` (`event_registry.py:23` `EventTypeSpec`). Đó là lý do emitter biết redact ở mức nào (`emit_event` lấy `spec.visibility`), và tại sao chỉ event `public`/`ui_safe` ra wire. Mỗi command-type trong `config/runtime_command_types.yaml` khai `apply_at` (`next_checkpoint`/`immediate_if_waiting`/`immediate`) + `requires_permission` (`command_registry.py:23`). Ví dụ neo: `UpdateAgentPermission` → `requires_permission: workflow.modify_permissions` (`runtime_command_types.yaml:27`) chính là chỗ predicate authz móc vào.

Thiết kế đầy đủ (đọc khi cần): `docs/spec/active/E21-realtime-control-plane/` — PRD, `stories.md`, `01_BACKEND_STANDARDIZATION_BEFORE_UI.md` (vì sao chuẩn hoá backend trước UI), `02_FULL_FEATURE_MAP.md` (tier T1/T2 — cái gì local, cái gì sau port), `03_INTERRUPT_AND_INJECT_MODEL.md` (mô hình interrupt/inject command).

## 3. Dựng step-by-step

Thứ tự nội bộ E21. Mỗi bước có self-check. Vì sao đúng thứ tự này quan trọng: mỗi bước *khoá* một bất biến rồi mới cho bước sau xây lên. Contract khoá hình dạng → registry khoá tên → emitter khoá đường publish → redact khoá biên secret → fake khoá seam → UI xây trên seam đã khoá. Đảo thứ tự (ví dụ viết UI trước khi có `TaskLoopSnapshot` dataclass) là cách seam thành "lỗ by-discipline": UI và backend *trông* khớp nhưng không có gì ép chúng khớp.

**B0 — Contracts trước.** Viết `control/events.py` đầu tiên: `RuntimeEvent` validate trong `__post_init__` nên một event sai **không thể tồn tại**, đừng nói tới chuyện publish. Frozen dataclass + `as_dict`/`from_dict` (khớp repo, không pydantic). Tự kiểm: `RuntimeEvent(event_type="", ...)` → `ControlContractError`.

**B1 — Registry = allowlist.** `event_registry.py` + `command_registry.py` load YAML. Mọi `event_type`/`command_type` phải khai trong `config/runtime_event_types.yaml` / `runtime_command_types.yaml`. Module **không tự chế tên** — `assert_known` chặn. Tự kiểm: `registry.assert_known("agent.invented")` raise.

**B2 — Backend chuẩn hoá TRƯỚC UI (điều-kiện-trước-UI).** Đây là tinh thần file `01_BACKEND_STANDARDIZATION_BEFORE_UI.md`: 2/5 shape (`TaskLoopSnapshot`, `CommandAck`) phải có dataclass *trước* khi viết một dòng UI. Nếu không, seam còn lỗ "by-discipline" thay vì "by-construction". Tự kiểm: `CommandAck` + `TaskLoopSnapshot` import được, `.as_dict()` chạy.

**B3 — Emitter + redaction.** `emitter.py` là đường publish DUY NHẤT, thay `bus.publish(topic, dict)` rải rác. Luồng cứng: **gate → seq → redact → fan-out** (`control/emitter.py:53`). Redactor fill `ui_payload` ở đúng `visibility` của type. Tự kiểm: `Redactor().apply()` không đổi `event.payload` gốc; event lạ → raise trước khi tới sink.

**B4 — Fake HTTP/SSE backend reuse dataclass (DEC-6).** `tools/fake_control_server.py` chạy **cùng** `Redactor`, **cùng** `parse_command`/`CommandTypeRegistry`, **cùng** `build_snapshot` mà backend thật sẽ chạy. Đây là chỗ "drop-in = đổi URL" thành thật chứ không khẩu hiệu: *fake = thật về cấu trúc*. Secret không rò vì cùng một đường redact. Tự kiểm: `FakeControlPlane.stream()` chỉ trả frame của event `public`/`ui_safe`, `data` luôn là `ui_payload` (không bao giờ raw).

**B5 — UI-first trên fake.** Vì fake = thật về cấu trúc, UI (`ui/control-plane/`, React Flow + tanstack-virtual) build trên đúng seam, không phải facade tay nặn. UI mới sống **song song** console cũ, không đụng `ui/server.py` (DEC-6). Tự kiểm: contract-seam test khẳng định UI đọc `ui_payload`, không đọc `payload`.

**B6 — Reliability (đang/sẽ).** `replay.py` mô phỏng đúng 3 việc transport thật phải làm: **dedup theo `event_id`**, **catch-up theo Last-Event-ID** (`events_after`), **resync khi rớt khỏi ring** (`needs_resync`). Build UI trên cái này là *honest* vì reality (at-least-once, drop giữa stream) được inject thật. PENDING: đưa các đảm bảo này vào transport production + wire authz enforcement.

## 4. Class & biến kiểm soát (cái neo)

| Neo | Ở đâu | Vì sao quan trọng |
|---|---|---|
| `RuntimeEvent` (payload vs ui_payload) | `control/events.py:113` | một hình dạng cho mọi event; tách thô/đã-mask |
| `EventTypeRegistry.assert_known` | `control/event_registry.py:47` | allowlist — không ai tự chế tên event |
| `Redactor.apply` (không mutate) | `control/redaction.py:65` | biên an toàn secret trước UI/SSE |
| `EventEmitter.emit_event` | `control/emitter.py:53` | đường publish duy nhất: gate→seq→redact→fan-out |
| `is_permission_escalating` / `command_needs_human_checkpoint` | `control/authz.py:29,43` | bắt leo quyền; ép permission-edit cần human |

Envelope: một shape, tách thô khỏi đã-mask (`ui_payload` là `None` cho tới khi Redactor fill):

```python
# control/events.py:113
@dataclass(frozen=True)
class RuntimeEvent:
    event_type: str
    session_id: str
    actor: Actor
    trace: TraceContext
    redaction: RedactionInfo
    ...
    seq: int = 0
    payload: dict[str, Any] = field(default_factory=dict)        # thô, nội bộ
    ui_payload: dict[str, Any] | None = None                     # đã mask, cho UI/SSE
```

Registry chặn tên tự chế — emitter gọi `get()` trước khi publish:

```python
# control/event_registry.py:47
def assert_known(self, event_type: str) -> None:
    if event_type not in self._specs:
        raise ControlContractError(
            f"Unknown event_type: {event_type!r}. Declare it in runtime_event_types.yaml."
        )
```

Redactor: mask đệ quy (dict AND list), trả **bản sao**, gốc không đổi:

```python
# control/redaction.py:65
def apply(self, event: RuntimeEvent, *, level: str | None = None) -> RuntimeEvent:
    ui_payload, fields = self.redact(event.payload)   # event.payload KHÔNG bị sửa
    info = RedactionInfo(level=level or event.redaction.level,
                         has_secret=bool(fields), redacted_fields=tuple(fields))
    return replace(event, ui_payload=ui_payload, redaction=info)
```

EventEmitter: bốn bước, đúng thứ tự, raise trước khi fan-out nếu type lạ:

```python
# control/emitter.py:53
def emit_event(self, event: RuntimeEvent) -> RuntimeEvent:
    spec = self._registry.get(event.event_type)                          # 1. gate
    staged = event if event.seq else replace(event, seq=self._seq.next(event.session_id))  # 2. seq
    final = self._redactor.apply(staged, level=spec.visibility)          # 3. redact
    for sink in self._sinks:                                             # 4. fan-out
        sink.emit(final)
    return final
```

Authz predicate (DEC-8): permission-edit cần human checkpoint kể cả dưới trust-O — quyết từ **registry**, không từ claim issuer:

```python
# control/authz.py:43
def command_needs_human_checkpoint(command_type: str, registry: CommandTypeRegistry) -> bool:
    return registry.requires_permission(command_type) in PERMISSION_EDIT_PERMISSIONS
```

## 5. Invariant của phase

- **I16 — secret chết ở biên.** `Redactor.apply()` mask ~14 secret key (`api_key`, `token`, `authorization`, `cookie`, …; `control/redaction.py:16`) đệ quy qua dict + list, **không mutate** `payload` gốc. Mọi đường tới UI/SSE chỉ phát `ui_payload`. Nếu `ui_payload` thiếu, gateway **không** fallback về raw (`fake_control_server.py:101`: `ui = {}`, không lấy raw).
- **I17 — attribution ≠ authz.** `issued_by`/`Actor` = tự khai (audit/trail), KHÔNG phải quyền (`commands.py:31`). `is_permission_escalating` bắt cờ `can_*` False→True; `command_needs_human_checkpoint` ép `UpdateAgentPermission`→`can_modify_permissions` cần human `RuntimeCheckpoint` kể cả dưới trust-O. **Enforcement hoãn** — predicate có, call-site (`command_bridge`) chưa wire (`control/authz.py:7-10`).
- **Contracts no-I/O above kernel.** `control/` chỉ là dataclass + validation; transport/storage sống sau `control/ports.py:EventSinkPort`. Đổi sang Kafka = sink mới, không đổi caller (`emitter.py:28` `BusEventSink`).
- **UI đọc ui_payload, không đọc raw.** `build_snapshot` whitelist field scalar và copy dict free-form **chỉ** từ `ui_payload` đã redact (`snapshot.py:14`, F2/C1) — một snapshot không bao giờ mang secret.
- **Registry là cổng tên.** Không module nào publish/accept một tên không khai trong YAML (`event_registry.py:47`, `command_registry.py:43`).
- **Allowlist visibility trên wire.** Chỉ event `public`/`ui_safe` ra dây — event `internal`/`restricted` (dù có `ui_payload`) KHÔNG leak (`fake_control_server.py:99`, review I1). Đây là *allowlist*, không phải *denylist*: chặn 'secret' thôi sẽ để lọt `internal`.
- **Checkpoint một chiều.** `RuntimeCheckpoint` khởi `waiting` rồi chỉ chuyển sang một terminal status (`approved`/`rejected`/`expired`/`auto_approved`); `with_status` từ chối re-resolve (`checkpoint.py:57-68`). Không có "duyệt lại" một gate đã đóng.
- **Ack hai trạng thái + lý do bắt buộc.** `CommandAck.status` chỉ `received`/`rejected` (biên nhận đồng bộ; outcome `accepted`/`applied` tới sau qua SSE). Một `rejected` không nói lý do là *lỗ contract* → `__post_init__` raise nếu thiếu `rejection_reason` (`commands.py:109-134`). Cùng tinh thần với `IssuedBy(type='human')` bắt buộc `user_id`.
- **Idempotency.** `RuntimeCommand` mang `idempotency_key` bắt buộc (`parse_command` raise nếu rỗng, `commands.py:162`); fake dedup theo `(session_id, idempotency_key)` để "apply exactly once" dù client retry (`fake_control_server.py:140-153`, F9).

## 6. Pitfall / bug sẽ gặp

**Triệu chứng → Nguyên nhân → Cách tránh**

- **Secret xuất hiện trong UI/Inspector.** → UI (hoặc snapshot) đọc `payload` thô thay vì `ui_payload`. → Luôn đọc `ui_payload`; trong fold whitelist field + copy dict free-form chỉ từ redacted view. `control/snapshot.py:152` (`_fields` ưu tiên `ui_payload`), `:252,:268,:306` (acceptance/context_packet/checkpoint payload chỉ lấy từ `redacted`).

- **Một agent "tự khai O" rồi leo quyền.** → Tin `issued_by`/`Actor` như authz. → Authz quyết bởi `requires_permission` + checkpoint, không bởi claim. `UpdateAgentPermission` luôn cần human checkpoint. `control/commands.py:31`, `control/authz.py:43`. (Nhớ: enforcement call-site còn PENDING — đừng tưởng predicate tự chặn.)

- **Module tự chế tên event → mất sink/replay/visibility.** → Bỏ qua registry, gọi `bus.publish("agent.whatever", ...)` trực tiếp. → Mọi publish đi qua `EventEmitter.emit_event`; nó gọi `registry.get()` raise trước khi fan-out. `control/emitter.py:56`, `control/event_registry.py:47`.

- **UI "chạy" trên fake nhưng vỡ khi đấu backend thật.** → Fake là facade tay nặn, khác shape thật → seam đúng "by-discipline", lỗ. → Fake PHẢI reuse `control/` (cùng `Redactor`, `parse_command`, `build_snapshot`); 2 shape thiếu (`TaskLoopSnapshot`/`CommandAck`) tạo dataclass trước UI. `tools/fake_control_server.py:5-6,32-39` (DEC-6).

- **Client mất thứ tự / không resync được.** → Emitter bỏ bước seq, hoặc transport không hỗ trợ Last-Event-ID. → `EventEmitter` stamp `seq` đơn điệu per-session (`SessionSeq`); buffer dedup theo `event_id`, `events_after(seq)` catch-up, `needs_resync` báo rớt-khỏi-ring. `control/emitter.py:57`, `control/events.py:193`, `control/replay.py:61,68`.

- **Resolve checkpoint hai lần / phantom Approval modal.** → Cho phép re-resolve checkpoint, hoặc snapshot vẫn ship `waiting` sau khi stream đã báo approve. → `RuntimeCheckpoint.with_status` chỉ cho `waiting`→terminal (`checkpoint.py:57`); `build_snapshot` resolve gate khi gặp `approval.approved/rejected` (`snapshot.py:324`).

## 7. Definition of Done

Test thật (đã có, đang xanh):

- `tests/test_control_contracts.py` (19 test) — envelope/command/checkpoint/permission validate; object sai không dựng được.
- `tests/test_control_emitter.py` (6 test) — gate→seq→redact→fan-out; type lạ raise trước publish; `BusEventSink` bridge.
- `tests/test_fake_control_server.py` (19 test) — snapshot không secret; stream chỉ phát `ui_payload`; token authz; idempotency; resync/catch-up; visibility allowlist.
- `tests/test_authz_attribution.py` (7 test) — `is_permission_escalating` (False→True), `command_needs_human_checkpoint` (DEC-8/I17).
- `tests_audit/test_acceptance_evidence_adversarial.py` (3 test) — gate evidence-typed adversarial (cross-ref Phase 6 / DEC-7).
- Phụ trợ đã có: `tests/test_control_snapshot.py`, `tests/test_acceptance_gate.py`; UI có `ui/control-plane/src/test/contract-seam.test.ts` (UI chỉ đọc `ui_payload`).

PENDING — **chưa có DoD** (đừng coi là done):

- **Authz enforcement** — `command_bridge` (call-site áp `requires_permission` + ép human checkpoint) **vắng** trên branch (DEC-7/DEC-8). Predicate có test; *đường thực thi* chưa.
- **Live transport là default** — supervisor emitter opt-in, default `None` (`supervisor/graph.py:48`); envelope chưa là đường mặc định của runtime live.
- **Command lifecycle thật** (`command.accepted`/`applied` end-to-end) + **reliability production** (at-least-once, resync ngoài fake) — thiết kế trong `docs/spec/active/E21-realtime-control-plane/`, chưa ship.

## 8. Vì sao tổ chức thế này giúp kiểm soát

Bốn quyết định ghép lại thành "realtime control mà không rò secret / không leo quyền":

1. **Contracts-first.** Một envelope (`RuntimeEvent`) + hai allowlist (event/command registry) nghĩa là *mọi thứ chảy qua control plane đều có hình dạng biết trước và tên hợp lệ*. Bug "module tự chế event" hay "payload thiếu field" bị chặn ở `__post_init__`/`assert_known`, không phải ở review.

2. **Redact-at-boundary.** Secret chết ở `Redactor.apply` — một hàm, một chỗ, không mutate gốc. UI đọc `ui_payload`. Không có "đừng quên mask chỗ này" rải khắp code; an toàn secret là *thuộc tính của biên*, không phải kỷ luật của từng dev.

3. **Authz ≠ attribution.** Tách "ai tự khai đã làm" khỏi "ai được phép" làm cho việc leo quyền *không khả thi bằng cách nói dối*. Permission-edit luôn cần human checkpoint — cái neo cuối cùng vẫn là con người, kể cả dưới trust-O.

4. **Fake-by-construction (DEC-6).** Vì fake reuse đúng `control/`, UI build trên đúng seam thật. "Drop-in khi đấu nối" được bảo đảm *bằng cấu trúc*, không bằng lời hứa — đổi backend là đổi URL.

Bài học rút ra: **kiểm soát một hệ realtime không đến từ thêm checkpoint, mà từ thu hẹp số chỗ một thứ nguy hiểm có thể xảy ra.** Một envelope, một đường publish, một biên redact, một định nghĩa authz — mỗi thứ là *một* chỗ phải đúng, không phải N chỗ phải nhớ. Và hãy trung thực: predicate authz có nhưng enforcement chưa wire; envelope tồn tại nhưng chưa là đường mặc định của runtime live. Tổ chức tốt làm cho phần còn thiếu *thấy được* và *cắm vào được* — không phải giả vờ đã xong.

---
*Điều hướng: ← [Phase 6](phase-6-roles-delegation.md) · → [Index](README.md)*
