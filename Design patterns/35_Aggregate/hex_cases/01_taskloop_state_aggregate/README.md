# Case 01 — TaskLoopState: Aggregate cho một lượt chạy multi-agent

> Distill từ `supervisor/state.py` trong `hex_agent`. Liên hệ bài học gốc: `35_Aggregate.md`.

---

## 1. Bối cảnh trong hex_agent

Khi một task được giao cho nhiều agent cùng giải (Epic E10), hệ thống cần một **"Blackboard"
tuần-tự-hoá-được** đại diện cho toàn bộ trạng thái của một lượt chạy: đã chọn team nào, đang ở
round mấy, các tiêu chí nghiệm thu (acceptance check) đã đạt chưa, các lượt làm việc
(agent turn) và artifact sinh ra. Vòng lặp điều phối (`o_decide`) **chỉ đọc Blackboard này**,
không bao giờ đọc raw session của từng worker (xem docstring `supervisor/state.py:1-6`).

Vấn đề thật cần một *consistency boundary*:

- "Một lượt chạy được coi là **FINISHED** chỉ khi **tất cả** acceptance check đã thoả" — nếu
  luật này rải ra nhiều service thì mỗi nơi một phiên bản, dễ lệch.
- "Một acceptance check chỉ tính là **đạt** khi `status == passed` VÀ có ít nhất 1 evidence" —
  bất biến cục bộ, thấy ở `supervisor/state.py:35-37`.
- State phải checkpoint được xuống SQLite/S3, nên chỉ chứa primitive (docstring dòng 4-6).

`TaskLoopState` (`supervisor/state.py:80-111`) là class gom cụm `AcceptanceCheck` +
`AgentTurn` + `artifacts` và cung cấp các method gác bất biến đó: `all_accepted()`,
`acceptance_by_id()`, `is_terminal`, `acceptance_snapshot()`.

File đã mở kiểm chứng: `/Users/uspro/Desktop/namnson/hex_agent/supervisor/state.py` (146 dòng).

---

## 2. Trích đoạn code thật

`supervisor/state.py:96-111` — phần "trái tim" của Aggregate Root:

```python
    # ── helpers ──────────────────────────────────────────────────────────────
    def add_artifact(self, artifact_id: str, payload: dict[str, Any]) -> None:
        self.artifacts[artifact_id] = payload

    def acceptance_by_id(self, check_id: str) -> AcceptanceCheck | None:
        return next((c for c in self.acceptance_checks if c.id == check_id), None)

    def all_accepted(self) -> bool:
        return bool(self.acceptance_checks) and all(c.is_satisfied for c in self.acceptance_checks)

    @property
    def is_terminal(self) -> bool:
        return TaskLoopStatus(self.status) in TERMINAL

    def acceptance_snapshot(self) -> tuple[tuple[str, str, int], ...]:
        """A comparable snapshot of acceptance progress (for the loop guard)."""
        return tuple((c.id, c.status, len(c.evidence_ids)) for c in self.acceptance_checks)
```

Và bất biến cục bộ của internal entity, `supervisor/state.py:35-37`:

```python
    @property
    def is_satisfied(self) -> bool:
        return self.status == "passed" and bool(self.evidence_ids)
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò trong Aggregate (Lesson 35) | Thành phần code thật (`supervisor/state.py`) |
|---|---|
| **Aggregate Root (AR)** | `TaskLoopState` (dòng 80-111) — class duy nhất bao cụm |
| **Internal Entity** | `AcceptanceCheck` (28-49), `AgentTurn` (52-77) — chỉ AR quản lý |
| **Invariant** | `all_accepted()` (102-103), `is_satisfied` (35-37), tập `TERMINAL` (25) |
| **Public API (Tell-Don't-Ask)** | `add_artifact()` (96-97) — cổng duy nhất ghi artifact |
| **Query method** | `acceptance_by_id()` (99-100), `is_terminal` (105-107) |
| **Domain event / snapshot** | `acceptance_snapshot()` (109-111) — fact so sánh được cho loop guard |
| **Biên giới persistence (Outbox-like)** | `encode/decode_taskloop_state()` (114-145) |
| **State machine** | `TaskLoopStatus` enum (14-22) + `TERMINAL` (25) |

---

## 4. Bản rút gọn chạy được

File: [`taskloop_state_aggregate.py`](./taskloop_state_aggregate.py) — chạy:
`python3 taskloop_state_aggregate.py` (exit 0, không traceback).

**Mô phỏng gì:** toàn bộ vòng đời một lượt chạy — tạo → chọn team → ghi turn/artifact →
pass dần các acceptance check (bắt buộc kèm evidence) → finish (chỉ khi `all_accepted`) →
khoá mutation khi terminal → encode/decode round-trip giữ nguyên consistency. Có demo 10 bước
in narration tiếng Việt, kèm `assert` chứng minh từng bất biến.

**Lược bỏ / fake:** thay checkpoint SQLite/S3 bằng round-trip qua `dict` trong bộ nhớ
(`encode/decode`). Bỏ `tool_results`, `max_rounds` chi tiết và một số field telemetry.

**Cố ý siết chặt hơn code thật:** code thật dùng `@dataclass` với field **public** (ví dụ
`status` có thể gán thẳng). Bản distill đặt `_status`, `_round_no`, `_acceptance_checks`...
thành private và chỉ cho đổi qua command method (`select_team`, `pass_check`, `finish`,...),
đồng thời thêm bảng `_LEGAL_ADVANCE` khoá chuyển trạng thái. Đây là cách *minh hoạ thuần*
nguyên lý "invariant inside AR" / "invalid state should be impossible" của Lesson 35 (xem mục 5).

**Đối chứng:** class `AnemicLoop` (bước 10) — data bag phơi field public; ta set thẳng
`status = "finished"` dù 0 acceptance check pass → invariant bị bỏ qua **im lặng** (data
corruption). Đây chính là Vi phạm A & D mà bài gốc cảnh báo.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Boilerplate:** mỗi mutation phải có command method + tiền điều kiện + (đôi khi) event.
  Code thật của hex_agent **chấp nhận đánh đổi ngược lại**: để field public cho gọn vì state
  này được điều phối bởi đúng một vòng lặp (`o_decide`) — rủi ro "ai cũng sửa" thấp, mà lại
  cần serialize/checkpoint dễ. Bài học: mức độ siết encapsulation nên tỷ lệ với số lượng nơi
  có quyền mutate.
- **Đừng nhét invariant eventual vào AR:** ví dụ "tổng số task hoàn thành của user ≤ hạn mức"
  KHÔNG thuộc `TaskLoopState` — đó là check xuyên-aggregate, xử lý qua event sau (Vernon rule d).
- **Đừng để aggregate phình:** nếu một lượt chạy phải load hàng nghìn turn/artifact, cân nhắc
  tách hoặc phân trang (heuristic ~50 object của Lesson 35).
- CRUD thuần / read-model thì không cần aggregate (dùng projection — xem `control/snapshot.py`).

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `all_accepted()` trả `False` khi danh sách acceptance check **rỗng**? (Gợi ý:
   `bool(self.acceptance_checks) and ...` ở `state.py:103` — "không có tiêu chí" khác "đã đạt").
2. `acceptance_snapshot()` trả về tuple gồm `(id, status, len(evidence_ids))`. Tại sao loop
   guard cần một snapshot **so sánh được** thay vì chỉ một cờ boolean tiến độ?
3. Trong bản distill, điều gì xảy ra nếu gọi `record_turn()` sau khi `finish()`? Bất biến nào
   chặn nó, và ở code thật bất biến tương ứng nằm ở đâu (gợi ý: `is_terminal`, `state.py:105-107`)?
