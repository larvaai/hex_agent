# Case 02 — `PolicyGate`: handler early-exit (chặn TRƯỚC khi tới core)

> Một ConcreteHandler tối giản và tập trung, thể hiện quyết định cốt lõi nhất của CoR: **handle** (return ngay) hay **forward** (gọi `nxt`). Đây là dạng "gate" thuần — không modulate, không hậu xử lý, chỉ lọc/chặn sớm.

---

## 1. Bối cảnh trong hex_agent

`PolicyGate` là deny-list chokepoint: nếu một tool nằm trong tập `deny`, nó **trả về envelope thất bại ngay** và **không gọi `nxt`** — nghĩa là tool bên trong (và mọi middleware nằm sau nó) không bao giờ chạy. Nếu không nằm trong deny-set, nó forward request xuống chuỗi.

- Cài đặt handler: `middleware/policy.py:9-22`.
- Hành vi short-circuit được kiểm chứng bằng test: `tests/test_middleware.py:15-23` (`test_policy_blocks_before_core`) — khẳng định `r["ok"] is False`, `r["metadata"]["policy_block"] is True`, kernel vẫn đóng dấu trace-id ngay cả khi short-circuit, và callback `on_block` ghi nhận tool bị chặn (`blocked == ["echo"]`).
- Gate được wire ở `core/bootstrap.py:38-42` khi config bật policy.
- Cái mà gate ngăn không cho chạm tới chính là `core(req)` — executor thật ở `core/kernel.py:152-177`.

Vấn đề thật: cần một điểm chặn an toàn (fail-closed) để một số tool không bao giờ thực thi, đặt **trước** logic nghiệp vụ, không nhúng kiểm tra này rải rác trong từng tool.

## 2. Trích đoạn code thật

`middleware/policy.py:9-22`:

```python
class PolicyGate:
    def __init__(self, *, deny: set[str] | None = None,
                 on_block: Callable[[ToolRequest], None] | None = None) -> None:
        self.deny = set(deny or ())
        self.on_block = on_block

    def __call__(self, request: ToolRequest, nxt) -> dict[str, Any]:
        if request.name in self.deny:
            if self.on_block:
                self.on_block(request)
            return {"ok": False, "capability": request.name, "feature": None, "data": {},
                    "error": f"Blocked by policy: {request.name}", "metadata": {"policy_block": True}}
        return nxt(request)
```

Test cố định hành vi short-circuit (`tests/test_middleware.py:15-23`):

```python
def test_policy_blocks_before_core():
    k = build_kernel(ECHO)
    blocked = []
    k.use(PolicyGate(deny={"echo"}, on_block=lambda req: blocked.append(req.name)))
    r = k.execute_tool("echo", {"a": 1})
    assert r["ok"] is False
    assert r["metadata"]["policy_block"] is True
    assert "task_id" in r["metadata"]  # kernel stamps trace ids even on short-circuit
    assert blocked == ["echo"]
```

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò trong CoR | Thành phần trong hex_agent |
|---|---|
| `ConcreteHandler` (gate) | `PolicyGate` — `middleware/policy.py:9-22` |
| điểm quyết định | `request.name in self.deny` — `policy.py:16` |
| handle-here (return, dừng chuỗi) | `return {... "policy_block": True}` — `policy.py:19-20` |
| forward sang handler kế tiếp | `return nxt(request)` — `policy.py:21` |
| hook quan sát quyết định | `self.on_block(request)` — `policy.py:17-18` |
| receiver bị bảo vệ (không bao giờ chạm khi bị chặn) | `core(req)` executor — `core/kernel.py:152-177` |

## 4. Bản rút gọn chạy được

File: [`policy_gate_handler.py`](./policy_gate_handler.py) — chạy `python3 policy_gate_handler.py`.

Nó mô phỏng:
- `PolicyGate` distill gần như nguyên văn bản thật (kèm `on_block`).
- `MiniKernel` + `_wrap` = hạ tầng chuỗi tối giản đủ để chứng minh: khi gate chặn, `core` không chạy.
- Bằng chứng then chốt: `admin_tool` ghi vào list `side_effects` mỗi khi thực thi; sau khi bị gate chặn, `side_effects == []` → tool thật sự không chạy (giống cách `tests_audit/.../test_core_edges_rigor.py:82-102` dùng `ExplodingTool` để chứng minh inner tool không bao giờ bị gọi).
- Ba màn: (1) tool bị chặn → short-circuit, (2) tool an toàn → forward, (3) đối chứng bỏ gate khỏi chuỗi → tool nguy hiểm chạy.

Đã **lược bỏ**: `ToolRequest` schema (thay bằng dict), `EventBus`/đóng dấu trace-id, `CapabilityResult`. Trọng tâm giữ nguyên: quyết định handle-vs-forward và đặc tính early-exit.

Đối chứng "không dùng pattern": phần [3] dựng một kernel KHÔNG có gate; request đi thẳng tới core và side-effect ("xóa prod-db") xảy ra — cho thấy chính handler early-exit trong chuỗi là thứ bảo vệ core.

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Vị trí trong chuỗi rất quan trọng.** Gate phải đứng trước các handler có side-effect; nếu đặt sai chỗ (sau một middleware đã gọi tool), chặn trở nên vô nghĩa.
- **Deny-list dễ lỗi thời.** Một tool mới nguy hiểm có thể bị quên thêm vào deny-set; deny-list là fail-closed cho cái đã biết, không cho cái chưa biết.
- **Khi cần logic phân quyền phức tạp** (theo vai trò, theo amount, theo ngữ cảnh động) thì một gate boolean đơn giản không đủ — có thể cần policy engine riêng thay vì nhồi vào một handler.
- **Khi mọi handler đều phải chạy** (không bao giờ chặn) thì đây là Pipeline, không phải CoR — dùng gate ở đây chỉ gây nhầm lẫn.

## 6. Câu hỏi tự kiểm tra

1. Điều gì xảy ra với các middleware đăng ký **sau** `PolicyGate` khi một tool bị chặn? Vì sao?
2. `PolicyGate` không bao giờ sửa result envelope của tool. Vậy nó khác `CondenseResult` ([case 03 — modulate-and-forward](../03_condense_fail_open/)) ở chỗ nào về hành vi CoR?
3. Test `test_policy_blocks_before_core` khẳng định `"task_id" in r["metadata"]` ngay cả khi short-circuit. Vì sao kernel vẫn đóng dấu trace-id dù gate đã trả về sớm? (Gợi ý: xem `core/kernel.py:210-213`.)
