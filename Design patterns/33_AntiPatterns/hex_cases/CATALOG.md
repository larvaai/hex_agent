# CATALOG — Vét cạn mọi occurrence anti-pattern / smell trong hex_agent

> Bảng này liệt kê **toàn bộ** occurrence từ bước discover, gồm cả flagship (đã distill
> thành case con) lẫn các smell *borderline*. Mọi `path:line` đã được mở file kiểm chứng.
> Đường dẫn tương đối so với root `/Users/uspro/Desktop/namnson/hex_agent/`.
>
> Cột **độ rõ**: `cao` = anti-pattern rõ ràng, nên sửa; `trung bình` = đáng nhìn kỹ, có
> sức ép readability; `thấp` = chấp nhận được trong bối cảnh domain, đưa vào checklist
> review để "trigger conversation".

## Flagship (đã distill thành case chạy được)

| path:line | mô tả | độ rõ |
|-----------|-------|-------|
| `discipline/json_gate.py:338-343` | **Swallowing Exceptions** — `_safe()` bắt MỌI `Exception` rồi trả `None` lặng lẽ; không log rule nào hỏng hay vì sao. Xem case `01_swallowed_exceptions_json_repair/`. | cao |
| `discipline/json_gate.py:373-378` | **Swallowing Exceptions** — `try_literal_eval()` cũng nuốt ngoại lệ; caller không bao giờ biết vì sao `ast.literal_eval` từ chối candidate. | cao |
| `llm/adapter.py:9, 25-37` | **Global Mutable State + Cargo Cult Singleton + Premature Optimization** — `_client` module-level (dòng 9), lazy-init `_get_client()` (25-32), mutate qua `reset_client()` (35-37); một instance chia sẻ mãi mãi. Xem case `02_global_mutable_client_singleton/`. | cao |

## Borderline / chấp nhận được (đưa vào checklist review)

| path:line | mô tả | độ rõ |
|-----------|-------|-------|
| `discipline/json_gate.py:305-317` | **Golden Hammer (borderline)** — `light_json_repair()` xâu chuỗi ~9 hàm repair (strip_bom → strip_markdown_fence → extract_largest_json_region → remove_trailing_commas → replace_python_literals → quote_unquoted_keys → escape_control_chars_in_strings → convert_single_quoted_values → balance_trailing_delimiters). Mỗi hàm thuần, nhưng "áp cả chuỗi repair cho mọi JSON" là cận Golden Hammer; chính đáng vì domain output của local LLM rất bẩn. | trung bình |
| `core/bootstrap.py:48-53` | **Spaghetti (nhẹ) / nesting** — cấu hình `CondenseResult` lồng nhiều cấp `.get()` cộng constructor nhiều dòng. Có thể flatten bằng helper trích cấu hình. Không nguy hiểm nhưng có sức ép readability. | trung bình |
| `llm/adapter.py:72-100` | **Spaghetti / quá nhiều trách nhiệm trong 1 hàm** — `call_llm()` ~30 dòng, lồng try/except trong vòng while; làm 3 việc: (1) build kwargs, (2) retry + backoff, (3) downgrade response_format. Ứng viên tách Strategy để cô lập điều phối retry khỏi đàm phán response-format. | trung bình |
| `ui/server.py:314-344` | **Feature Envy (vừa phải)** — `_normalize_messages()` đọc `checkpoint.get('messages')`, `summary.get('outcome')` rồi trộn; chạm nhiều field qua hai object. Chấp nhận được cho lớp projection của UI, nhưng có thể tách normalizer cho message/outcome. | thấp |
| `control/snapshot.py:189-300+` | **Cyclomatic complexity cao (không phải God Object)** — `build_snapshot()` là hàm fold 160+ dòng xử lý các event `team_composed`/`decision`/`turn`/`tool`/`permission.changed`/`checkpoint.reached`. Độ phức tạp chu trình cao, nhưng mỗi nhánh event biệt lập (không đan xen), nên chấp nhận được cho event projection. | thấp |
| `ui/server.py:205-262` | **Ví dụ ĐÚNG (đối chứng)** — `RunController`: 5 method, quản lý `threading.Lock`, dict `_jobs`, executor, logger. ~60 dòng, SRP rõ (thực thi job + theo dõi trạng thái), dùng `_lock` an toàn thread. Đây là encapsulation đúng, KHÔNG phải anti-pattern. | thấp |
| `discipline/json_gate.py:238-274` | **Intricate (không phải anti-pattern)** — `convert_single_quoted_values()` ~40 dòng, state machine theo dõi `in_double_string`/`escaped`. Sâu nhưng chính đáng vì domain (sửa literal JSON). Phức tạp có lý do, không phải smell. | thấp |

---

## Đọc bảng này thế nào

1. **Flagship** (3 dòng đầu, độ rõ `cao`) là anti-pattern thật — đã có thư mục case con
   với code chạy được và bài học đầy đủ.
2. **Borderline** là các occurrence cần "con mắt 30 giây": gọi tên được smell, nhưng quyết
   định *không sửa* vì bối cảnh domain biện minh được. Đúng tinh thần Lesson 33: số liệu
   chỉ để *trigger conversation*, không reject PR một cách máy móc.
3. Hai dòng cuối (`ui/server.py:205-262` và `json_gate.py:238-274`) cố tình giữ trong bảng
   làm **đối chứng dương tính** — code phức tạp nhưng *đúng nguyên lý*, để luyện phân biệt
   "code đẹp đúng nguyên lý" với "code có smell".
