# KNOWN_RISKS — file dễ vỡ & rủi ro hành vi đã biết

> Trạng thái: **mô tả hiện thực đang chạy** (đã verify trực tiếp trên code, không chép lại
> cảnh báo trong `MCP_TOOLS.md` — đó là proposal, một phần có thể lạc hậu).
> Dùng kèm `RUNTIME_FLOW.md` (luồng chạy) và `MAP.md` (file nào là gì).
>
> Mục đích: trước khi sửa, biết file nào giữ **invariant** và sửa sai thì vỡ gì. Đây là tầng
> "dangerous files" mà recovery checklist yêu cầu.

---

## Phần 1 — File dễ vỡ nhất (sửa cần cẩn trọng)

Xếp theo mức "sửa ẩu → vỡ rộng".

| # | File | Invariant nó giữ | Sửa sai → vỡ gì | Quy tắc sửa an toàn |
|---|---|---|---|---|
| 1 | `core/kernel.py` | **Chokepoint duy nhất** `execute_tool`: mọi LLM/tool đi qua đây; envelope chuẩn hóa; lineage event; `freeze()` đóng băng config/registry trước session đầu. | Mất observability/safety/envelope cho **toàn bộ** call; hoặc cho sửa config sau freeze → state rò giữa các run. | Không thêm đường thực thi tool nào ngoài `execute_tool`. Không bỏ try/except bọc executor (tool không được làm sập kernel). Giữ thứ tự publish `tool.requested` → chain → `tool.completed/failed`. |
| 2 | `graph/state.py` | `AgentState` **chỉ chứa giá trị serializable**; codec `encode/decode_session_state` (hiện chỉ đặc cách `TaskEnvelope`); `schema_version=2` (+ key `kernel_state` migrate v1). | Đặt object không-primitive vào `session.state` mà quên mở rộng codec → checkpoint/resume **vỡ âm thầm** (SQLite serialize lỗi hoặc restore sai). | Mọi thứ bỏ vào `session.state` phải là primitive **hoặc** được xử lý trong `encode/decode_session_state`. Đổi shape state → tăng `schema_version` + thêm nhánh migrate. |
| 3 | `orchestrator/loop.py` + `orchestrator/checkpoint.py` | **SQLite là nguồn sự thật**; `checkpoint.json` chỉ là projection cho UI; `resume()` đọc SQLite; có nhánh migrate JSON cũ (`_legacy_state`). `run_id == thread_id`. | Resume sai/đọc nhầm projection → mất tiến trình hoặc **chạy lại** node đã chạy (nguy hiểm khi có side effect). | Không bao giờ resume từ `checkpoint.json`. Không đổi `run_id↔thread_id`. Sửa logic resume phải test bằng `tests/test_resume.py`. |
| 4 | `graph/runtime.py` + `graph/nodes.py` | Topology + hợp đồng `_route`; finish gate; **đóng lifecycle đúng một lần** (`complete_task`/`fail_task`). | Route sai → loop vô tận / không terminate; hoặc đóng lifecycle hai lần / không đóng. | Thêm node phải khai báo đủ cạnh trong `build_agent_graph` và set `route` hợp lệ trong node. Mọi nhánh kết thúc phải về `finish`/`fail`. Cập nhật `RUNTIME_FLOW.md` khi đổi topology. |
| 5 | `delegation/policy.py` + `delegation/manager.py` | Chokepoint delegation **tách khỏi kernel**; enforce depth/budget và **scope con ⊆ scope cha**. | Bỏ qua `validate()` → đệ quy không kiểm soát hoặc con leo quyền vượt cha. | Mọi delegation phải đi qua `DelegationPolicyEngine.validate`. Không nới `max_depth/max_steps` không có lý do. Giữ check `scope <= parent.allowed_capabilities`. |
| 6 | `safety/sandbox.py` + `toolbox/filesystem.py` | **Workspace jail**: path phải nằm trong `var/workspace` (`resolve()` + `is_relative_to`). | Tool fs mới bỏ qua `resolve_in_workspace` → path traversal ra ngoài workspace. | Mọi tool đụng filesystem **bắt buộc** gọi `resolve_in_workspace(...)` trước khi đọc/ghi. Không nhận path tuyệt đối từ model mà không qua jail. |

---

## Phần 2 — Rủi ro hành vi đã biết (footgun)

`LIVE` = đang bật ở config mặc định · `LATENT` = chỉ thành rủi ro khi bật/ thêm thứ gì đó.

| Rủi ro | Trạng thái | Vị trí | Vì sao | Cách xử lý trước khi mở rộng |
|---|---|---|---|---|
| **Log raw args** vào `events.jsonl` | 🔴 LIVE | `core/kernel.py:79-82` (`tool.requested` ghi `args`) | Secret/PII trong tool args bị ghi xuống đĩa. | Redact/`args_digest + safe_preview` trước khi bật write tool / MCP. Xem `MCP_TOOLS.md` §12. |
| **Retry không biết idempotency** | 🟡 LATENT | `middleware/retry.py` | Retry **mọi** `ok=False` (trừ `policy_block`); không phân biệt read-only/side-effect. Hiện *chưa wire* (config không có section `middleware:`). | Trước khi bật `middleware.retry` **và** thêm tool có side effect: chỉ retry khi descriptor `read_only/idempotent`. |
| **Không có deny-list ở kernel** mặc định | 🟡 LATENT | `core/bootstrap.py:28-53` (PolicyGate chỉ wire khi config bật) | Capability **không thuộc toolbox** đăng ký vào registry sẽ **không** qua policy/deny nào ở chokepoint (chỉ toolbox có `SafeToolPort`+jail). | Khi thêm tool ngoài toolbox: bật `middleware.policy` hoặc bọc safety tương đương. |
| **`checkpoint.json` không phải sự thật** | 🟡 LATENT | `orchestrator/checkpoint.py` | Dễ tưởng nhầm là state để resume → debug sai, hoặc sửa tay vô tác dụng. | Coi nó là read-only cho UI. Truy vết thật bằng SQLite + `events.jsonl`. |
| **Hợp đồng serializable ngầm** của state | 🟡 LATENT | `graph/state.py` | Người mới dễ nhét dataclass/đối tượng vào `session.state` → vỡ resume về sau. | Xem Phần 1 #2. Thêm test resume cho state mới. |
| **Xóa `var/agent_runs/<run_id>`** | 🟢 thấp | `var/` (gitignored) | Mất khả năng resume run đó. | Chỉ xóa run đã kết thúc; đừng xóa khi đang chạy/chờ resume. |

> Lưu ý: `BudgetGuard` (chống lặp cùng tool) **cố ý không** wire ở kernel vì bộ đếm là per-run
> (`core/bootstrap.py:28-32`). Việc chặn step/same-tool budget hiện nằm ở graph nodes
> (`guard_node`, `tool_node`) — đừng nhân đôi nó ở middleware.

---

## Phần 3 — Kiểm tra mình chưa làm vỡ invariant

```bash
python run_smoke.py        # CORE_AGENT_SMOKE_OK
python -m pytest -q        # phải xanh hết (resume/delegation/concurrency nằm trong này)
```

Nếu đụng vào bất kỳ file ở Phần 1, chạy thêm test trọng yếu tương ứng:

| Đụng vùng | Test phải xanh |
|---|---|
| kernel / chokepoint | `tests/test_kernel.py`, `tests/test_trace_ids.py` |
| state / checkpoint / resume | `tests/test_state.py`, `tests/test_checkpoint.py`, `tests/test_resume.py`, `tests/test_lifecycle.py` |
| graph / topology | `tests/test_graph.py`, `tests/test_orchestrator.py` |
| delegation | `tests/test_delegation.py` |
| safety / workspace jail | `tests/test_safety.py`, `tests/test_toolbox.py` |
| events / concurrency | `tests/test_event_concurrency.py`, `tests/test_observability.py` |
