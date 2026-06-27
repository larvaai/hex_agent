# Case 02 — `Node` / `DoneWhen`: Factory method + Specification (validation-as-construction)

> Distill từ `decompose_agent/node.py:102-176` (Node), `:50-99` (DoneWhen), `:33-47`
> (assert_safe_relpath), `:19-30` (hằng số). Đây là ví dụ Factory method (`from_dict`) enforce
> invariant **tại lúc dựng** qua `__post_init__`, kèm một **Specification an toàn**: criterion
> nghiệm thu KHÔNG được mang field dạng verdict, và artifact phải nằm trong workspace.

---

## 1. Bối cảnh trong hex_agent

`Node` là "một đơn vị công việc trên đĩa" trong cây decomposition. Docstring code thật nêu rõ
ranh giới toàn vẹn nó bảo vệ (`decompose_agent/node.py:1-9`):

> *"A structurally-wrong node cannot exist — every invariant is enforced at construction... the
> Worker is the one untrusted component, and it never gets to write a verdict. So a done_when
> criterion is only a question the gate will answer — `{check, params, artifact}` — never an answer."*

Vấn đề thật: Worker (LLM) đề xuất action + tiêu chí nghiệm thu (`done_when`); **gate** mới là nơi
chạy kiểm tra và ghi verdict. Nếu một criterion do worker tạo lại chứa sẵn `{"verdict": true}`,
worker tự nghiệm thu chính mình — phá vỡ toàn bộ mô hình tin cậy. Vì vậy `DoneWhen.from_dict`
từ chối mọi key dạng verdict NGAY tại factory (`decompose_agent/node.py:76-81`), trước khi object
kịp tồn tại. Tương tự, `assert_safe_relpath` (`:33-47`) path-jail artifact: chỉ cho đường dẫn
tương đối, trong workspace — chặn `/`, `~`, `..`.

`Node` là frozen dataclass: status chỉ chuyển qua `dataclasses.replace` (Navigator sở hữu cây,
không ai mutate node trực tiếp — `decompose_agent/node.py:104-105`).

---

## 2. Trích đoạn code thật

Specification chống forgery — `decompose_agent/node.py:71-91`:

```python
@classmethod
def from_dict(cls, raw: Any) -> DoneWhen:
    if not isinstance(raw, dict):
        raise ValueError(f"done_when criterion must be a mapping, got {type(raw).__name__}")
    extra = set(raw) - _CRITERION_KEYS
    forged = extra & FORBIDDEN_VERDICT_KEYS
    if forged:
        raise ValueError(
            f"done_when criterion must not carry a verdict field {sorted(forged)} — "
            "the gate writes the verdict, not the author"
        )
    if extra:
        raise ValueError(
            f"done_when criterion has unexpected field(s) {sorted(extra)}; "
            "criteria are exactly {check, params, artifact}"
        )
    return cls(check=raw.get("check"), params=dict(raw.get("params") or {}), artifact=raw.get("artifact"))
```

Path-jail (predicate kiểu spec) — `decompose_agent/node.py:43-47`:

```python
if os.path.isabs(p) or p.startswith("~"):
    raise ValueError(f"artifact path must be relative and in-workspace: {path!r}")
if ".." in PurePosixPath(p).parts:
    raise ValueError(f"artifact path must not escape the workspace ('..'): {path!r}")
return p
```

Invariant enforce tại construct — `decompose_agent/node.py:125-128`:

```python
if self.kind not in VALID_KINDS:
    raise ValueError(f"Node.kind must be one of {sorted(VALID_KINDS)}, got {self.kind!r}")
if self.status not in VALID_STATUSES:
    raise ValueError(f"Node.status must be one of {sorted(VALID_STATUSES)}, got {self.status!r}")
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò trong pattern | Code thật (hex_agent) | Trong bản distill (`node_factory_validation.py`) |
|-----------------------|-----------------------|--------------------------------------------------|
| Factory method (entry) | `Node.from_dict` (143-158), `DoneWhen.from_dict` (71-91) | `Node.from_dict`, `DoneWhen.from_dict` |
| Enforce invariant lúc dựng | `__post_init__` (122-140 / 58-69) | `__post_init__` (Node + DoneWhen) |
| Reverse cho persistence | `as_dict` (160-176 / 93-99) | `as_dict` (round-trip) |
| Specification — chống forgery | `FORBIDDEN_VERDICT_KEYS` check (76-81) | `forged = extra & FORBIDDEN_VERDICT_KEYS` |
| Specification — path predicate | `assert_safe_relpath` (33-47) | `assert_safe_relpath` |
| Aggregate frozen, mutate qua replace | `@dataclass(frozen=True)` Node (102-103) | `@dataclass(frozen=True)` + `dataclasses.replace` |
| Value object lồng nhau | `DoneWhen` (50-99) trong `Node.done_when` | `DoneWhen` trong `Node.done_when` |

---

## 4. Bản rút gọn chạy được

File: [`node_factory_validation.py`](node_factory_validation.py) — `python3 node_factory_validation.py` (exit 0).

Mô phỏng đầy đủ:
- Factory `Node.from_dict` dựng DoneWhen lồng nhau qua factory của nó; round-trip
  `from_dict(as_dict(n)).as_dict() == n.as_dict()`.
- Specification chống forgery: lần lượt từ chối cả 5 key `verdict/passed/status/score/done`.
- Specification path-jail: chặn `/etc/passwd`, `~/secret`, `../../escape.json`.
- Invariant `__post_init__`: chặn `kind` sai, `max_attempts < 1`.
- Frozen: gán trực tiếp `n.status = ...` raise `FrozenInstanceError`; chuyển status qua `replace`
  (tạo bản mới, bản gốc không đổi).
- Đối chứng (`naive_gate_without_spec`): gate ngây thơ tin `criterion["verdict"]` → worker tự
  nghiệm thu. Với Specification, criterion forgery bị chặn ngay tại factory, không bao giờ thành object.

Lược bỏ (không ảnh hưởng vai trò pattern):
- YAML loader, `load_tree`, runner filesystem → không cần; ta dựng node từ dict trực tiếp.
- `os.path.isabs` / `PurePosixPath` → kiểm `startswith("/")` + `split("/")` bằng string thuần
  (đủ minh hoạ predicate; giữ pure-stdlib và đơn giản).
- Các field phụ của Node (depth, order, activated_at, reduce_op, inputs) → giữ subset cốt lõi.
- `CMD_CHECKS` trong `ARTIFACTLESS_CHECKS` → rút gọn còn `{"all_children_done"}`.
- **Spec cmd-gate (`expect_code`)** — code thật có thêm một Specification thứ hai trong
  `DoneWhen.__post_init__` (`decompose_agent/node.py:63-65`, dựa trên `CMD_CHECKS` ở `:26`):
  một `cmd` check KHÔNG được tự đặt `expect_code` (gate cố định success = exit 0; worker đặt
  `expect_code` có thể giả pass). Bản distill bỏ guard này cùng với `CMD_CHECKS`. Đây cũng là
  một "spec áp lúc construct" thật sự — ghi rõ ở đây để không undersell mức phủ Specification.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Validation-as-construction làm constructor "nặng".** Mọi lỗi cấu trúc phát hiện sớm, nhưng nếu
  bạn cần dựng object tạm/incomplete (vd builder qua nhiều bước) thì enforce-tất-cả-tại-`__post_init__`
  gây vướng. Khi đó tách validation ra một bước `validate()` riêng có thể hợp lý hơn.
- **Specification ở đây là blacklist key (`FORBIDDEN_VERDICT_KEYS`) + whitelist (`_CRITERION_KEYS`).**
  Đơn giản và đúng cho domain này, nhưng không phải spec composable (`& | ~`) như bài gốc mô tả.
  Nếu rule cần kết hợp động (passing & recent & non-banned) thì cần Specification đầy đủ với
  `is_satisfied_by` + operator overloading — đây là phiên bản tối giản, "spec áp lúc construct".
- **Frozen + replace tốn allocation.** Mỗi lần đổi status tạo một object mới. Với cây rất lớn,
  cân nhắc; nhưng đổi lại ta có an toàn (không ai mutate ngầm) và dễ suy luận.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao việc từ chối key verdict phải xảy ra ở **factory (lúc dựng)** chứ không phải khi gate
   chấm điểm? Worker có thể lách bằng cách nào nếu kiểm tra này nằm muộn hơn?
2. `assert_safe_relpath` được mô tả là "predicate kiểu specification". Nó khác Specification đầy
   đủ (`is_satisfied_by` composable) ở điểm nào, và vì sao ở đây bản tối giản là đủ?
3. Node là frozen và chỉ đổi qua `dataclasses.replace`. Điều này quan hệ thế nào với invariant
   "một node sai cấu trúc không được tồn tại" — và vì sao mutate trực tiếp sẽ phá vỡ nó?
