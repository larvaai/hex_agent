# Case 03 — DelegationManager: Facade `delegate()` trên policy + registry + sessions + store + events

> **Một method `delegate()` gói trọn vũ điệu uỷ thác 6 subsystem với 3 nhánh lỗi, thay vì bắt client tự dựng 10+ bước.**

---

## 1. Bối cảnh trong hex_agent

Khi agent cha muốn uỷ thác một việc cho agent con, hệ thống phải làm tuần tự rất nhiều thứ: validate policy với session cha → ghi `start` vào store → publish event `delegation.started` → resolve target string thành handler từ registry → tạo child session có scoping năng lực → chạy handler với một `progress_sink` callback (mỗi bước ghi store rồi publish `delegation.progress`) → khi xong thì đóng child (`complete_task`/`fail_task`) → `finish` vào store → publish `delegation.finished`. Và có **3 nhánh lỗi** phải xử lý khác nhau (policy reject, tạo child fail, handler fail).

`DelegationManager.delegate()` là "sequential delegation chokepoint" gói toàn bộ:

- `delegation/manager.py:1` — `"""Sequential delegation chokepoint: policy, child session, progress, events, result."""`
- `delegation/manager.py:19-32` — `__init__(registry, sessions, store, policy)` và `registry.freeze()`.
- `delegation/manager.py:45-61` — `_finish()`: `store.finish` rồi publish `delegation.finished` (store trước, event sau).
- `delegation/manager.py:63-192` — `delegate()`: điều phối 6 subsystem; nhánh policy-reject (79-104), nhánh tạo-child-fail (119-140), nhánh handler-fail (178-185).
- `delegation/manager.py:142-157` — `progress_sink`: contract callback, `store.append_progress` trước, publish event sau.

Client (ví dụ node `delegate` trong graph, hoặc supervisor loop `supervisor/loop.py`) chỉ gọi `delegate(parent, target, spec)` — **không** import `DelegationPolicyEngine`, `DelegationRegistry`, `DelegationStorePort` hay `EventBus`.

## 2. Trích đoạn code thật

```python
# delegation/manager.py:63-104 (rút gọn) — entrypoint + nhánh policy-reject
def delegate(self, parent_session, target, spec, policy=None):
    if not parent_session.is_active:
        raise RuntimeError("Cannot delegate from an inactive parent session.")
    ...
    delegation_id = uuid.uuid4().hex
    requested_policy = policy or DelegationPolicy()
    try:
        active_policy = self.policy.validate(parent_session, requested_policy)
    except Exception as exc:
        request = DelegationRequest(delegation_id=delegation_id, ...)
        self.store.start(request)
        parent_session.kernel.events.publish("delegation.started", ...)
        return self._finish(parent_session, target,
                            DelegationResult(..., outcome="rejected", error=str(exc)))
    ...
```

```python
# delegation/manager.py:142-157 — progress_sink: store trước, event sau
def progress_sink(progress: DelegationProgress) -> None:
    if progress.delegation_id != delegation_id:
        raise ValueError("Progress delegation_id does not match the active request.")
    if progress.sequence > active_policy.max_steps:
        raise ValueError("Delegation progress exceeded max_steps.")
    self.store.append_progress(progress)   # source of truth first
    child.kernel.events.publish("delegation.progress", {...})
```

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Facade | Thành phần trong hex_agent | Trong bản distill `.py` |
|---|---|---|
| **Facade** | `DelegationManager.delegate()` — `delegation/manager.py:63` | `DelegationManager.delegate()` |
| Subsystem 1 — policy | `DelegationPolicyEngine.validate()` (`delegation/policy.py`) | `DelegationPolicyEngine` |
| Subsystem 2 — registry → handler | `DelegationRegistry.resolve()` (`delegation/registry.py`) | `DelegationRegistry` + `DelegationHandler` |
| Subsystem 3 — child session scoping | `SessionFactory.create_child()` (`core/session.py`) | `SessionFactory.create_child()` |
| Subsystem 4 — chạy handler | `DelegationPort.run()` (`core/ports.py`) | `DelegationHandler.run()` |
| Subsystem 5 — store (nguồn-sự-thật) | `DelegationStorePort` start/append/finish (`core/ports.py`) | `InMemoryDelegationStore` |
| Subsystem 6 — events | `EventBus.publish` started/progress/finished | `EventBus` |
| Contract callback | `progress_sink` (`delegation/manager.py:142`) | `progress_sink` |
| Quy mọi lỗi về 1 lối ra | `_finish()` (`delegation/manager.py:45`) | `_finish()` |
| Client | node `delegate` / supervisor loop | `demo()` gọi `mgr.delegate` |

## 4. Bản rút gọn chạy được

File: [`delegation_manager_facade.py`](./delegation_manager_facade.py) — chạy `python3 delegation_manager_facade.py`.

**Mô phỏng gì:**
- Giữ nguyên choreography 6 subsystem và **cả 3 nhánh lỗi** xử lý khác nhau, đều quy về `_finish()` để client luôn thấy một `DelegationResult` nhất quán.
- Giữ bất biến thứ tự event `started → progress* → finished` và quy ước "store trước, event sau" (assert kiểm chứng cả hai).
- Giữ scoping: `create_child` từ chối child xin năng lực ngoài scope cha → `PermissionError` → outcome `rejected`.
- `demo()`: (1) thành công; (2) policy reject; (3) target không tồn tại → failed; (4) handler nổ giữa chừng → failed nhưng vẫn đóng sổ; (5) đối chứng `delegate_without_facade` — client tự dựng vũ điệu, handler nổ làm `finish` không bao giờ chạy → audit trail rò rỉ, child treo.

**Lược bỏ gì (so với bản thật):**
- Schemas đầy đủ (`DelegationRequest/Result/Progress/Spec/Policy` ở `core/schemas.py`) → dataclass rút gọn.
- Hợp nhất artifact từ store + result, kiểm `parent_task_id` chéo (`delegation/manager.py:163-177`) → giản lược.
- **Chữ ký `SessionFactory.create_child()` bị giản lược:** bản thật (`core/session.py:148-157`) còn nhận thêm `user_request: str` (bắt buộc) và `context: dict | None` (tuỳ chọn) để dựng `TaskEnvelope` cho child; bản distill (`delegation_manager_facade.py:145-147`) **bỏ hai tham số này**, chỉ giữ `parent`, `delegation_id`, `target`, `requested_scope`. Bất biến scoping (`PermissionError` khi child xin năng lực vượt scope cha) được **giữ đúng**; phần lược chỉ là payload nhiệm vụ của child, không ảnh hưởng minh hoạ Facade.
- `call_context().event_fields()` lineage đầy đủ → field tối thiểu.
- Handler thật chạy qua LangGraph (`adapters/agents.py`) → `DelegationHandler` xác định, có cờ `blow_up`.

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Method dài, nhiều nhánh**: `delegate()` thật ~90 dòng. Đây là cái giá hợp lý của facade — nhưng nếu thêm nhiều outcome/subsystem nữa, nên tách thành các bước nhỏ (như hex_agent đã tách `_finish`, `_event_fields`).
- **Mediator vs Facade**: nếu các subsystem cần "nói chuyện" hai chiều với nhau (peer-to-peer) thì đó là Mediator, không phải Facade. `delegate()` chỉ điều phối một chiều client → subsystem nên đúng là Facade.
- **Khi cần can thiệp sâu** vào từng bước (custom progress handling), facade kín có thể vướng; lúc đó `progress_sink` là điểm mở rộng được thiết kế sẵn.
- **Uỷ thác đơn giản, không cần audit/scoping** thì facade nặng nề là thừa.

## 6. Câu hỏi tự kiểm tra

1. Vì sao `progress_sink` ghi `store.append_progress` **trước** rồi mới publish event? Nếu đảo thứ tự, điều gì có thể sai khi tiêu thụ event nhưng store chưa cập nhật?
2. Bước `[5]` cho thấy hậu quả khi client tự điều phối mà handler nổ giữa chừng. Facade thật bảo đảm "luôn `_finish`" bằng cấu trúc try/except nào (xem `delegation/manager.py:159-185`)?
3. Cả ba nhánh lỗi (rejected do policy, rejected/failed do tạo child, failed do handler) đều trả về cùng kiểu `DelegationResult`. Lợi ích của việc "một lối ra duy nhất" với client là gì?
