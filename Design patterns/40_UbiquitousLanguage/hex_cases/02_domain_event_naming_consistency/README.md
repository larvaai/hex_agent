# Case 02 — Domain event naming consistency (UL → Published Language)

> Flagship của Ubiquitous Language: event và metadata trong hex_agent được đặt tên bằng
> *ngôn ngữ nghiệp vụ*, không phải jargon kỹ thuật. UL chảy thẳng vào Published Language.

## 1. Bối cảnh trong hex_agent

Một control plane phát rất nhiều event cho UI / audit / replay. Nếu event tên kiểu
`agents_selected`, `job_queued`, `execution_done`, thì business expert đọc log chẳng hiểu
gì, và new dev không biết `agent_dispatched` khác `delegation.finished` ra sao. hex_agent
chọn đặt tên event theo *phase nghiệp vụ*, tiền tố mirror bounded context:

- Supervisor BC (Epic E10) phát `loop.team_composed`, `loop.decision`, `loop.turn`,
  `loop.parse_error` — xem [`supervisor/graph.py:103`](../../../../supervisor/graph.py),
  `:117`, `:122`, `:209`.
- Delegation BC phát `delegation.started`, `delegation.finished` kèm domain context
  (`outcome`, `artifact_count`) — xem [`delegation/manager.py:52-60`](../../../../delegation/manager.py)
  và `:91-94`.
- Ngay metadata cũng nói domain: [`control/events.py:23-25`](../../../../control/events.py)
  định nghĩa `ACTOR_TYPES = {human, agent, tool, system, runtime}` và
  `VISIBILITY_LEVELS = {public, ui_safe, internal, secret, restricted}` — không phải
  `debug/info/warn`.

## 2. Trích đoạn code thật

Event đặt tên theo phase nghiệp vụ — `supervisor/graph.py:103, 122`:

```python
state.status = TaskLoopStatus.TEAM_SELECTED.value
ctx.emit("loop.team_composed", {"selected": list(state.selected_agents)})
...
ctx.emit("loop.decision", {"round": state.round_no, "decision": decision.decision})
```

Delegation lifecycle event kèm domain semantics — `delegation/manager.py:52-60`:

```python
parent.kernel.events.publish(
    "delegation.finished",
    {
        **self._event_fields(parent, result.delegation_id, target),
        "outcome": result.outcome,
        "artifact_count": len(result.artifacts),
        "error": result.error,
    },
)
```

UL enforced bằng validation — `control/events.py:23-25, 37-43`:

```python
ACTOR_TYPES = frozenset({"human", "agent", "tool", "system", "runtime"})
VISIBILITY_LEVELS = frozenset({"public", "ui_safe", "internal", "secret", "restricted"})
...
def __post_init__(self) -> None:
    if self.type not in ACTOR_TYPES:
        raise ControlContractError(
            f"Actor.type must be one of {sorted(ACTOR_TYPES)}, got {self.type!r}.")
```

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò trong Ubiquitous Language | Thành phần hex_agent | Trong file distill |
|---|---|---|
| Event name = UL của producing BC | `loop.*`, `delegation.*` topics | `supervisor_run()`, `delegation_run()` |
| Published Language carries semantics | payload `outcome`, `artifact_count` | payload trong `bus.publish(...)` |
| Vocabulary metadata theo domain | `ACTOR_TYPES`, `VISIBILITY_LEVELS` | hằng cùng tên ở đầu file |
| UL enforced bằng validation | `Actor.__post_init__` → `ControlContractError` | `Actor.__post_init__` |
| Traceability event ↔ slice | tiền tố topic mirror BC + spec S10.x | `build_ul_map()` |
| Anti-pattern "dev jargon" (Ví dụ 2) | tên `agents_selected`, `job_queued` (KHÔNG dùng) | `_BANNED_JARGON`, `audit_event_naming()` |

## 4. Bản rút gọn chạy được

File: [`domain_event_naming_consistency.py`](domain_event_naming_consistency.py) — chạy:

```bash
python3 domain_event_naming_consistency.py
```

Nó **mô phỏng**: một EventBus in-memory; supervisor + delegation phát đúng các event UL của
hex_agent; `Actor` validate `type` theo `ACTOR_TYPES` (UL enforced); một bộ `audit_event_naming`
kiểm topic phải có dạng `<bc>.<phase-UL>` và phase thuộc vocabulary BC; và một UL map nối
event với phase/slice nghiệp vụ.

Nó **lược bỏ**: EventBus thật + SSE + Redactor + `RuntimeEvent` envelope đầy đủ (seq, trace,
ui_payload). Ở đây payload chỉ là dict thường, đủ để thấy event mang *domain context*.

Bất biến được `assert` chứng minh:
- mọi event hex_agent dùng đúng UL (`audit.consistent` True);
- `Actor(type='superuser')` bị từ chối — vocabulary là hợp đồng, không phải gợi ý;
- bộ event jargon (`agents_selected`, `job_queued`, `log_entry`) **bị audit bắt**.

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Phải thống nhất vocabulary trước**: đặt tên event bằng UL đòi hỏi đã có ngôn ngữ chung
  với business expert. Nếu domain chưa rõ (đang khám phá), ép naming sớm có thể đặt sai và
  phải rename — mà rename event là *Published Language*, đắt.
- **Tiền tố BC trong topic là một cam kết**: `loop.*` ngụ ý ranh giới BC supervisor. Khi
  refactor BC, topic phải đổi theo — nếu không, traceability vỡ. Đây là chi phí giữ topic
  mirror BC boundary.
- **Validation cứng (`ControlContractError`)** loại được event sai, nhưng cũng nghĩa là
  thêm một `ACTOR_TYPE`/`VISIBILITY_LEVEL` mới phải sửa enum + có thể vỡ test cũ.
- Khi nhẹ: prototype ngắn, một consumer duy nhất, không có business expert đọc log — lúc đó
  `info/debug` đơn giản là đủ.

## 6. Câu hỏi tự kiểm tra

1. Vì sao `delegation.finished` mang `artifact_count` và `outcome` trong payload lại quan
   trọng hơn việc chỉ phát một event rỗng `delegation_done`? Liên hệ "Published Language
   carries semantics".
2. Nếu đổi `loop.team_composed` → `loop.roster_built`, những nơi nào phải cập nhật cùng PR
   (gợi ý: test, docs, observability, replay)? Vì sao đây là *rename multi-phase* chứ không
   phải sửa-một-chỗ?
3. `Actor.__post_init__` ném lỗi khi `type` lạ. Đây là "UL enforced bằng validation". Nêu
   một trường hợp validation cứng như vậy gây cản trở, và cách hex_agent cân bằng (gợi ý:
   chỉ enum hoá vocabulary load-bearing).
