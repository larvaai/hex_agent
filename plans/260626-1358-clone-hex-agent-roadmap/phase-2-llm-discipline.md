---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 2 — LLM-as-capability & Output discipline

> Epic: E03 + E02 · Cổng vào: Phase 1 · Rời phase với: `agent_node` gọi được LLM qua `execute_tool("llm.chat")`, parse đúng **một** action mỗi turn, và `finish` bị chặn khi đổi code mà chưa validate — tất cả qua cùng một chokepoint của Phase 1.

## 1. Mục tiêu & ranh giới

Phase 1 cho bạn một cái cửa (`AgentKernel.execute_tool`) và quan sát được mọi thứ đi qua nó. Phase 2 dạy agent **nói chuyện với LLM** và **kỷ luật cái LLM nói ra** — nhưng không phá cái cửa đó.

Hai ý lớn, đọc kỹ trước khi gõ phím:

- **LLM không phải công dân hạng nhất.** Nó là một capability `llm.chat` như mọi tool khác (I5). Không có hàm `kernel.call_llm()` đi đường vòng. Lý do: nếu LLM có back-door, bạn mất luôn envelope + event + budget mà Phase 1 vừa dựng.
- **Model là nguồn hỗn loạn.** Nó trả JSON hỏng, trả 5 action một lúc, lặp vô hạn, hoặc "xong rồi" khi chưa làm gì. `discipline/` là 4 cái van chặn hỗn loạn đó **trước** khi nó vào loop.

Trong phase: adapter LLM (E03) + 4 module discipline (E02) + wire `llm_chat` qua kernel.
Ngoài phase: graph topology đầy đủ, delegation, toolbox an toàn (Phase 3+). Ở đây bạn chỉ cần đủ để một agent_node chạy được một turn sạch.

Ranh giới cứng: **discipline là module dùng chung** — graph node (Phase này) và middleware (Phase sau) gọi *cùng* `discipline.condense`, *cùng* `check_finish`. Không copy-paste logic. Sai chỗ này thì hai nơi sẽ trôi lệch nhau.

**Một turn nhìn từ trên xuống** — mỗi mũi tên là một cái van bạn sắp dựng:

```text
messages ──► execute_tool("llm.chat")          # I5: LLM qua cửa, có envelope+event
              │ adapter: lazy client, json_mode, retry transient
              ▼
            content (text/JSON model trả)
              │ parse_action                    # I6: ép đúng 1 action
        ┌─────┴─────┐
   parse lỗi      hợp lệ
        │            │
 record_parse_error  record_step                # I7: hai bộ đếm tách rời
 (KHÔNG đốt step)     │ route theo verb
   retry → guard     ├─ tool   → condense kết quả → guard
                     ├─ delegate → guard
                     └─ final  → check_finish    # chặn nếu đổi code chưa validate
```

Bốn cái van (adapter / json_gate / budget / finish_gate) đều nằm *quanh* cái cửa của Phase 1 — không thay nó.

## 2. Bạn sẽ xây gì (bản đồ module)

| file | vai trò | class/hàm chính |
|---|---|---|
| `discipline/json_gate.py` | parse + sửa JSON model trả về, ép đúng 1 action | `parse_action`, `parse_json_object`, `light_json_repair`, `JsonGateError`, `build_retry_message` |
| `discipline/budget.py` | đếm step / parse-error / tool lặp | `Budget` (dataclass), `tool_key` |
| `discipline/condense.py` | co nhỏ kết quả tool trước khi nhét lại cho model | `condense` |
| `discipline/finish_gate.py` | chặn `final` khi đổi code mà chưa validate | `check_finish`, `requires_validation`, `has_passing_validation` |
| `discipline/__init__.py` | mặt tiền: export gọn cho cả node lẫn middleware | re-export 9 symbol |
| `llm/adapter.py` | gọi endpoint OpenAI-compatible, JSON-mode, lazy, retry | `call_llm`, `_get_client`, `_is_transient`, `reset_client` |
| `features/llm_chat.py` | bọc adapter thành capability `llm.chat` | `LLMChatTool`, `FEATURE`, `install` |

## 3. Dựng step-by-step

Thứ tự: **discipline trước** (chúng không phụ thuộc gì) → adapter → wire qua kernel. Mỗi bước có cách tự kiểm offline.

**B1 — `json_gate.py` (cái van quan trọng nhất).**
Viết một thang sửa (`_candidates`): raw trước, rồi từng rule `str -> str` ngày càng mạnh. `parse_json_object` thử `json.loads` từng candidate, cuối cùng `ast.literal_eval`; không ra dict thì `raise JsonGateError`. `parse_action` = `parse_json_object` + bắt buộc field `"action"` (`json_gate.py:411`).
Nguyên tắc vàng: **JSON hợp lệ luôn được candidate #1 (raw) bắt** — rule sửa không bao giờ chạm vào object đã đúng (`json_gate.py:4-6`).
Mỗi rule là một hàm thuần `str -> str` (total trên text bất kỳ), gom trong `light_json_repair` (`json_gate.py:305-317`) — đây là những gì model local/open thực sự nhả ra:

| rule `file:line` | sửa cái gì |
|---|---|
| `strip_markdown_fence` `json_gate.py:35` | bóc ` ```json ... ``` ` |
| `extract_largest_json_region` `json_gate.py:76` | nhặt `{...}` lớn nhất khỏi prose bao quanh |
| `remove_trailing_commas` `json_gate.py:86` | `{"a":1,}` → hợp lệ |
| `replace_python_literals` `json_gate.py:125` | `True/False/None` → `true/false/null` |
| `quote_unquoted_keys` `json_gate.py:129` | `{key: 1}` → `{"key": 1}` |
| `convert_single_quoted_values` `json_gate.py:238` | token `'...'` kiểu Python → `"..."` |
| `balance_trailing_delimiters` `json_gate.py:277` | đóng nốt `{`/`[` bị cụt (≤3 tầng) |

Tự kiểm: `parse_action('{"action":"tool","tool":"echo","args":{}}')` ra `action=="tool"`; `parse_action('```json\n{"action":"final","message":"ok",}\n```')` vẫn ra `final` (fence + trailing comma); `parse_action('action: {"action":"final","message":"x"} thanks')` ra `final` (gỡ khỏi prose); `parse_action('{"tool":"echo"}')` ném `JsonGateError` `stage=="schema"`; `parse_action("not json")` ném `JsonGateError`.

**B2 — `budget.py`.**
Một dataclass đếm. Để ý điểm dễ sai nhất: `record_parse_error()` tăng `parse_errors`, **không** đụng `steps` (`budget.py:25-26`). `tool_key` băm `tool+args` (sort key) để phát hiện lặp y hệt.
Tự kiểm: gọi `record_parse_error()` 2 lần → `parse_exceeded()` True nhưng `steps == 0`.

**B3 — `condense.py`.**
Đệ quy: dict đệ quy theo value, list cắt còn `max_list` rồi gắn `"... [+N items]"`, str cắt còn `max_chars` rồi gắn `"... [+N chars]"`, còn lại giữ nguyên (`condense.py:13-24`). Quan trọng: **chỉ co, không bịa** — luôn ghi số đã cắt để model biết có dữ liệu bị giấu.
Tự kiểm: `condense({"text":"x"*5000}, max_chars=100)` → len < 200 và chuỗi chứa `"+4900"`.

**B4 — `finish_gate.py`.**
3 hàm thuần đọc `state`. `check_finish` trả `{allowed, reason}`: chặn khi `code_changed and not validation_passed and finish_reason != "blocker"` (`finish_gate.py:17`). Cửa thoát hợp pháp duy nhất: tuyên bố `finish_reason="blocker"`.
Tự kiểm: `check_finish({"code_changed":True,"validation_passed":False})["allowed"]` là False; thêm `finish_reason="blocker"` → True.

**B5 — `llm/adapter.py`.**
`call_llm(messages, *, model, temperature, json_mode, client)`. Bốn việc:
1. **Lazy client** — `_get_client()` chỉ `from openai import OpenAI` và dựng client khi *được gọi*, cache vào `_client` global (`adapter.py:25-32`). Không có network lúc import.
2. **Ép JSON** — `json_mode=True` thì `kwargs["response_format"]={"type":"json_object"}` (`adapter.py:80-81`). Đây là cách *request shape* buộc model trả JSON.
3. **Retry transient** — vòng `while`, chỉ retry khi `_is_transient(exc)` (timeout/connection/429/5xx), backoff mũ `retry_base*2**attempt` (`adapter.py:99-100`). 4xx khác = permanent, dừng ngay.
4. **Không bao giờ raise** — kiệt retry thì trả JSON `{"action":"final","finish_reason":"error","message":...}` (`adapter.py:115-119`). Loop xử lý error như một final, không sập.
Tự kiểm (inject fake client, không mạng): xem `tests/test_llm_adapter.py`, `tests/test_llm_retry.py`.

**B6 — `features/llm_chat.py` (wire qua cửa).**
`LLMChatTool.execute(request)` đọc `request.args`, gọi `call_llm(...)`, trả `{"ok":True,"content":...,"model":...}` (`llm_chat.py:23-32`). `install(kernel, client=)` đăng ký FEATURE + tool vào registry (`llm_chat.py:35-37`). Client injectable để test offline.
Tự kiểm: `kernel.execute_tool("llm.chat", {...})` trả envelope có `capability=="llm.chat"`, `feature=="llm"`, và phát `tool.requested`/`tool.completed` — y như mọi tool (xem `tests/test_llm_capability.py`).

**B7 — nối vào `agent_node` (`graph/nodes.py`).**
Đây là chỗ discipline gặp LLM: `agent_node` gọi `session.execute_tool("llm.chat", {messages, model, json_mode:True})` (`nodes.py:55-58`), lấy `content`, rồi `parse_action(content)` (`nodes.py:64`). Lỗi → `record_parse_error` + retry message (`nodes.py:66-82`); hợp lệ → `record_step` rồi route theo verb (`nodes.py:84-103`). `finish_node` chạy `check_finish` (`nodes.py:220`).

## 4. Class & biến kiểm soát (cái neo)

| neo `file:line` | invariant | sai thì mất gì |
|---|---|---|
| `_client` global + `_get_client` `adapter.py:25-32` | network chỉ chạm khi gọi, không khi import | import-time hang / test offline gãy |
| `kwargs["response_format"]` `adapter.py:80-81` | `json_mode` ⇒ request ép `json_object` | model trả văn xuôi, gate phải gánh nhiều hơn |
| `_is_transient` `adapter.py:40-50` | chỉ retry timeout/conn/429/5xx | retry 4xx vô ích, hoặc bỏ qua lỗi tạm |
| `parse_action` `json_gate.py:411-416` | đúng 1 object, bắt buộc `"action"` (I6) | turn nhập nhằng nhiều action / thiếu verb |
| `Budget.record_parse_error` `budget.py:25-26` | parse-error KHÔNG đốt step (I7) | một model hay hỏng JSON tiêu sạch step budget |
| `check_finish` `finish_gate.py:15-22` | chặn final nếu đổi code chưa validate | agent "báo xong" với code chưa chạy được |
| `condense` `condense.py:13-24` | co nhưng luôn ghi `+N` đã cắt | mất dữ liệu lặng lẽ, model quyết định mù |

Candidate #1 luôn là raw — JSON đúng không bao giờ bị rule sửa làm méo:
```python
# json_gate.py:358-368 (rút gọn)
base = strip_bom(raw)
add(base)                                   # raw trước nhất
fenced = _safe(strip_markdown_fence, base)
add(fenced)
add(_safe(lambda t: light_json_repair(t, extract_region=False), base))
add(_safe(extract_largest_json_region, region_src))
add(_safe(light_json_repair, base))         # mạnh tay nhất, cuối cùng
```

Parse-error và step là hai bộ đếm tách rời — đó là cả ý nghĩa của I7:
```python
# budget.py:19-29
def record_step(self) -> None:        self.steps += 1
def step_exceeded(self) -> bool:      return self.steps > self.max_steps
def record_parse_error(self) -> None: self.parse_errors += 1   # KHÔNG đụng steps
def parse_exceeded(self) -> bool:     return self.parse_errors >= self.max_parse_errors
```

Trong `agent_node`, thứ tự là load-bearing: parse lỗi thì `record_parse_error` rồi *return sớm* — chưa tới `record_step`:
```python
# nodes.py:64-84 (rút gọn)
try:
    action = parse_action(content)
except JsonGateError as exc:
    budget.record_parse_error()             # đốt parse-error, KHÔNG đốt step
    if budget.parse_exceeded(): return {... "route": "fail"}
    messages.append({"role": "user", "content": build_retry_message(exc)})
    return {... "route": "guard"}            # quay lại, thử turn khác
budget.record_step()                         # chỉ tới đây khi action HỢP LỆ
```

## 5. Invariant của phase

- **I5 — LLM qua cửa.** LLM là capability `llm.chat`; `agent_node` chạm nó qua `session.execute_tool` (`nodes.py:55`), không đường tắt. Envelope + event + lineage giống hệt tool (`tests/test_llm_capability.py`).
- **I6 — đúng một action mỗi turn.** `parse_action` trả đúng một dict có `"action"`, ném `JsonGateError` nếu không (`json_gate.py:411-416`); node biến nó thành đúng một route.
- **I7 — parse-error không đốt step.** `record_parse_error` tách khỏi `record_step` (`budget.py:25-26`); node return sớm trước `record_step` (`nodes.py:66-84`). Model hay hỏng JSON vẫn có cơ hội sửa mà không cụt budget.

## 6. Pitfall / bug sẽ gặp

**Network lúc import.**
Triệu chứng: `import llm.adapter` hoặc collect pytest bị treo / cần mạng.
Nguyên nhân: dựng `OpenAI(...)` ở top-level module thay vì trong hàm.
Cách tránh: client lazy + cache global, `from openai import OpenAI` *bên trong* `_get_client` (`adapter.py:25-32`); `reset_client()` cho test.

**Parse-error đốt step.**
Triệu chứng: model trả JSON hỏng vài lần là run `fail` vì hết step, dù chưa làm gì.
Nguyên nhân: gọi `record_step()` cả khi parse lỗi, hoặc không return sớm.
Cách tránh: chỉ `record_step()` sau khi `parse_action` thành công; nhánh lỗi return sớm (`nodes.py:66-84`, `budget.py:25-26`).

**Retry mọi lỗi.**
Triệu chứng: prompt sai (400) bị thử lại 3 lần rồi mới chết — chậm, tốn token.
Nguyên nhân: retry trên mọi exception thay vì phân loại.
Cách tránh: `_is_transient` chỉ True cho timeout/conn/429/5xx; 4xx khác dừng ngay (`adapter.py:40-50`, `99-103`). Đối chiếu `test_no_retry_on_permanent_4xx`.

**Condense cắt ẩu mất dữ liệu.**
Triệu chứng: model "quên" phần cuối kết quả tool, quyết định sai.
Nguyên nhân: cắt chuỗi/list mà không để lại dấu vết.
Cách tránh: luôn nối `"... [+N chars/items]"` để model biết có phần bị giấu (`condense.py:7-21`).

**Finish-gate bị bypass.**
Triệu chứng: agent báo "xong" sau khi đổi code nhưng test chưa từng xanh.
Nguyên nhân: `finish_node` không gọi `check_finish`, hoặc gọi rồi nhưng không quay lại `guard` khi `allowed=False`.
Cách tránh: `finish_node` luôn `check_finish(state, finish_reason)`; `allowed=False` → emit `graph.finish_blocked` + route `guard` (`nodes.py:220-229`). Cửa thoát hợp pháp duy nhất là `finish_reason="blocker"`.

**Server không nhận `json_object`.**
Triệu chứng: 400 `"response_format.type must be json_schema or text"` trên llama.cpp / vLLM.
Nguyên nhân: vài server local chỉ nhận `json_schema`/`text`.
Cách tránh: bắt lỗi này, hạ xuống `{"type":"text"}` *một lần* không tốn attempt — gate vẫn parse text (`adapter.py:62-69`, `95-98`).

## 7. Definition of Done (cổng đóng phase)

Tất cả offline (inject fake client, không mạng). Xanh hết:

- `tests/test_llm_adapter.py` — lazy import, json-mode bật/tắt, injected client không ghi cache, lỗi → final có `finish_reason=="error"`, message connection actionable (tên endpoint + "is the server running").
- `tests/test_llm_retry.py` — 5xx/429/timeout retry rồi thành công; 4xx không retry (`calls==1`); kiệt retry → error.
- `tests/test_llm_capability.py` — envelope `capability=="llm.chat"`/`feature=="llm"`; phát `tool.requested`/`tool.completed` kèm `task_id`; metric `llm_calls==1` + kind `LLMCallEvent`; `create_kernel()` có sẵn `llm.chat`.
- `tests/test_json_gate_repair.py` — thang sửa bắt fence/prose/trailing-comma/Python-literal/unquoted-key/single-quote.
- `tests/test_discipline.py` — parse 1 action, missing-action ném `stage=="schema"`, condense, finish-gate, budget (`parse_does_not_consume_steps`, same-tool).
- `tests/test_supervisor_discipline.py` — chứng minh finish-gate là **cùng module** worker turn chạy qua (không duplicate).

Lệnh: `python -m pytest tests/test_discipline.py tests/test_llm_adapter.py tests/test_llm_retry.py tests/test_llm_capability.py tests/test_json_gate_repair.py -q`.

## 8. Vì sao tổ chức thế này giúp kiểm soát

Hai quyết định tổ chức là toàn bộ bài học của phase:

**LLM-qua-cửa.** Bạn có thể cám dỗ cho agent gọi `openai` trực tiếp cho "nhanh". Đừng. Khi LLM là `llm.chat` đi qua `execute_tool`, nó tự động có: envelope chuẩn, event `tool.*` với lineage, đếm `llm_calls`, và (Phase sau) middleware budget/retry/condense bọc quanh — *miễn phí*. Một back-door LLM nghĩa là một lỗ đen không quan sát được giữa hệ thống quan sát được. Đây chính là chokepoint của Phase 1 trả cổ tức.

**Discipline dùng chung.** `condense` và `check_finish` không sống trong graph node — chúng sống trong `discipline/` và được *cả* node *lẫn* `middleware/condense.py` gọi (`middleware/condense.py:8` import `from discipline import condense`). Một định nghĩa, hai nơi tiêu thụ. Nếu bạn nhân đôi logic finish-gate vào worker turn riêng, đến lúc đổi luật (thêm `finish_reason="blocker"`) bạn sẽ sửa một chỗ và quên chỗ kia — và agent sẽ "báo xong dối" ở đúng nhánh bạn quên. Module dùng chung là cách bạn giữ một sự thật duy nhất về "thế nào là được phép kết thúc".

---
*Điều hướng: ← [Phase 1](phase-1-microkernel-chokepoint.md) · → [Phase 3](phase-3-toolbox-safety.md)*
