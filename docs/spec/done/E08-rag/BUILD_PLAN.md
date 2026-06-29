# E08 — Build Plan (các bước trước khi code)

> Gói pre-code cho E08 RAG. Nguyên tắc: **interface trước**, và **giữ test offline-deterministic**
> (đừng để pytest phụ thuộc Qdrant/docker). Đọc kèm `PRD.md`, `acceptance.md`.

## 0. Readiness (verify trên repo)

| Mục | Trạng thái | Ghi chú |
|---|---|---|
| E06 tool boundary | ✅ | `toolbox/` + feature `install(kernel)` pattern — RAG đăng ký như feature |
| Workspace jail | ✅ | `safety/sandbox.py::resolve_in_workspace` cho S08.5 |
| RAG/vector code | ❌ greenfield | chưa có gì |
| dep `qdrant-client` | ❌ thiếu | thêm vào optional group `rag` (đừng nhồi base install) |
| dep `fastembed` | ❌ thiếu | embed **local**, không cần API; nhưng tải model lần đầu |
| Qdrant runtime | ❌ external | cần docker → **không** dùng trong pytest; chỉ ở integration test |
| Generic StorePort | ❌ | `core/ports.py` chỉ có Tool/Delegation ports → định nghĩa `VectorStorePort` mới |

## 1. Quyết định kiến trúc then chốt
Giữ **Qdrant + fastembed** cho production (đúng PRD), **nhưng** bọc sau port để:
- **Test offline-deterministic**: dùng `InMemoryVectorStore` + `FakeEmbedder` (hash→vector cố định) →
  toàn bộ AC S08.1–S08.5 chạy xanh **không cần docker/network**, đúng kỷ luật smoke offline.
- Qdrant/fastembed chỉ là **adapter** thay được; lỗi infra không lan vào logic.

## 2. Contracts / seams (interface trước)
```python
# rag/ports.py
class EmbedderPort(Protocol):
    dim: int
    def embed(self, texts: list[str]) -> list[list[float]]: ...

@dataclass(frozen=True)
class Chunk:  source: str; chunk_index: int; text: str; vector: list[float] | None = None
@dataclass(frozen=True)
class Hit:    source: str; chunk_index: int; text: str; score: float

class VectorStorePort(Protocol):
    def health(self) -> dict: ...                              # {"ok": bool, "collection": ...}
    def delete_by_source(self, source: str) -> int: ...        # cho re-ingest replace
    def upsert(self, chunks: list[Chunk]) -> int: ...
    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]: ...

@dataclass(frozen=True)
class RagConfig:
    collection: str; model: str
    chunk_size: int = 800; chunk_overlap: int = 100
    score_threshold: float = 0.8; top_k: int = 5
    qdrant_url: str = "http://127.0.0.1:6333"
```
Adapters: `QdrantVectorStore` / `InMemoryVectorStore`; `FastEmbedEmbedder` / `FakeEmbedder`.

**Tool surface** (feature install, mỗi tool qua `execute_tool`):
- `rag_health()` → `{ok, collection, count}` — **gate**.
- `rag_ingest(path)` → resolve_in_workspace → thu `.md/.txt/.py` → chunk → embed → `delete_by_source` → upsert.
- `rag_search(query, top_k?, score_threshold?)` → health-gate → embed → search → lọc ngưỡng → hits có `source`+`chunk_index`.

**Invariants:** health-gate trước ingest/search; path qua sandbox jail; tool qua chokepoint; ext ngoài `.md/.txt/.py` bị skip.

## 3. AC → test map (offline qua fakes)

| AC | Test | Cách |
|---|---|---|
| S08.1 health gate | `test_rag::test_search_blocked_when_unhealthy` | FakeStore.health ok=false → search không chạy, trả dependency-failure |
| S08.2 ingest | `test_rag::test_ingest_filters_extensions` | thư mục có `.md/.py/.png` → chỉ 2 file vào store |
| S08.3 re-ingest replace | `test_rag::test_reingest_replaces_source` | ingest 2 lần cùng source → count ổn định, không dup |
| S08.4 search threshold | `test_rag::test_search_threshold_and_fields` | threshold=0.8 → chỉ hit≥0.8, có source+chunk_index |
| S08.5 sandbox | `test_rag::test_ingest_outside_workspace_rejected` | path ngoài workspace → SandboxError |
| (integration) | `test_rag_qdrant` | **skip nếu không có Qdrant** (`pytest.mark.skipif`) |

## 4. Build slices + DoD

| Slice | Nội dung | DoD |
|---|---|---|
| **S0 prep** | `rag/ports.py` + `InMemoryVectorStore` + `FakeEmbedder` + tool stubs + test skeleton | import sạch; pytest xanh (skips) |
| **S1 offline** | chunking + ingest/search/health logic vs fakes; sandbox; health-gate | S08.1–S08.5 xanh **offline, no docker** |
| **S2 prod adapter** | `QdrantVectorStore` + `FastEmbedEmbedder`; optional dep group `rag`; docker-compose; integration test skipif | integration xanh khi có Qdrant |
| **S3 wire + obs** | đăng ký feature trong `config/features.yaml`; events `rag.*`; tinh chỉnh threshold | rag chạy trong agent loop thật |

## 5. Quyết định đã chốt / open
- Giữ Qdrant+fastembed (prod) **+ port + fake** (test). Không đổi sang store khác trừ khi bạn yêu cầu.
- dep RAG vào **optional group `rag`**, không vào base.
- Open: reranker / metadata filter / source line-ranges (phase sau); chiến lược chunk (fixed vs semantic);
  có ship `docker-compose.yml` cho Qdrant không.

## 6. Bất biến phải giữ khi code
Tool qua `execute_tool`; ingest/search path qua sandbox jail; health-gate trước mọi search/ingest;
logic không phụ thuộc Qdrant trực tiếp (chỉ qua `VectorStorePort`); pytest không cần docker.
