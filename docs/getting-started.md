# Bắt đầu — cách theo dõi repo khi nó lớn dần

Đừng đọc từng file rời rạc. Repo này có **5 lớp dẫn đường** liên kết nhau — đi từ trên xuống là hiểu, không lạc:

## 1. `MAP.md` — "cái gì là cái gì" (1 dòng/module)
Bảng tự sinh: mỗi module + một dòng mục đích + epic. Mở `../MAP.md` (ở root repo) để biết toàn bộ file đang có và làm gì.
- Tự sinh, không sửa tay: `python tools/gen_map.py` (đọc docstring dòng đầu mỗi module).
- Chạy lại sau mỗi lần thêm file → MAP luôn đúng. Chi tiết: [guides/regenerate-map.md](guides/regenerate-map.md).

## 2. `CHANGELOG.md` — "thêm gì, vì sao, khi nào"
Nhật ký theo **Sprint + Epic**. Đọc từ trên xuống để thấy repo lớn lên qua từng đợt: thêm module nào, thuộc epic nào, test gì. Đây là "câu chuyện" của repo (`../CHANGELOG.md`).

## 3. `spec/` + `roadmap/` — "tại sao / hợp đồng"
Mỗi module truy được về một **epic**. Epic đã chốt nằm ở [spec/](spec/) (`done/` + `active/`), mỗi epic có `PRD.md` (vì sao + phạm vi), `stories.md` (ai cần gì), `acceptance.md` (Given/When/Then). Epic tương lai (chưa đấu nối) nằm ở [roadmap/future/](roadmap/future/) dưới dạng *living note*. Muốn hiểu *ý định* của một module → mở epic của nó.
> Chuỗi truy vết: **file → epic (Exx) → acceptance criteria → test**.

## 4. `tests/` — "hành vi kỳ vọng" (hợp đồng sống)
Test phản chiếu acceptance criteria. Muốn biết một module *phải làm gì* mà không đọc hết code → đọc test của nó. `python -m pytest` luôn phải xanh; test đỏ = hợp đồng bị phá.

## 5. `git log` — "dòng thời gian"
Mỗi epic = một (cụm) commit với cú pháp `feat(Exx): ...`. `git log --oneline` đọc như mục lục. Muốn xem một epic đổi gì → `git show` commit đó.

---

## Convention mình sẽ tuân theo khi THÊM file (để bạn luôn theo dõi được)
1. **Mỗi module mới có docstring dòng đầu**: `"""<mục đích 1 dòng>. Epic Exx."""` → tự vào `MAP.md`.
2. **Mỗi năng lực mới có test** map tới acceptance criteria của epic.
3. **Cập nhật `CHANGELOG.md`** một mục cho đợt thêm đó.
4. **Chạy lại `python tools/gen_map.py`** để `MAP.md` cập nhật.
5. **Commit theo epic**: `feat(E06): MCP tool layer + safety chokepoint`.
6. Module mới thuộc package mới → `MAP.md` tự phát hiện package (không cần khai báo).

## Thứ tự đọc đề xuất (cho người mới mở repo)
`../README.md` → `../MAP.md` → [reference/runtime-flow.md](reference/runtime-flow.md) (cách một task chạy) → `../CHANGELOG.md` (mới nhất) → mở 1 epic ở [spec/](spec/) đang quan tâm → đọc `acceptance.md` rồi `tests/` rồi module tương ứng.

> Trước khi **sửa** (không phải đọc) một module lõi: mở [reference/known-risks.md](reference/known-risks.md) để biết file đó có giữ invariant gì và sửa sai thì vỡ gì.

## Kiểm tra nhanh "mình có hiểu đúng không"
```
python run_smoke.py     # CORE_AGENT_SMOKE_OK
python -m pytest        # phải xanh hết
python -m observability.inspect summary latest   # xem run gần nhất
python tools/gen_map.py # xem lại MAP
```
Nếu cả bốn lệnh chạy ổn và bạn đọc được `MAP.md` + `CHANGELOG.md` mới nhất, bạn đang nắm đúng trạng thái repo.

### `run_smoke.py` kiểm tra gì
Đây là bài kiểm tra end-to-end nhỏ nhất cho nền agent — chạy offline, không gọi LLM, không cần network. Nó dựng kernel (`create_kernel()` đọc `config/features.yaml`, nạp feature `example_echo`), gắn `EventLogger` vào event bus, rồi lần lượt:

- **tool hợp lệ**: `execute_tool("echo", {"msg": "hi"})` → `ok=True`, data echo lại args.
- **tool thiếu**: `execute_tool("does_not_exist")` → failure có cấu trúc `missing_capability=True` (không crash).
- **JSON discipline**: `parse_action()` xử lý JSON trong markdown fence + trailing comma → `action="final"`.
- **finish gate**: `check_finish()` chặn `final` khi `code_changed=True` nhưng `validation_passed=False`.

Nếu mọi thứ ổn, nó ghi `summary.json`, append `index.jsonl`, rồi in:
```
CORE_AGENT_SMOKE_OK run_id=<run_id>
```
