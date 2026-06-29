# Flyweight (Structural) trong `hex_agent` — Hồ sơ ca thực tế

> **Một câu chốt (theo bài học gốc):** *Tách trạng thái thành **intrinsic** (bất biến,
> chia sẻ) và **extrinsic** (theo ngữ cảnh, truyền vào), rồi cache intrinsic trong
> Factory để N instance chỉ tốn bộ nhớ của K << N instance.*

Thư mục này tập hợp các nơi pattern **Flyweight** xuất hiện thật trong codebase
`hex_agent`, distill thành các bản chạy được self-contained (chỉ dùng thư viện chuẩn
Python 3.14). Mỗi case mở lại file thật, trích đúng `path:line`, và kèm bản rút gọn có
`demo()` + `assert`.

---

## Pattern này biểu hiện thế nào trong hex_agent

Flyweight trong `hex_agent` hiện ra ở ba dạng, đều xoay quanh **object bất biến dùng
chung để giảm chi phí bộ nhớ / tính toán** khi có rất nhiều thực thể nhẹ:

1. **Frozen dataclass constants** — hằng số bất biến chia sẻ qua các lần đăng ký
   (`FeatureDescriptor`, `ToolDescriptor`, các envelope schema frozen).
2. **AgentKernel như một shared frozen factory** — cache executor + config đã đông cứng,
   truy cập qua `SessionFactory` để tạo session nhẹ cho từng task. N session dùng chung
   K=1 kernel bất biến.
3. **Content-addressed caching trong DecompCache** — kết quả phân rã được đánh khóa theo
   hash của canonical spec và tái dùng mà không re-validate; đi kèm `Node` frozen quản lý
   qua chuyển-trạng-thái thay vì mutate.

Điểm chung của cả ba: **intrinsic state bất biến + chia sẻ**, **extrinsic state truyền
vào riêng**, và **immutability được bảo đảm ở mức ngôn ngữ** (`@dataclass(frozen=True)`,
`MappingProxyType`, `frozenset`).

---

## Các case con (flagship)

| # | Case | Vai trò Flyweight nổi bật | File thật chính |
|---|------|---------------------------|-----------------|
| [01](./01_agent_kernel_shared_pool/) | **AgentKernel: Shared Frozen Factory + Registry Pool** | Factory + Shared Intrinsic Pool; N session dùng chung 1 kernel bất biến | `core/kernel.py:14-22, 91-97`; `core/session.py:104-146`; `core/registry.py:43-112` |
| [02](./02_frozen_dataclass_constants/) | **Frozen Dataclass Constants** | Flyweight đơn giản nhất: intrinsic bất biến, hashable, chia sẻ | `core/schemas.py:11-129`; `core/registry.py:10-20`; `features/example_echo.py:9-25` |
| [03](./03_decomp_cache_content_addressed/) | **DecompCache: Content-Addressed Flyweight Pool** | Cache theo content address (hash của intrinsic spec); tái dùng kết quả đắt | `decompose_agent/store.py:27-92`; `decompose_agent/node.py:20, 102-140` |

Mỗi thư mục con có:
- `README.md` — 6 mục: bối cảnh thật, trích code thật, bảng ánh xạ vai trò, bản rút gọn,
  cái giá/khi nào không dùng, câu hỏi tự kiểm tra.
- `<name>.py` — bản distill chạy được (`python3 <name>.py`).

---

## Vai trò pattern (tổng hợp)

| Vai trò GoF       | Trong hex_agent                                                                 |
|-------------------|----------------------------------------------------------------------------------|
| FlyweightFactory  | `AgentKernel` + `CapabilityRegistry.resolve_tool`; `DecompCache`                 |
| Shared intrinsic  | `_tools` pool, `config` (đã `_deep_freeze`), `DEFAULT_DESCRIPTOR`, `FEATURE`     |
| Flyweight (immutable) | mọi `@dataclass(frozen=True)`: schemas, `Node`, `DoneWhen`, descriptors      |
| Context (extrinsic) | `KernelSession`; depth/order/status của `Node`                                 |
| Client            | `SessionFactory`; `install()`; vòng decompose/retry                              |
| Immutability guard | `_deep_freeze` (`core/kernel.py:14-22`) + `frozen=True` + `frozenset`           |

---

## Bảng vét cạn mọi occurrence

Xem [`CATALOG.md`](./CATALOG.md) — liệt kê đầy đủ mọi nơi pattern (hoặc dấu vết của nó:
frozen dataclass, pool dùng chung, `__slots__`, content-address) xuất hiện, kèm
`path:line`, mô tả, và độ rõ.

---

## Liên hệ bài học gốc

So với [`../11_Flyweight.md`](../11_Flyweight.md):
- "Receptor type chia sẻ ở hàng tỷ synapse" ↔ kernel/registry/descriptor chia sẻ ở N session.
- "Flyweight phải immutable" ↔ `frozen=True` + `_deep_freeze`; case 02 tái hiện đúng bug
  "mutable Flyweight" để đối chứng.
- "Cache vs Flyweight: `a is b`" ↔ case 03: cache hit trả về *cùng shared identity*
  (`c1 is c2`), không phải bản copy.
- "Singleton ⊂ Flyweight (K=1)" ↔ `DEFAULT_DESCRIPTOR`, `FEATURE` là Flyweight với 1 instance.
