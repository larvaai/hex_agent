# Case 03 — Reduce Node: Pluggable Aggregation Strategies (pick/concat/merge/manifest)

> Strategy (Behavioral) ở dạng **dispatch theo selector**: một phép toán (gộp N output
> anh-em thành 1 aggregate) có 4 cách cài đặt, chọn bằng `node.reduce_op` khai báo trên
> chính Node — không hardcode trong handler.

---

## 1. Bối cảnh trong hex_agent

`decompose_agent` chia một việc lớn thành cây node; các node anh-em chạy độc lập rồi một
**reduce node** gom output của chúng thành một artifact tổng hợp mà `done_when` của nó sẽ kiểm.
Vấn đề: có **nhiều cách gộp hợp lệ** tuỳ ngữ cảnh — copy nguyên (pick), nối text (concat),
deep-merge JSON metric (merge_json), hay chỉ liệt kê tồn tại/size (manifest).

Thay vì để runner đoán, hex_agent **khai báo strategy ngay trên Node**: trường `reduce_op`
(`decompose_agent/node.py:114`) chọn một trong tập đóng `REDUCE_OPS`
(`decompose_agent/node.py:28`), và bất biến cấu trúc được ép tại construction — một reduce node
mà thiếu `reduce_op` hợp lệ thì **không thể tồn tại** (`decompose_agent/node.py:132-133`).

`run_reduce()` (`decompose_agent/reduce.py:44-77`) là **Context** dispatch theo `node.reduce_op`:
gom các nguồn theo destination (để nhiều nguồn fold vào một aggregate) rồi chạy nhánh tương ứng.

Ghi chú trung thực về văn phong: code thật dùng `if/elif` trong `run_reduce()`. Theo đúng
`21_Strategy.md` (mục 1.4 và 2.4), điều này **chấp nhận được** khi số strategy ít và ổn định —
intent vẫn là "một phép toán, nhiều cài đặt". Distill này giữ tinh thần đó nhưng tách mỗi cách
gộp thành một callable trong một **registry** để làm nổi bật vai trò Strategy và minh hoạ lợi
ích Open/Closed.

---

## 2. Trích đoạn code thật

`decompose_agent/node.py:28` — tập strategy hợp lệ (selector domain):

```python
REDUCE_OPS = frozenset({"merge_json", "pick", "manifest", "concat"})
```

`decompose_agent/node.py:132-133` — bất biến: reduce node phải khai báo strategy hợp lệ:

```python
if self.kind == "reduce" and self.reduce_op not in REDUCE_OPS:
    raise ValueError(f"reduce node {self.id!r} needs reduce_op ∈ {sorted(REDUCE_OPS)}, got {self.reduce_op!r}")
```

`decompose_agent/reduce.py:64-77` — Context dispatch theo selector:

```python
for dst, srcs in by_dst.items():
    target = out_dir / dst
    target.parent.mkdir(parents=True, exist_ok=True)
    if node.reduce_op == "pick":
        target.write_bytes(srcs[-1].read_bytes() if srcs[-1].is_file() else b"")
    elif node.reduce_op == "concat":
        target.write_text("".join(_read_text(s) for s in srcs), encoding="utf-8")
    elif node.reduce_op == "merge_json":
        merged: dict[str, Any] = {}
        for s in srcs:
            obj = _load_json(s)
            if isinstance(obj, dict):
                _deep_merge(merged, obj)
        target.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Strategy | Thành phần trong hex_agent | File:line |
|---|---|---|
| **Selector strategy** | `Node.reduce_op` (chuỗi enum) | `decompose_agent/node.py:114` |
| **Tập strategy hợp lệ** | `REDUCE_OPS` | `decompose_agent/node.py:28` |
| **Bất biến chọn đúng strategy** | `__post_init__` ép `reduce_op ∈ REDUCE_OPS` | `decompose_agent/node.py:132-133` |
| **Context dispatch** | `run_reduce()` | `decompose_agent/reduce.py:44-77` |
| **ConcreteStrategy: manifest** | nhánh `if reduce_op == "manifest"` | `decompose_agent/reduce.py:50-57` |
| **ConcreteStrategy: pick** | nhánh `if reduce_op == "pick"` | `decompose_agent/reduce.py:67-68` |
| **ConcreteStrategy: concat** | nhánh `elif reduce_op == "concat"` | `decompose_agent/reduce.py:69-70` |
| **ConcreteStrategy: merge_json** | nhánh `elif reduce_op == "merge_json"` + `_deep_merge` | `decompose_agent/reduce.py:71-77`, `35-41` |
| **Kiểm thử từng strategy độc lập** | `test_reduce.py` (test riêng pick/concat/merge/manifest) | `decompose_agent/tests/test_reduce.py:34-55` |

---

## 4. Bản rút gọn chạy được

File: [`reduce_operations.py`](./reduce_operations.py) — `python3 reduce_operations.py` (exit 0).

**Mô phỏng trung thực:**
- `Node` giữ `reduce_op` + `inputs`, ép bất biến `reduce_op ∈ REDUCE_OPS` trong `__post_init__`
  đúng như `decompose_agent/node.py`.
- 4 strategy (`pick`, `concat`, `merge_json`, `manifest`) giữ nguyên ngữ nghĩa: gom theo
  destination, deep-merge nested dict (`_deep_merge` sao y `reduce.py:35-41`), nối text theo thứ
  tự, copy bản cuối, liệt kê tồn tại + size.
- `run_reduce()` là Context dispatch theo `node.reduce_op` y như bản thật, nhưng dùng một
  **registry** `STRATEGIES = {tên: callable}` để minh hoạ Strategy rõ ràng.
- Demo: cùng bộ input anh-em → 4 reduce_op cho 4 aggregate khác hẳn; bất biến reduce_op hợp lệ;
  mở rộng thêm strategy `count` mà **không đụng** `run_reduce()`.

**Lược bỏ (thay bằng fake stdlib):** filesystem thật (`Path`, `read_bytes`, `mkdir`, `node_dir`,
`write_artifact`) → một `Workspace` trong RAM `{node_id: {artifact: bytes}}`; phần `done_when`/
gate/Navigator được lược (case này chỉ tập trung vào *cách gộp*).

**Đối chứng:** `run_reduce_hardcoded()` tách selector ra khỏi Node (caller phải tự truyền
`reduce_op`) và nhồi if/elif cứng, chưa cài đủ strategy → thêm cách gộp mới phải mở hàm sửa, và
selector rời Node dễ truyền lệch với node thật.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **if/elif vs registry là một đánh đổi có chủ đích.** Với 4 strategy ổn định, `if/elif` trong
  `run_reduce()` đọc dễ và đủ. Chỉ registry-hoá khi số strategy tăng hoặc cần plug-in từ ngoài —
  registry quá sớm là over-engineering (đúng cảnh báo "strategy explosion" trong `21_Strategy.md`).
- **Selector phải đồng bộ với tập strategy.** Nếu thêm `reduce_op` mới vào `REDUCE_OPS` mà quên
  cài nhánh xử lý (hoặc ngược lại) → node hợp lệ nhưng chạy ra `KeyError`/no-op. Distill này
  assert `set(STRATEGIES) == REDUCE_OPS` để bắt lệch đó.
- **Strategy có side-effect (ghi file)** như ở đây làm khó test hơn pure function. Bản thật
  giảm rủi ro bằng cách reduce node chỉ ghi vào **dir của chính nó**, không đụng dir anh-em.
- **Khi chỉ có một cách gộp** → đừng tạo selector; một hàm thẳng là đủ.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao bất biến `reduce_op ∈ REDUCE_OPS` được ép tại **construction** của Node thay vì kiểm
   trong `run_reduce()`? Lợi ích về "fail fast" và về việc một node sai cấu trúc không thể tồn tại?
2. `run_reduce()` gom inputs **theo destination** trước khi gộp. Điều này cho phép hành vi gì khi
   nhiều nguồn cùng map vào một `as:` (vd. hai `b.json` → cùng `report.json`)?
3. Khi nào bạn nên giữ `if/elif` như code thật, và khi nào nên chuyển sang registry như distill?
   Nêu một dấu hiệu cụ thể buộc bạn chuyển.
