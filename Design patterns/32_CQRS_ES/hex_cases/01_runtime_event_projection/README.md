# Case 01 — Runtime Event Projection (CQRS Read Model qua "fold events")

> Distill từ `control/snapshot.py` trong hex_agent. File chạy được: [`runtime_event_projection.py`](./runtime_event_projection.py).

Đây là ví dụ **CQRS rõ nhất** trong hex_agent: events do supervisor publish (write side) được *chiếu* (project) thành một read model tối ưu cho UI. UI **query thẳng** snapshot, không bao giờ chạm tới write side. `build_snapshot` chính là **projection**, và logic fold là sự **derive state từ events** một cách tường minh.

---

## 1. Bối cảnh trong hex_agent

UI (Agent Graph + Inspector) cần một "ảnh hiện trạng": agent nào đang chạy/xong/chờ, orchestrator vừa quyết định gì, có checkpoint nào đang chờ duyệt. Nhưng nguồn sự thật mà supervisor phát ra lại là **một chuỗi event** `loop.team_composed` → `loop.decision` → `loop.turn` → `loop.tool` → `loop.finished`… (cộng `checkpoint.reached`, `approval.approved`).

Nếu UI tự suy diễn từng event thì mỗi component phải tự giữ state, dễ lệch nhau. Giải pháp CQRS: **một projection duy nhất** fold cả chuỗi event thành `TaskLoopSnapshot` — đúng một read model, UI chỉ việc vẽ.

Vấn đề thật được giải, kiểm chứng tại file:
- `control/snapshot.py:189-365` — `build_snapshot()`: vòng fold tuyến tính, order-sensitive, dựng `agents` / `checkpoints` / `orchestrator` / `status` hoàn toàn từ events.
- `control/snapshot.py:36-134` — `AgentView` / `TaskLoopSnapshot`: read model `frozen=True` (bất biến) + `as_dict`/`from_dict`.
- `control/snapshot.py:140-149` — bảng `_STATUS_BY_EVENT` ánh xạ event-type → status session; terminal không bị ghi đè.
- `control/events.py:113-190` — `RuntimeEvent` (envelope bất biến, `frozen=True`), nguồn của `event_type` + `ui_payload` mà fold đọc.

Hai lựa chọn quan trọng (ghi trong docstring `snapshot.py:1-17`):
- Fold `loop.*`, **không** fold `agent.*` (red-team F1) — vì `loop.*` mới là cái supervisor thực sự phát.
- Chỉ đọc `ui_payload` (đã redact), **không** đọc `payload` raw cho field free-form (F2) — snapshot không bao giờ mang secret.

---

## 2. Trích đoạn code thật

Trái tim của projection — derive trạng thái node bằng fold rồi quyết định status (`control/snapshot.py:339-352`):

```python
running = {c["agent_id"] for c in latest_calls} - turned
agents = tuple(
    AgentView(
        agent_id=aid,
        role=meta[aid]["role"],
        status=("done" if aid in turned else "waiting" if aid in waiting
                else "running" if aid in running else "pending"),
        round_no=meta[aid]["round_no"],
        allowed_tools=meta[aid]["allowed_tools"],
        last_output_summary=meta[aid]["last_output_summary"],
        context_packet=meta[aid]["context_packet"],
        permission=meta[aid]["permission"],
    )
    for aid in order
)
```

Quy tắc "terminal status không bị marker sau ghi đè" (`control/snapshot.py:231-233`):

```python
# session status: never let a terminal status be overwritten by a later marker.
if status not in _TERMINAL_STATUS and et in _STATUS_BY_EVENT:
    status = _STATUS_BY_EVENT[et]
```

Resolve checkpoint khi gate được duyệt (`control/snapshot.py:324-337`):

```python
elif et in ("approval.approved", "approval.rejected"):
    cid = str(view.get("checkpoint_id", ""))
    entry = cp_index.get(cid)
    new_status = "approved" if et == "approval.approved" else "rejected"
    if entry is not None:
        entry["status"] = new_status
    aid = str(view.get("agent_id") or (entry.get("agent_id") if entry else "") or "")
    waiting.discard(aid)   # agent hết bị gate chặn
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò CQRS + ES | Trong hex_agent (file:line) | Trong bản distill (`runtime_event_projection.py`) |
|---|---|---|
| **Domain Event** (past-tense fact) | `RuntimeEvent`, `control/events.py:113-190` | `RuntimeEvent` (frozen) |
| **Command** (ý định) | `RuntimeCommand` ở gateway (ngoài file này) | mô phỏng bằng list event dựng sẵn |
| **Projection / Projector** | `build_snapshot()`, `control/snapshot.py:189-365` | `build_snapshot()` |
| **Read Model** (materialized view) | `TaskLoopSnapshot` / `AgentView`, `snapshot.py:36-134` | `TaskLoopSnapshot` / `AgentView` (frozen) |
| **Query** | UI đọc thẳng snapshot (không replay aggregate) | truy cập field của `snap` sau khi fold |
| **fold(events) = state** | vòng `for ev in events` trong build_snapshot | vòng `for ev in events` |
| **Event versioning / redaction-aware** | đọc `ui_payload`, `schema_version` (`events.py`) | đọc `ui_payload` qua `_fields()` |

---

## 4. Bản rút gọn chạy được

File [`runtime_event_projection.py`](./runtime_event_projection.py) **chỉ dùng stdlib**, mô phỏng:
- 10 event `loop.*` serialize sẵn (đứng thay cho những gì supervisor publish).
- `build_snapshot()` giữ đúng cấu trúc fold thật: `see()`, các set `turned`/`waiting`/`running`, `cp_index`, quy tắc status `done > waiting > running > pending`, terminal không bị ghi đè, approval resolve checkpoint.
- `AgentView` / `TaskLoopSnapshot` `frozen=True` để chứng minh read model bất biến.

Đã **lược bỏ** (so với code thật) để giữ self-contained:
- Toàn bộ `actor` / `trace` / `seq` / nhiều scalar field của `RuntimeEvent` (giữ lại đúng phần fold dùng tới).
- Phần whitelist scalar và copy `context_packet`/`permission` từ redacted (giữ tinh thần "chỉ đọc ui_payload").
- SQLite / SSE / HTTP / Redactor đầy đủ — không liên quan tới vai projection.

Các đối chứng & assert trong file:
- **ĐỐI CHỨNG `MutableBoard`**: set state trực tiếp (anti-CQRS) — event tới sai thứ tự (turn trước decision) khiến node kẹt sai `running` dù đã `done`; cùng tập event đó, `build_snapshot` vẫn cho `done` vì derive từ cả tập.
- **assert** state agents/checkpoints/status derive đúng; fold deterministic (rebuild cho cùng kết quả); `AgentView` frozen không mutate được.

Chạy:
```bash
python3 runtime_event_projection.py   # exit 0, in narration từng bước
```

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Eventual consistency**: read model lag sau write. Trong hex_agent là chấp nhận được (UI), nhưng nếu cần read-your-writes tức thì thì projection async không hợp.
- **Fold chi phí O(n) theo số event**: chuỗi event rất dài → cần snapshot/cache (hex_agent dùng ring buffer 2048, xem `control/replay.py`). Không nên fold-từ-đầu mỗi request nếu stream khổng lồ.
- **Không phải full Event Sourcing**: hex_agent **không** rebuild *trạng thái nghiệp vụ* từ event — nguồn sự thật là LangGraph SQLite (`supervisor/state.py`). Projection ở đây chỉ phục vụ view. Đừng nhầm "fold để vẽ UI" với "event store là system-of-record".
- Với CRUD đơn giản (1 form admin), tách write/read + projection là over-engineering.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `build_snapshot` ưu tiên đọc `ui_payload` thay vì `payload`? Nếu đọc nhầm `payload` thì rủi ro gì (gợi ý: red-team F2)?
2. Trong quy tắc `done > waiting > running > pending`, vì sao `turned` (đã `loop.turn`) phải thắng `running` (trong decision mới)? Đối chứng `MutableBoard` trong file minh hoạ điều gì khi event tới sai thứ tự?
3. `TaskLoopSnapshot` là *derived* hay *primary*? Nếu xoá toàn bộ snapshot đang cache nhưng vẫn còn chuỗi event, hệ thống có dựng lại được view không? Vì sao đó **không** đồng nghĩa hex_agent là full Event Sourcing?
