# Case 03 — DecompCache: Content-Addressed Flyweight Pool cho kết quả decompose

> Flyweight áp dụng vào tình huống tốn kém thật: phân rã một task tree cần gọi LLM.
> Nếu gặp lại CÙNG spec (intrinsic: id + done_when + notes) lúc retry/resume thì tái
> dùng children đã cache thay vì decompose lại. Khóa cache là **hash của intrinsic
> state** (content-addressed). `Node` frozen đảm bảo cache an toàn khi chia sẻ.

---

## 1. Bối cảnh trong hex_agent

`decompose_agent` chia một task lớn thành cây node con. Bước phân rã gọi model ở
temperature 0 (`decompose_agent/store.py:1-9` mô tả: "retry/resume reuses the SAME
children and never re-samples a temp-0 model"). Đây là thao tác đắt và phải **xác định**
(deterministic) — cùng input phải cho cùng output.

Cơ chế:

- `canonical_spec(node)` (`decompose_agent/store.py:27-32`) tạo JSON xác định của
  **intrinsic** spec — chỉ gồm `id`, `done_when`, `notes`. Lưu ý nó **không** gồm
  extrinsic (depth/order/status).
- `decomp_id(node)` (`decompose_agent/store.py:35-37`) hash
  `node_id ‖ canonical_spec ‖ decomposer_version` bằng sha256 → khóa content-addressed.
  Cùng input ⇒ cùng id.
- `DecompCache.get(decomp_id)` (`decompose_agent/store.py:62-66`) đọc kết quả cache
  **verbatim, không re-validate** ("The staging file IS the cache").
- `commit()` (`decompose_agent/store.py:74-78`) stage trước, rồi `_attach`
  (`decompose_agent/store.py:79-85`) gắn children và lật parent sang `decomposed` bằng
  `dataclasses.replace` — vì `Node` là frozen (`decompose_agent/node.py:102-103`).
- `FORBIDDEN_VERDICT_KEYS` (`decompose_agent/node.py:20`) chặn forge verdict ngay lúc
  construct criterion (`decompose_agent/node.py:73-78`).

Vấn đề thật được giải: tránh gọi lại LLM cho cùng spec, và đảm bảo node bất biến để cache
chia sẻ an toàn (không lo bị mutate giữa chừng).

---

## 2. Trích đoạn code thật

`canonical_spec` + `decomp_id` — `decompose_agent/store.py:27-37`:

```python
def canonical_spec(node: Node) -> str:
    dw = sorted(
        json.dumps({"check": c.check, "params": c.params, "artifact": c.artifact}, sort_keys=True, ensure_ascii=False)
        for c in node.done_when
    )
    return json.dumps({"id": node.id, "done_when": dw, "notes": node.notes}, sort_keys=True, ensure_ascii=False)


def decomp_id(node: Node, decomposer_version: int = DEFAULT_DECOMPOSER_VERSION) -> str:
    blob = f"{node.id}{_US}{canonical_spec(node)}{_US}{decomposer_version}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
```

`get` đọc cache verbatim, không re-validate — `decompose_agent/store.py:62-66`:

```python
def get(self, decomp_id: str) -> list[dict] | None:
    p = self.staging_path(decomp_id)
    if not p.exists():
        return None
    return yaml.safe_load(p.read_text(encoding="utf-8"))  # verbatim — never re-validated
```

`_attach` chuyển trạng thái node frozen qua `replace` — `decompose_agent/store.py:79-85`:

```python
def _attach(self, tree, parent_id: str, children: list[dict]) -> None:
    parent = tree.nodes[parent_id]
    for i, c in enumerate(children):
        child = Node.from_dict({**c, "parent": parent_id, "status": "pending"})
        tree.nodes[child.id] = replace(child, depth=parent.depth + 1, order=len(tree.nodes) + i)
    tree.nodes[parent_id] = replace(parent, status="decomposed")
    tree.rebuild_children()
```

`Node` frozen + chặn forge verdict — `decompose_agent/node.py:102-103, 20, 73-78`:

```python
@dataclass(frozen=True)
class Node:
    """One unit of work on disk. Frozen — status transitions go through dataclasses.replace
    (the Navigator owns the tree; nothing else mutates a node)."""
    ...

FORBIDDEN_VERDICT_KEYS = frozenset({"verdict", "passed", "status", "score", "done"})
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Flyweight                          | Thành phần trong hex_agent                                             |
|--------------------------------------------|-----------------------------------------------------------------------|
| `FlyweightFactory` (cache theo key)        | `DecompCache` (`decompose_agent/store.py:53-92`)                       |
| Key function (trích intrinsic state)       | `canonical_spec` (`decompose_agent/store.py:27-32`)                    |
| Hash: intrinsic → khóa cache duy nhất      | `decomp_id` (`decompose_agent/store.py:35-37`)                         |
| `Flyweight` instance bất biến              | `Node`, `DoneWhen` frozen (`decompose_agent/node.py:50-99, 102-140`)   |
| Extrinsic state (ngữ cảnh, truyền vào)     | depth/order/status của node — bị `canonical_spec` bỏ qua              |
| Immutability guard                         | `@dataclass(frozen=True)` + `replace()` + `FORBIDDEN_VERDICT_KEYS`     |
| Cache hit = trả shared identity            | `get()` đọc verbatim, không re-validate (`store.py:62-66`)             |

---

## 4. Bản rút gọn chạy được

File: [`decomp_cache_content_addressed.py`](./decomp_cache_content_addressed.py) — chạy
`python3 decomp_cache_content_addressed.py`.

**Mô phỏng đúng:**
- `canonical_spec` / `decomp_id` y nguyên thuật toán thật (json sort_keys + sha256 +
  unit separator `␟`, version 3).
- `DecompCache.get/stage/commit/_attach` distill `decompose_agent/store.py:53-92`.
- `Node`/`DoneWhen` frozen + `DoneWhen.from_dict` chặn `FORBIDDEN_VERDICT_KEYS`.
- `expensive_decompose` đếm số lần "gọi LLM" để chứng minh cache hit không gọi lại.
- Assert: hai node cùng spec nhưng khác extrinsic → cùng `canonical_spec` và cùng
  `decomp_id`; cache hit trả về cùng object (`c1 is c2`); mutate node bị chặn; forge
  verdict bị từ chối; commit lật parent sang `decomposed`.

**Lược bỏ:** YAML + filesystem (`staging_path`, `os.replace`, `tree_state.yaml`) thay bằng
`dict` in-memory; LLM thật thay bằng `expensive_decompose` deterministic; bỏ
`decomp_sig` (thrash detector D4), `rebuild_children`, kiểm tra coverage/termination ở
gate-2 (`accept.py`). Trọng tâm chỉ giữ: content address + cache hit/miss + node bất biến.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Lifetime ngắn:** nếu mỗi spec chỉ xử lý đúng một lần (không retry/resume) thì cache
  vô nghĩa, chỉ thêm chi phí hash + lưu trữ.
- **Key space lớn không có eviction:** content address sinh khóa mới cho mỗi spec khác
  nhau; nếu spec biến thiên vô hạn, cache phình ra (store thật ghi file `<id>.yaml` —
  cần cơ chế dọn nếu key space lớn).
- **Cache ≠ value semantics:** ở đây cache trả về *cùng shared identity* (`c1 is c2`).
  Nếu caller vô tình mutate list children dùng chung thì hỏng — đây là lý do node phải
  frozen. Nếu cần bản copy độc lập thì không nên dùng kiểu trả-shared này.
- **Spec không deterministic** (ví dụ chứa timestamp): hash sẽ luôn khác → luôn miss →
  cache vô dụng. `canonical_spec` cố ý chỉ lấy phần intrinsic ổn định.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `canonical_spec` chỉ gồm `id + done_when + notes` mà **không** gồm
   `depth/order/status`? Liên hệ với khái niệm intrinsic vs extrinsic.
2. Hai node có `decomp_id` giống nhau thì `get()` trả về gì? Đây giống "Cache" hay
   "Flyweight" theo bảng so sánh trong bài học gốc (gợi ý: `a is b`)?
3. Nếu `Node` *không* frozen, kịch bản hỏng cụ thể nào có thể xảy ra khi hai phần của
   chương trình cùng đọc một kết quả cache?
