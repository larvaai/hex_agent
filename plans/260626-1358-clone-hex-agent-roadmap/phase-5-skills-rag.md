---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 5 — Skills & RAG

> Epic: E07 + E08 · Cổng vào: Phase 3 (toolbox/safety) · Rời phase với: skill là hợp đồng role-agnostic + RAG health-gated chạy offline mà không cần Qdrant, sẵn sàng cho role (Phase 6) bind vào.

## 1. Mục tiêu & ranh giới

Hai mảnh độc lập, ghép qua cùng một chokepoint của kernel.

- **E07 Skills** — đọc `SKILL.md` thành `SkillSpec` bất biến (hợp đồng vận hành: allowed/forbidden tools, steps, report). Render theo **progressive disclosure**: chỉ lộ contract trước, lộ thủ tục sau. Skill **không biết role** — đây là cách bẻ vòng E07↔E09.
- **E08 RAG** — ingest/search trên vector store sau một **Port**. Logic (`RagService`) không bao giờ chạm Qdrant trực tiếp; mọi thao tác hạ tầng đi qua `VectorStorePort`/`EmbedderPort`. Chạy được offline (memory + FakeEmbedder), đổi sang Qdrant chỉ bằng config.

**Trong phạm vi:** parser SKILL.md, registry + disclosure, ports + value types, service health-gated, adapter memory/qdrant, wire feature, observability `rag.*`.

**Ngoài phạm vi:** role→allowlist (E09/Phase 6), lens catalog (chỉ chạm để lint), multi-agent graph (Phase 4). Skill cố tình **dừng ở interface** để E09 build phần content lên trên.

**Vì sao hai mảnh chung một phase?** Chúng không phụ thuộc nhau về code, nhưng dạy *cùng một bài học kiểm soát*: tách hợp đồng khỏi hiện thực. Skill tách *contract tool* khỏi *role dùng nó*; RAG tách *logic ingest/search* khỏi *Qdrant chạy nó*. Cùng một khuôn tư duy "seam trước, plug-in sau" — học một lần, áp hai chỗ.

## 2. Bạn sẽ xây gì (bản đồ module)

```
skills/
  spec.py          SkillSpec (frozen) + parse_skill()  ← parser SKILL.md
  registry.py      SkillRegistry: load + render(mode) + union_tools()
  library/*.md     skill thật: code_review.md, file_edit.md
rag/
  ports.py         Chunk, Hit, EmbedderPort, VectorStorePort, RagConfig  ← cái seam
  service.py       RagService: health-gate → ingest/search (chỉ chạm Port)
  chunking.py      collect_files() + chunk_text()  (cửa sổ overlap)
  embedders.py     FakeEmbedder (offline) | FastEmbedEmbedder (lazy, [rag])
  stores.py        InMemoryVectorStore (offline, health() switchable)
  stores_qdrant.py QdrantVectorStore (prod, optional, lazy import)
  feature.py       install(kernel): build_service() + 3 tool qua chokepoint
config/features.yaml   bật rag, chọn backend (memory mặc định)
docker-compose.rag.yml Qdrant local (chỉ cho backend qdrant + test tích hợp)
```

Hai nhánh `skills/` và `rag/` không phụ thuộc lẫn nhau. Điểm gặp duy nhất: cả hai phơi năng lực qua `kernel.registry` + `execute_tool`.

**Đường đi một lệnh `rag_search` (để thấy seam nằm đâu):**

```
caller → kernel.execute_tool("rag_search", args)        # chokepoint + tool.* event
  → RagSearchTool.execute(request)                      # rag/feature.py:89  (+ rag.search event)
    → RagService.search(query, top_k, threshold)        # rag/service.py:78
      → _require_healthy() → store.health()              # HEALTH-GATE: down → trả envelope, dừng
      → embedder.embed([query])                          # qua EmbedderPort
      → store.search(vector, k, threshold)               # qua VectorStorePort  ← SEAM
        → InMemory cosine | Qdrant query_points          # adapter cụ thể, service không biết
    ← dict {"ok", "hits": [...]}                         # envelope, kernel bọc CapabilityResult
```

Chú ý: từ `RagService` trở xuống, không có một dòng nào nhắc `qdrant`. Đổi adapter ở dòng cuối cùng là đổi toàn bộ hành vi hạ tầng mà không chạm 4 dòng phía trên nó.

**Đối xứng phía skill (một lần `render`):**

```
load_dir(library) → parse_skill(SKILL.md) → SkillSpec (frozen)   # skills/spec.py:98
selector cần chọn → registry.render(name, mode="contract")        # chỉ contract
step đã chọn skill → registry.render(name, mode="full")           # mới lộ Steps/Report
E09 cần allowlist  → registry.union_tools([names])                # union tool, không role
```

Cùng nguyên tắc: lộ ít nhất có thể ở mỗi nấc, và nơi tiêu thụ (selector, E09) không bao giờ đọc nhiều hơn nó cần.

**Config knobs (cần khi rebuild):**

| Knob | Mặc định | Ở đâu | Ý nghĩa |
|---|---|---|---|
| `rag.backend` | `memory` | `config/features.yaml:19` | `memory` (offline) hoặc `qdrant` (prod) |
| `score_threshold` | `0.8` | `ports.py:45` | điểm cosine tối thiểu mới tính là hit (inclusive) |
| `top_k` | `5` | `ports.py:46` | số hit trả về sau khi sort |
| `chunk_size`/`overlap` | `800`/`100` | `ports.py:43-44` | cửa sổ ký tự + chồng lấn |
| `qdrant_timeout` | `30.0` | `ports.py:51` | nới rộng vì tạo collection có thể chậm vài giây |

## 3. Dựng step-by-step

Thứ tự bắt buộc: hợp đồng trước, hạ tầng sau; offline trước, prod sau.

**B1 — Skill spec + parser** (`skills/spec.py`).
`SkillSpec` là `@dataclass(frozen=True)` chỉ chứa tên tool canonical, **không có trường role** (`spec.py:26`). `parse_skill` tách frontmatter YAML (`_split_frontmatter`, `spec.py:39`) rồi cắt body theo heading (`_split_sections`, `spec.py:50`); thiếu `name`/`description`/frontmatter → `ValueError` (`spec.py:103-106`). Hai mẹo parser cần để ý: heading match bằng *substring case-insensitive* nên "Allowed (tools)" và "Allowed Tools" tương đương (`spec.py:19-21`); và `_bullets` lọc placeholder (`""`, `none`, `n/a`, `-`) để section rỗng không sinh tool ma (`spec.py:23,76-85`).
*Tự kiểm:* `pytest tests/test_skills.py -k "parse or missing"` — 4 test xanh: `test_parse_extracts_contract_fields`, `test_missing_name_raises`, `test_missing_description_raises`, `test_missing_frontmatter_raises`.

**B2 — Registry + progressive disclosure** (`skills/registry.py`).
`render(name, mode="contract")` chỉ ghép description + Allowed + Forbidden; `mode="full"` mới thêm Steps + Report (`registry.py:57-76`); mode lạ → `ValueError` (`registry.py:58-59`). *Vì sao chia hai mode?* Một agent đang chọn skill chỉ cần biết **được phép làm gì** (contract) để quyết định — bơm cả thủ tục Steps vào lúc đó là nhồi context vô ích. Chỉ khi skill được chọn cho step hiện hành mới lộ `full`. Đây là kiểm soát *ngân sách context*, không phải bảo mật. `register` từ chối trùng tên thay vì ghi đè im lặng (`registry.py:22-26`). `union_tools` (`registry.py:79`) là *đóng góp phía skill* cho allowlist E09 — registry **không** tự nhắc role; gộp với core tool + áp forbidden-wins là việc của `RoleSpec` ở E09.

```python
# contract: chỉ hợp đồng — đủ để chọn skill
reg.render("code_review", mode="contract")   # ## code_review + Allowed + Forbidden
# full: thêm thủ tục — chỉ khi đã chọn skill cho step
reg.render("code_review", mode="full")        # ... + ### Steps + ### Report
```

*Tự kiểm:* `pytest tests/test_skills.py -k "render or union"` — `test_render_contract_excludes_steps_report`, `test_render_full_includes_steps_report`, `test_union_tools_across_skills` xanh.

**B3 — RAG ports + value types** (`rag/ports.py`).
Định nghĩa seam *trước* khi có bất kỳ adapter nào. **Value types** là `Chunk`/`Hit` frozen (`ports.py:8,16`) — đây là "tiền tệ" hai bên seam trao đổi: logic nói chuyện bằng `Chunk`/`Hit`, không bằng kiểu của Qdrant (`PointStruct`, `ScoredPoint`). Adapter chịu trách nhiệm dịch giữa value type và kiểu hạ tầng (xem `stores_qdrant.py:116-123` đóng gói, `:138-147` mở gói). **Ports** là `Protocol` `runtime_checkable` (`ports.py:24,31`) — dùng Protocol (structural typing) thay vì base class nghĩa là adapter không cần kế thừa gì, chỉ cần "trông giống" interface; test giả lập thoải mái. `RagConfig` (`ports.py:39`) gom toàn bộ knob (collection, threshold, top_k, qdrant_url/timeout) với `from_dict` lọc field lạ (`ports.py:53`) để config dư thừa không làm vỡ khởi tạo.
*Tự kiểm:* `python -c "from rag.ports import VectorStorePort; print('ok')"` — chạy được trên máy *không cài* qdrant-client, chứng minh ports không kéo theo dep.

**B4 — Service health-gated** (`rag/service.py`).
`_require_healthy()` (`service.py:30`) chạy **trước** mọi ingest/search; store unhealthy → trả envelope `dependency_unavailable`, không ném. Ingest đi qua sandbox jail (`resolve_in_workspace`, `service.py:47`) — đây là móc nối ngược về Phase 3 (safety): path do người dùng đưa vào không được thoát workspace; `SandboxError` thành envelope `code="sandbox"` chứ không crash. Trước khi upsert, service refuse *cardinality mismatch* (số vector ≠ số chunk) (`service.py:64-69`) để không bao giờ ghi một phần lệch; và gọi `delete_by_source` **trước** `upsert` (`service.py:71`) để re-ingest thay thế sạch chunk cũ. Mọi method trả envelope `{"ok": bool, ...}` để map thẳng thành tool result.
*Tự kiểm:* `pytest tests/test_rag.py` — health-gate chặn khi store down; ingest path ngoài workspace bị từ chối.

**B5 — Memory store + FakeEmbedder (offline)** (`rag/stores.py`, `rag/embedders.py`).
`InMemoryVectorStore` có `set_healthy()` để test bật/tắt cổng dependency mà không cần server thật (`stores.py:32`); search là cosine deterministic, bỏ qua chunk `vector is None`, sort theo `(-score, source, chunk_index)` rồi cắt `top_k` (`stores.py:47-56`). `FakeEmbedder` là bag-of-words hash normalize: token → bucket qua `blake2b` rồi chuẩn hoá L2 (`embedders.py:33-46`), nên text giống hệt cosine 1.0, text rời nhau 0.0 — đủ để thử `score_threshold` mà không tải model, không network. Chi tiết tinh tế: chunking dùng cửa sổ ký tự chồng lấn `step = size - overlap` (clamp ≥1), `overlap ≥ size` bị kẹp về step=1 nên không vòng lặp vô hạn (`chunking.py:23`).
*Tự kiểm:* `pytest tests/test_rag.py tests_audit/test_rag_edges_rigor.py` — xanh, không docker; chú ý `test_inmemory_score_threshold_is_inclusive_boundary` (biên `>=`) và `test_chunk_text_overlap_ge_size_is_clamped_to_step_one`.

**B6 — Qdrant adapter (prod, optional)** (`rag/stores_qdrant.py`).
`qdrant_client` import **lazy trong `__init__`** (`stores_qdrant.py:43`), và `__init__` chấp nhận `client` inject (`client: object | None`) — đây là cú mở để test bằng FakeClient mà không cần server. Collection tạo lười theo dim ở lần upsert đầu (`_ensure_collection`, `stores_qdrant.py:52`): kiểm tra tồn tại *ngoài* lock rồi create *trong* lock + double-check, nên dưới nhiều upsert đồng thời collection chỉ tạo đúng một lần (`stores_qdrant.py:57-73`). `upsert` validate cả batch (vector không None, không rỗng, đồng nhất dim) **trước** mọi network call (`stores_qdrant.py:104-112`) để batch xấu không nửa-ghi. Point id `uuid5(source::chunk_index)` (`stores_qdrant.py:28`); `delete_by_source` lọc theo payload `source` đã index keyword; `health()` bọc `try/except` → unreachable trả `{"ok": False}` (`stores_qdrant.py:83-90`).
*Tự kiểm:* `pytest tests_audit/test_rag_qdrant_adapter_contract.py` — dùng FakeClient (`:63`), không cần Qdrant thật; `test_lazy_collection_creation_is_singleton_under_concurrent_first_upsert` (`:218`) khoá hành vi tạo-một-lần.

**B7 — Wire feature qua chokepoint** (`rag/feature.py`).
`build_service` chọn backend từ config: `memory` mặc định (InMemory + FakeEmbedder), `qdrant` import lazy QdrantVectorStore + FastEmbedEmbedder; backend lạ → `ValueError` (`feature.py:30-42`). `install` đăng ký `FeatureDescriptor` + 3 tool vào `kernel.registry` (`feature.py:109-121`). Mỗi wrapper (`RagHealthTool`/`RagIngestTool`/`RagSearchTool`) phát thêm event ngữ nghĩa `rag.health`/`rag.ingest`/`rag.search` (`feature.py:72,81,90`) kèm lineage session từ `request.context.event_fields()` (`feature.py:61-68`), song song `tool.*` mà kernel phát ở chokepoint. Service vẫn là object logic thuần — kernel mới là bên bọc dict thành `CapabilityResult`.
*Tự kiểm:* `pytest tests_audit/test_roles_skills_config_integrity.py -k "tool_names_are_known"` — `test_bundled_skill_tool_names_are_known_to_runtime` xanh.

## 4. Class & biến kiểm soát (cái neo)

| Neo | Ở đâu | Vai trò kiểm soát |
|---|---|---|
| `VectorStorePort` / `EmbedderPort` | `rag/ports.py:24,31` | Seam: logic chỉ thấy interface, không thấy Qdrant |
| `RagService._require_healthy` | `rag/service.py:30` | Health-gate: chặn ingest/search khi dep down |
| `QdrantVectorStore.health` | `rag/stores_qdrant.py:83` | Không ném → dependency-failure là control-flow |
| `_point_id` (uuid5) | `rag/stores_qdrant.py:28` | Id ổn định → re-upsert ghi đè, không nhân bản |
| `SkillSpec` (frozen, no role) | `skills/spec.py:26` | Hợp đồng role-agnostic → bẻ vòng E07↔E09 |
| `SkillRegistry.render(mode)` | `skills/registry.py:57` | Progressive disclosure: contract trước, steps sau |

**Seam = Port (logic không thấy infra):**

```python
class RagService:
    def __init__(self, store: VectorStorePort, embedder: EmbedderPort, config: RagConfig):
        self._store = store          # chỉ Protocol — có thể là memory hoặc qdrant
        self._embedder = embedder
        self._cfg = config
```

**Health-gate trước mọi việc (service.py:30):**

```python
def _require_healthy(self) -> dict | None:
    h = self._store.health()
    if not h.get("ok"):
        return {"ok": False, "code": "dependency_unavailable", "error": ...}
    return None  # khoẻ → cho chạy tiếp
```

**health() không bao giờ ném (stores_qdrant.py:83):**

```python
def health(self) -> dict:
    try:
        ...
        return {"ok": True, "collection": self.collection, "count": count}
    except Exception as exc:   # server chết → trả ok=False, KHÔNG raise
        return {"ok": False, "collection": self.collection, "count": 0, "error": str(exc)}
```

**Point id ổn định → re-ingest không nhân bản (stores_qdrant.py:28):**

```python
def _point_id(source: str, chunk_index: int) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, f"{source}::{chunk_index}"))
```

## 5. Invariant của phase

1. **Health-gate trước ingest/search.** `_require_healthy()` chạy đầu tiên trong `ingest`/`search` (`service.py:43,86`). Không có đường tắt nào upsert/query khi store unhealthy. *Kiểm:* lật `set_healthy(False)` rồi gọi ingest → phải nhận `code="dependency_unavailable"`, store không bị chạm.
2. **Logic chỉ chạm infra qua Port.** `RagService` chỉ giữ `VectorStorePort`/`EmbedderPort`; không `import qdrant_client`, không gọi HTTP. Đổi adapter = đổi 1 dòng config. *Kiểm:* `grep -n qdrant rag/service.py` phải rỗng.
3. **Tool đi qua `execute_tool`.** 3 tool RAG đăng ký vào `kernel.registry` (`feature.py:113-121`); middleware/observability bám vào chokepoint `execute_tool` (`core/kernel.py:106`), không gọi service tay. Vì thế bật/tắt feature, log, rate-limit đều là việc của kernel — service không biết.
4. **Skill role-agnostic.** `SkillSpec` không có trường role; `union_tools` chỉ trả tool union, để E09 tự gộp với core tool + áp forbidden-wins. *Kiểm:* `test_role_allowlist_is_union_minus_forbidden_with_forbidden_winning` (E09) chứng minh việc gộp nằm bên role, không bên skill.
5. **Offline by default.** Backend mặc định `memory` (`config/features.yaml:19`); optional dep `[rag]` không nằm trong base; pytest xanh không cần docker. *Kiểm:* toàn bộ suite Phase 5 chạy trên máy chưa từng `docker compose up`.

## 6. Pitfall / bug sẽ gặp

**`health()` ném exception → vỡ control-flow.**
*Triệu chứng:* server Qdrant tắt, `RagService.health()` hoặc gate ném `ConnectionError`, agent crash thay vì báo "dependency unavailable".
*Nguyên nhân:* quên bọc `try/except` trong adapter `health()`.
*Cách tránh:* `health()` luôn trả dict; unreachable → `{"ok": False}` (`rag/stores_qdrant.py:83-90`). Gate đọc `h.get("ok")` (`rag/service.py:33`).

**Nhồi qdrant-client vào base install.**
*Triệu chứng:* `pip install -e .` kéo theo `qdrant-client`/`fastembed`; `import rag.ports` chậm/fail trên máy không có dep.
*Nguyên nhân:* import top-level trong module dùng chung.
*Cách tránh:* dep nằm group `[rag]`; import **lazy** trong `__init__`/method (`rag/stores_qdrant.py:43`, `rag/embedders.py:53`, `rag/feature.py:36`). `stores.py`/`ports.py` không bao giờ import qdrant.

**Test bắt buộc cần docker.**
*Triệu chứng:* CI offline đỏ vì test cố kết nối Qdrant.
*Nguyên nhân:* không có nhánh offline.
*Cách tránh:* suite mặc định dùng `InMemoryVectorStore` + `FakeEmbedder`; adapter contract test dùng FakeClient (`tests_audit/test_rag_qdrant_adapter_contract.py:63`); `tests/test_rag_qdrant.py` **skip** khi Qdrant không reachable.

**Re-ingest tạo điểm trùng nếu id không ổn định.**
*Triệu chứng:* sửa 1 file rồi ingest lại → KB phình to, chunk cũ còn lẫn.
*Nguyên nhân:* dùng id ngẫu nhiên (uuid4) → mỗi upsert là điểm mới.
*Cách tránh:* id deterministic `uuid5(source::chunk_index)` (`rag/stores_qdrant.py:28`) để overwrite đúng chỗ; thêm `delete_by_source` trước upsert (`rag/service.py:71`) để dọn chunk đã biến mất sau khi sửa. Lưu ý: uuid5 lo *cập nhật tại chỗ* (cùng index ghi đè), `delete_by_source` lo *thu nhỏ* (file ngắn lại còn ít chunk hơn) — thiếu một trong hai thì re-ingest vẫn rò chunk cũ.

**Upsert nửa-ghi khi batch lệch dim.**
*Triệu chứng:* một batch có vector lẫn lộn kích thước → collection tạo sai width hoặc ghi một phần rồi lỗi.
*Nguyên nhân:* tạo collection / gọi network *trước* khi kiểm tra batch.
*Cách tránh:* validate toàn batch (không None, không rỗng, đồng nhất dim) **trước** mọi network call (`rag/stores_qdrant.py:104-112`); ở tầng service, refuse cardinality mismatch trước khi chạm store (`rag/service.py:64-69`).

**Skill bind cứng vào role → tái lập vòng E07↔E09.**
*Triệu chứng:* `SkillSpec` thêm trường `role`, registry suy allowlist theo role → E07 cần E09 và ngược lại.
*Nguyên nhân:* nhét content (mapping role) vào interface (skill).
*Cách tránh:* skill chỉ khai tool canonical (`skills/spec.py:8-10,26`); chiều thật là E07→E09. `union_tools` (`skills/registry.py:79`) là điểm duy nhất E09 tiêu thụ, registry không nhắc role.

## 7. Definition of Done

Tất cả xanh offline, không docker:

- `tests/test_skills.py` — parser contract, render disclosure (contract vs full), union_tools, duplicate-name reject, library lint clean.
- `tests/test_lens_catalog.py` — nếu chạm: mọi tool lens tham chiếu tồn tại trong hex, render được (`test_lens_catalog.py:33,44`).
- `tests_audit/test_rag_edges_rigor.py` — biên chunking/cosine/threshold inclusive, FakeEmbedder dim=1, lazy import fastembed.
- `tests_audit/test_rag_qdrant_adapter_contract.py` — point id deterministic, `health()` không ném, lazy collection singleton dưới concurrent upsert, upsert reject vector lệch dim, service reject cardinality mismatch trước network (`:109,119,140,218,247`).
- `tests_audit/test_roles_skills_config_integrity.py` — skill trigger roundtrip, parser reject schema sai, registry reject trùng tên, tool name khớp runtime (`:50,79,85,233`).

Cổng: `pytest tests/test_skills.py tests/test_rag.py tests_audit/test_rag_edges_rigor.py tests_audit/test_rag_qdrant_adapter_contract.py tests_audit/test_roles_skills_config_integrity.py` — 100% pass, không khởi Qdrant.

## 8. Vì sao tổ chức thế này giúp kiểm soát

Ba quyết định cấu trúc khoá lại quyền kiểm soát:

- **Port tách infra.** `RagService` chỉ thấy `VectorStorePort`. Đổi từ in-memory sang Qdrant (hay sang store khác sau này) = đổi `backend:` trong `config/features.yaml`, **không sửa một dòng logic**. Test chạy nhanh trên adapter giả; prod chạy adapter thật — cùng một interface.
- **Health-gate biến lỗi hạ tầng thành control-flow.** Vì `health()` không ném và service gate trước mọi việc, "Qdrant chết" là một nhánh `if` bình thường trả envelope, không phải exception phải bắt rải rác. Hệ thống suy biến *dự đoán được* thay vì crash.
- **Optional deps giữ base nhẹ.** Import lazy + group `[rag]` nghĩa là người clone repo chạy được skill + RAG-offline ngay, chỉ kéo qdrant/fastembed khi thật sự cần prod.
- **Interface trước, content sau** (skill role-agnostic) bẻ vòng phụ thuộc E07↔E09: định nghĩa hợp đồng (`SkillSpec` + `union_tools`) xong, role mới bind lên trên ở Phase 6. Đây là kỹ thuật tổng quát: khi hai epic vòng nhau, tách *seam* ra trước rồi mỗi bên hoàn thiện độc lập.

**Bằng chứng cụ thể — đổi memory → Qdrant chỉ 3 bước, không sửa logic:**

1. `pip install -e ".[rag]"` (kéo qdrant-client/fastembed — chỉ lúc này).
2. `docker compose -f docker-compose.rag.yml up -d` (Qdrant local).
3. Đổi `rag.backend: qdrant` trong `config/features.yaml`.

`RagService`, `rag/ports.py`, mọi caller giữ nguyên. `build_service` (`feature.py:35`) thấy `qdrant` thì lazy-import adapter prod. Đó là toàn bộ chi phí đổi hạ tầng.

**Điều gì vỡ nếu phá từng ranh giới (để thấy nó load-bearing):**

- Bỏ Port, gọi thẳng Qdrant trong service → test phải có Qdrant chạy; CI offline chết; đổi store phải sửa logic.
- Bỏ health-gate (hoặc để `health()` ném) → server down thành exception rải rác, agent crash giữa chừng thay vì suy biến gọn.
- Cho `SkillSpec` biết role → E07 cần E09, E09 cần E07, vòng phụ thuộc khoá cả hai epic không build được độc lập.

**Bài học:** kiểm soát không đến từ "code đúng" mà từ *ranh giới đặt đúng chỗ* — Port là ranh giới logic/infra, health-gate là ranh giới bình-thường/suy-biến, role-agnostic là ranh giới interface/content. Đặt đúng ba ranh giới này thì đổi hạ tầng, đổi backend, thêm role đều là thay đổi cục bộ; đặt sai một cái, mọi thay đổi lan ra toàn hệ.

---
*Điều hướng: ← [Phase 4](phase-4-graph-resume.md) · → [Phase 6](phase-6-roles-delegation.md)*
