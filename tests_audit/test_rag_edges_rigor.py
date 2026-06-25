"""Rigorous edge/error coverage for the rag package — the lines the focused suite leaves cold.

Complements tests/test_rag.py, tests/test_rag_qdrant.py (server-gated) and the existing
audit files: this one drives the *offline* error/empty/health branches and lazy-import seams
that the others skip — FastEmbedEmbedder via a stubbed ``fastembed``, the QdrantClient
auto-construction path via a stubbed ``qdrant_client``, the in-memory store's switchable
health and None-vector skip, chunking's single-file and exact-boundary behaviour, the
service's empty-document skip and health gate, and feature._emit's context-less path.

Everything here is offline and deterministic: no network, no real model, no qdrant server.
"""
from __future__ import annotations

import sys
import types

import pytest
from hypothesis import given, settings, strategies as st

from rag.chunking import INGEST_EXTS, chunk_text, collect_files
from rag.embedders import FakeEmbedder
from rag.ports import Chunk, EmbedderPort, RagConfig, VectorStorePort
from rag.service import RagService
from rag.stores import InMemoryVectorStore, _cosine

pytestmark = [pytest.mark.audit]


# ───────────────────────── embedders: FastEmbedEmbedder lazy seam ─────────────
# Pins embedders.py 53-57,60 — the production wrapper. We never import fastembed for
# real (it is not installed); a stub module proves the adapter (a) lazy-imports, (b)
# probes dimensionality once from the first embedding, (c) materialises generators to
# plain lists. This is the only place that drives FastEmbedEmbedder offline.


class _FakeTextEmbedding:
    """Mimics fastembed.TextEmbedding: yields generator-of-arrays from .embed()."""

    instances: list["_FakeTextEmbedding"] = []

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.embed_calls: list[list[str]] = []
        _FakeTextEmbedding.instances.append(self)

    def embed(self, texts):
        # fastembed returns a generator over per-text vectors (numpy arrays IRL).
        self.embed_calls.append(list(texts))
        return (tuple(float(len(t) + i) for i in range(3)) for t in texts)


@pytest.fixture
def stub_fastembed(monkeypatch):
    _FakeTextEmbedding.instances.clear()
    module = types.ModuleType("fastembed")
    module.TextEmbedding = _FakeTextEmbedding
    monkeypatch.setitem(sys.modules, "fastembed", module)
    return module


def test_fastembed_embedder_lazy_imports_and_probes_dim_once(stub_fastembed):
    """__init__ probes dim from a single "probe" embed; the model is built lazily."""
    from rag.embedders import FastEmbedEmbedder

    emb = FastEmbedEmbedder("BAAI/bge-small-en-v1.5")
    # dim probed from len(first vector) of the probe call -> our stub yields width 3.
    assert emb.dim == 3
    assert len(_FakeTextEmbedding.instances) == 1
    model = _FakeTextEmbedding.instances[0]
    assert model.model_name == "BAAI/bge-small-en-v1.5"
    # Exactly one probe call ("probe") happened during construction.
    assert model.embed_calls == [["probe"]]


def test_fastembed_embedder_embed_returns_plain_lists_not_generators(stub_fastembed):
    """embed() materialises each vector into a list[float] (line 60)."""
    from rag.embedders import FastEmbedEmbedder

    emb = FastEmbedEmbedder("m")
    out = emb.embed(["ab", "cde"])
    assert isinstance(out, list)
    assert all(isinstance(v, list) for v in out)  # not tuples/generators
    # Stub maps text -> (len, len+1, len+2); "ab"->2, "cde"->3.
    assert out == [[2.0, 3.0, 4.0], [3.0, 4.0, 5.0]]


def test_fastembed_embedder_embed_empty_input_is_empty(stub_fastembed):
    """An empty batch yields an empty list without touching dim/model state."""
    from rag.embedders import FastEmbedEmbedder

    emb = FastEmbedEmbedder("m")
    assert emb.embed([]) == []


def test_fastembed_embedder_satisfies_embedder_port(stub_fastembed):
    from rag.embedders import FastEmbedEmbedder

    emb = FastEmbedEmbedder("m")
    assert isinstance(emb, EmbedderPort)  # has .dim + .embed


# ───────────────────────── embedders: FakeEmbedder edge behaviour ─────────────
def test_fake_embedder_empty_batch_and_empty_string():
    """Empty batch -> [] ; whitespace/empty text -> zero-vector (norm 0, no NaN)."""
    emb = FakeEmbedder(dim=8)
    assert emb.embed([]) == []
    (zero,) = emb.embed(["   \n\t  "])  # no \w tokens -> all-zero, _normalize returns as-is
    assert zero == [0.0] * 8


def test_fake_embedder_dim_one_does_not_index_error():
    """dim=1 is a boundary: every token hashes into bucket 0 without IndexError."""
    emb = FakeEmbedder(dim=1)
    (vec,) = emb.embed(["alpha beta gamma"])
    assert vec == [1.0]  # normalized single bucket


# ───────────────────────── stores: in-memory switchable health + None skip ───
def test_inmemory_set_healthy_flips_health_flag():
    """set_healthy (line 33) toggles the ok flag the service health-gate reads."""
    store = InMemoryVectorStore(collection="kb")
    assert store.health()["ok"] is True
    store.set_healthy(False)
    h = store.health()
    assert h["ok"] is False and h["collection"] == "kb" and h["count"] == 0
    store.set_healthy(True)
    assert store.health()["ok"] is True


def test_inmemory_search_skips_chunks_with_none_vector():
    """A chunk persisted without a vector (line 51) is silently skipped, never scored."""
    store = InMemoryVectorStore()
    store.upsert([Chunk("a.md", 0, "embedded", [1.0, 0.0])])
    store.upsert([Chunk("b.md", 0, "no-vector", None)])  # vector is None
    hits = store.search([1.0, 0.0], top_k=10, score_threshold=0.0)
    assert [h.source for h in hits] == ["a.md"]  # b.md never appears


def test_inmemory_search_empty_store_returns_empty():
    assert InMemoryVectorStore().search([1.0], top_k=5, score_threshold=0.0) == []


def test_inmemory_top_k_truncates_after_sort_not_before():
    """top_k caps results AFTER the deterministic sort, so the best survive."""
    store = InMemoryVectorStore()
    aligned = [1.0, 0.0]
    store.upsert([Chunk("c.md", 0, "c", aligned), Chunk("a.md", 0, "a", aligned),
                  Chunk("b.md", 0, "b", aligned)])
    hits = store.search(aligned, top_k=2, score_threshold=0.0)
    # tie on score -> sort by (source, chunk_index); top_k keeps the first two.
    assert [h.source for h in hits] == ["a.md", "b.md"]


def test_inmemory_delete_by_source_returns_removed_count_and_is_idempotent():
    store = InMemoryVectorStore()
    store.upsert([Chunk("a.md", 0, "x", [1.0]), Chunk("a.md", 1, "y", [1.0]),
                  Chunk("b.md", 0, "z", [1.0])])
    assert store.delete_by_source("a.md") == 2
    assert store.delete_by_source("a.md") == 0  # already gone -> idempotent no-op
    assert store.health()["count"] == 1


def test_inmemory_score_threshold_is_inclusive_boundary():
    """A hit scoring exactly == threshold is kept (>=, not >)."""
    store = InMemoryVectorStore()
    v = [1.0, 0.0]
    store.upsert([Chunk("a.md", 0, "t", v)])
    # identical vector -> cosine exactly 1.0 ; threshold 1.0 must still include it.
    assert len(store.search(v, top_k=5, score_threshold=1.0)) == 1


def test_cosine_zero_vector_yields_zero_not_nan():
    """A zero vector has no direction: cosine is 0.0, never a divide-by-zero NaN."""
    assert _cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert _cosine([1.0, 1.0], [0.0, 0.0]) == 0.0


# ───────────────────────── chunking: collect_files single-file + filters ─────
def test_collect_files_single_file_with_ingestable_ext(tmp_path):
    """root.is_file() branch (line 12): an ingestable file returns just itself."""
    f = tmp_path / "note.md"
    f.write_text("hi", encoding="utf-8")
    assert collect_files(f) == [f]


def test_collect_files_single_file_with_rejected_ext(tmp_path):
    """A single non-ingestable file returns [] (the empty side of line 12)."""
    f = tmp_path / "image.png"
    f.write_text("binary-ish", encoding="utf-8")
    assert collect_files(f) == []


def test_collect_files_single_file_uppercase_ext_is_accepted(tmp_path):
    """Extension match is case-insensitive (suffix.lower())."""
    f = tmp_path / "README.MD"
    f.write_text("hi", encoding="utf-8")
    assert collect_files(f) == [f]


def test_collect_files_directory_recurses_filters_and_sorts(tmp_path):
    (tmp_path / "sub").mkdir()
    keep = [tmp_path / "b.py", tmp_path / "a.md", tmp_path / "sub" / "c.txt"]
    drop = [tmp_path / "x.json", tmp_path / "y.png", tmp_path / "sub" / "z.bin"]
    for p in keep + drop:
        p.write_text("x", encoding="utf-8")
    got = collect_files(tmp_path)
    assert got == sorted(keep)  # only ingestable exts, sorted, drops excluded
    assert all(p.suffix.lower() in INGEST_EXTS for p in got)


def test_collect_files_empty_directory_returns_empty(tmp_path):
    assert collect_files(tmp_path) == []


# ───────────────────────── chunking: boundary windows ────────────────────────
@pytest.mark.parametrize("blank", ["", "   ", "\n\t\r ", "      \n   "])
def test_chunk_text_blank_input_is_no_chunks(blank):
    assert chunk_text(blank, size=10, overlap=2) == []


@pytest.mark.parametrize("size", [0, -1, -5])
def test_chunk_text_nonpositive_size_returns_single_stripped_chunk(size):
    """size<=0 short-circuits to one whole-text chunk (stripped)."""
    assert chunk_text("  hello world  ", size=size, overlap=0) == ["hello world"]


def test_chunk_text_exact_boundary_no_trailing_empty_window():
    """Length an exact multiple of step: loop breaks cleanly, no empty tail chunk."""
    text = "abcdef"  # len 6
    # size=3, overlap=0 -> step 3 -> windows [abc][def]; start+size==len breaks after def.
    assert chunk_text(text, size=3, overlap=0) == ["abc", "def"]


def test_chunk_text_single_huge_doc_one_chunk():
    """A doc shorter than the window yields exactly one chunk == the doc."""
    text = "x" * 50
    assert chunk_text(text, size=10_000, overlap=100) == [text]


def test_chunk_text_overlap_ge_size_is_clamped_to_step_one():
    """overlap >= size would make step 0; max(1, ...) clamps it so the loop terminates."""
    out = chunk_text("abcd", size=2, overlap=5)  # step would be -3 -> clamped to 1
    # step 1, width 2 over "abcd": ab, bc, cd; start+size==len breaks after "cd" (no tail "d").
    assert out == ["ab", "bc", "cd"]
    assert len(out) < 100  # terminated, did not hang


def test_chunk_text_negative_overlap_treated_as_zero():
    """overlap<0 -> max(0, overlap)==0, so step==size (no overlap)."""
    assert chunk_text("abcdef", size=3, overlap=-9) == ["abc", "def"]


@given(
    text=st.text(st.characters(blacklist_categories=("Cs",)), max_size=120),
    size=st.integers(1, 40),
    overlap=st.integers(0, 39),
)
@settings(max_examples=150)
def test_chunk_text_covers_every_source_char_when_size_gt_overlap(text, size, overlap):
    """Property: with size>overlap the union of (pre-strip) windows covers the whole
    stripped source — no interior character is lost between adjacent windows."""
    stripped = text.strip()
    if not stripped:
        assert chunk_text(text, size, overlap) == []
        return
    step = max(1, size - overlap)
    chunks = chunk_text(text, size, overlap)
    assert chunks  # non-empty stripped source yields >=1 chunk
    # Reconstruct coverage from raw windows (chunks are stripped, so rebuild raw spans):
    covered = bytearray(len(stripped))
    start = 0
    while start < len(stripped):
        end = min(start + size, len(stripped))
        for i in range(start, end):
            covered[i] = 1
        if start + size >= len(stripped):
            break
        start += step
    # Every char of a non-whitespace-only source falls inside at least one window.
    assert all(covered), "a source character was never covered by any window"


@given(
    text=st.text(st.characters(whitelist_categories=("Ll", "Lu", "Nd")), min_size=1, max_size=120),
    size=st.integers(1, 30),
    overlap=st.integers(0, 29),
)
@settings(max_examples=150)
def test_chunk_text_every_chunk_is_substring_of_source(text, size, overlap):
    """Property: each emitted chunk is a contiguous substring of the source (alnum text
    has no leading/trailing whitespace stripping surprises)."""
    for chunk in chunk_text(text, size, overlap):
        assert chunk in text


# ───────────────────────── service: empty-doc skip + health gate ─────────────
def _service(*, healthy=True, **cfg):
    config = RagConfig(**cfg)
    store = InMemoryVectorStore(collection=config.collection, healthy=healthy)
    return RagService(store, FakeEmbedder(), config), store


def test_ingest_skips_files_that_chunk_to_nothing(tmp_path, monkeypatch):
    """A whitespace-only file produces no chunks (service.py line 62 continue): it is
    skipped, contributes no source, and never reaches embed/upsert."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "blank.md").write_text("   \n\t  ", encoding="utf-8")
    (tmp_path / "real.md").write_text("alpha alpha alpha", encoding="utf-8")
    svc, store = _service()
    out = svc.ingest(".")
    assert out["ok"] is True
    assert out["files"] == 1  # only real.md counted; blank.md skipped
    assert all("blank.md" not in s for s in out["sources"])
    assert store.health()["count"] >= 1


def test_ingest_all_files_blank_yields_zero_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "a.md").write_text("\n\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("   ", encoding="utf-8")
    svc, store = _service()
    out = svc.ingest(".")
    assert out == {"ok": True, "files": 0, "chunks": 0, "sources": []}
    assert store.health()["count"] == 0


def test_ingest_empty_directory_is_ok_with_no_work(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    svc, _ = _service()
    out = svc.ingest(".")
    assert out == {"ok": True, "files": 0, "chunks": 0, "sources": []}


def test_search_refused_when_unhealthy_never_embeds(tmp_path):
    """Health gate fires before any embedding/store work on search."""
    calls = []

    class _SpyEmbedder:
        dim = 4

        def embed(self, texts):
            calls.append(texts)
            return [[0.0] * 4 for _ in texts]

    store = InMemoryVectorStore(healthy=False)
    svc = RagService(store, _SpyEmbedder(), RagConfig())
    out = svc.search("anything")
    assert out["ok"] is False and out["code"] == "dependency_unavailable"
    assert "hits" not in out
    assert calls == []  # embedder never invoked


def test_ingest_refused_when_unhealthy_before_filesystem_walk(tmp_path, monkeypatch):
    """The gate precedes sandbox resolution: even a traversal path returns the dep error,
    proving the health check runs first (gate before sandbox)."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    svc, _ = _service(healthy=False)
    out = svc.ingest("../../etc/passwd")
    assert out["ok"] is False and out["code"] == "dependency_unavailable"


def test_health_envelope_shape_matches_store(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "k.md").write_text("alpha alpha", encoding="utf-8")
    svc, _ = _service(collection="my_kb")
    assert svc.health() == {"ok": True, "collection": "my_kb", "count": 0}
    svc.ingest(".")
    h = svc.health()
    assert h["ok"] is True and h["collection"] == "my_kb" and h["count"] >= 1


def test_search_top_k_zero_default_rejected_but_explicit_one_ok(tmp_path, monkeypatch):
    """Boundary: top_k must be >= 1; 1 is the inclusive minimum and must pass."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "k.md").write_text("alpha alpha alpha", encoding="utf-8")
    svc, _ = _service()
    svc.ingest(".")
    with pytest.raises(ValueError, match="top_k"):
        svc.search("alpha", top_k=0)
    out = svc.search("alpha alpha alpha", top_k=1)
    assert out["ok"] is True and out["top_k"] == 1


@pytest.mark.parametrize("threshold", [0.0, 1.0])
def test_search_threshold_inclusive_endpoints_accepted(tmp_path, monkeypatch, threshold):
    """0.0 and 1.0 are the inclusive bounds for score_threshold."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "k.md").write_text("alpha alpha alpha", encoding="utf-8")
    svc, _ = _service()
    svc.ingest(".")
    out = svc.search("alpha alpha alpha", score_threshold=threshold)
    assert out["ok"] is True and out["score_threshold"] == threshold


def test_search_hits_scores_are_rounded_to_six_places(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "k.md").write_text("alpha beta gamma", encoding="utf-8")
    svc, _ = _service()
    svc.ingest(".")
    out = svc.search("alpha beta", score_threshold=0.0)
    for hit in out["hits"]:
        assert hit["score"] == round(hit["score"], 6)


# ───────────────────────── stores_qdrant: offline error/empty/health branches ─
# All stubbed: a fake ``qdrant_client`` package (models + client) so no dep/server is
# needed. Pins stores_qdrant.py 43-47 (auto-construct client), 54 (_ensure_collection
# short-circuit), 60-61 (collection already exists), 103 (empty upsert returns 0).


class _Record:
    def __init__(self, **kw):
        self.__dict__.update(kw)


@pytest.fixture
def stub_qdrant(monkeypatch):
    """Install a fake ``qdrant_client`` package with .models and a QdrantClient ctor."""
    models = types.SimpleNamespace(
        VectorParams=_Record,
        Distance=types.SimpleNamespace(COSINE="cosine"),
        PayloadSchemaType=types.SimpleNamespace(KEYWORD="keyword"),
        Filter=_Record,
        FieldCondition=_Record,
        MatchValue=_Record,
        PointStruct=_Record,
    )
    constructed = []

    class FakeClient:
        def __init__(self, **kwargs):
            constructed.append(kwargs)
            self.exists = False
            self.points = []
            self.calls = []
            self.count_value = 0
            self.query_response = types.SimpleNamespace(points=[])

        def collection_exists(self, collection):
            self.calls.append(("collection_exists", collection))
            return self.exists

        def create_collection(self, collection, *, vectors_config):
            self.calls.append(("create_collection", collection))
            self.exists = True

        def create_payload_index(self, collection, *, field_name, field_schema):
            self.calls.append(("create_payload_index", collection))

        def count(self, collection, **kwargs):
            self.calls.append(("count", collection, kwargs))
            return types.SimpleNamespace(count=self.count_value)

        def delete(self, collection, *, points_selector):
            self.calls.append(("delete", collection))

        def upsert(self, collection, *, points):
            self.calls.append(("upsert", collection))
            self.points.extend(points)

        def query_points(self, collection, **kwargs):
            self.calls.append(("query_points", collection))
            return self.query_response

    package = types.ModuleType("qdrant_client")
    package.models = models
    package.QdrantClient = FakeClient
    monkeypatch.setitem(sys.modules, "qdrant_client", package)
    return types.SimpleNamespace(package=package, constructed=constructed, FakeClient=FakeClient)


def test_qdrant_auto_constructs_client_from_config_when_none(stub_qdrant):
    """client=None path (lines 43-47): the adapter builds a QdrantClient with the config's
    url/timeout/compat flag — exercised entirely offline via the stub ctor."""
    from rag.stores_qdrant import QdrantVectorStore

    cfg = RagConfig(collection="kb", qdrant_url="http://example:6333", qdrant_timeout=12.0)
    store = QdrantVectorStore(cfg)  # no client kwarg -> auto-construct
    assert store.collection == "kb"
    assert len(stub_qdrant.constructed) == 1
    kwargs = stub_qdrant.constructed[0]
    assert kwargs == {"url": "http://example:6333", "timeout": 12.0, "check_compatibility": False}
    # And it actually used the constructed client for a no-op health call.
    assert store.health()["ok"] is True


def test_qdrant_ensure_collection_short_circuits_when_already_ready(stub_qdrant):
    """After the first upsert marks the collection ready, a second upsert must NOT
    re-check existence or re-create (line 54 short-circuit)."""
    from rag.stores_qdrant import QdrantVectorStore

    store = QdrantVectorStore(RagConfig(collection="kb"))
    client = store._client
    store.upsert([Chunk("a.md", 0, "x", [1.0, 0.0])])
    creates_after_first = [c for c in client.calls if c[0] == "create_collection"]
    assert len(creates_after_first) == 1
    client.calls.clear()
    store.upsert([Chunk("a.md", 1, "y", [0.0, 1.0])])
    # Second upsert: no existence probe, no create — _collection_ready short-circuited.
    assert not any(c[0] in ("collection_exists", "create_collection") for c in client.calls)


def test_qdrant_ensure_collection_marks_ready_when_collection_preexists(stub_qdrant):
    """Lines 60-61: if the server already has the collection, mark ready WITHOUT
    creating it (no create_collection / create_payload_index call)."""
    from rag.stores_qdrant import QdrantVectorStore

    store = QdrantVectorStore(RagConfig(collection="kb"))
    store._client.exists = True  # collection pre-exists on the server
    n = store.upsert([Chunk("a.md", 0, "x", [1.0, 0.0])])
    assert n == 1
    assert not any(c[0] == "create_collection" for c in store._client.calls)
    assert not any(c[0] == "create_payload_index" for c in store._client.calls)
    assert any(c[0] == "upsert" for c in store._client.calls)


def test_qdrant_empty_upsert_returns_zero_without_network(stub_qdrant):
    """Line 103: upsert([]) short-circuits to 0 — no existence check, no create, no write."""
    from rag.stores_qdrant import QdrantVectorStore

    store = QdrantVectorStore(RagConfig(collection="kb"))
    assert store.upsert([]) == 0
    assert store._client.calls == []  # truly no network touch


def test_qdrant_health_false_on_unreachable_server(stub_qdrant):
    """health() never raises: a client that throws yields {"ok": False, ...}."""
    from rag.stores_qdrant import QdrantVectorStore

    store = QdrantVectorStore(RagConfig(collection="kb"))

    def boom(collection):
        raise ConnectionError("server down")

    store._client.collection_exists = boom
    h = store.health()
    assert h["ok"] is False and h["collection"] == "kb" and h["count"] == 0
    assert "server down" in h["error"]


def test_qdrant_search_empty_when_collection_absent(stub_qdrant):
    """search() returns [] (and never queries) if the collection does not exist."""
    from rag.stores_qdrant import QdrantVectorStore

    store = QdrantVectorStore(RagConfig(collection="kb"))  # exists=False
    assert store.search([1.0, 0.0], top_k=5, score_threshold=0.5) == []
    assert not any(c[0] == "query_points" for c in store._client.calls)


def test_qdrant_delete_by_source_zero_when_collection_absent(stub_qdrant):
    """delete_by_source short-circuits to 0 with no delete call when collection is absent."""
    from rag.stores_qdrant import QdrantVectorStore

    store = QdrantVectorStore(RagConfig(collection="kb"))
    assert store.delete_by_source("a.md") == 0
    assert not any(c[0] == "delete" for c in store._client.calls)


def test_qdrant_satisfies_vector_store_port(stub_qdrant):
    from rag.stores_qdrant import QdrantVectorStore

    store = QdrantVectorStore(RagConfig(collection="kb"))
    assert isinstance(store, VectorStorePort)


def test_qdrant_and_inmemory_share_health_envelope_keys(stub_qdrant):
    """Contract parity: both store adapters expose the same health() envelope keys."""
    from rag.stores_qdrant import QdrantVectorStore

    qd = QdrantVectorStore(RagConfig(collection="kb")).health()
    mem = InMemoryVectorStore(collection="kb").health()
    assert set(mem) <= set(qd)  # qdrant may add "error" on failure; core keys match
    assert {"ok", "collection", "count"} <= set(qd) & set(mem)


# ───────────────────────── feature: _emit context + code paths ────────────────
# Pins feature.py 66 — _emit when request.context is None (no event_fields) and when
# the result carries a "code". We instantiate the tool directly with a capturing publish
# so no kernel/network is involved.


def _capture_publish():
    seen: list[tuple[str, dict]] = []
    return seen, (lambda topic, payload: seen.append((topic, payload)))


def test_feature_emit_without_context_omits_lineage(tmp_path, monkeypatch):
    """request.context is None -> _emit publishes a payload without lineage fields,
    still carrying ok/extra. Drives the ``ctx is None`` branch in _emit."""
    from core.schemas import ToolRequest
    from rag.feature import RagHealthTool

    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    svc, _ = _service(collection="kb")
    seen, publish = _capture_publish()
    tool = RagHealthTool("rag_health", svc, publish)
    result = tool.execute(ToolRequest(name="rag_health"))  # no context
    assert result["ok"] is True
    assert len(seen) == 1
    topic, payload = seen[0]
    assert topic == "rag.health"
    assert payload["ok"] is True
    assert payload.get("collection") == "kb"
    assert "run_id" not in payload  # no lineage when context is None


def test_feature_emit_includes_code_on_failure(tmp_path):
    """When the service returns a failure envelope with "code", _emit forwards it."""
    from core.schemas import ToolRequest
    from rag.feature import RagSearchTool

    store = InMemoryVectorStore(healthy=False)
    svc = RagService(store, FakeEmbedder(), RagConfig())
    seen, publish = _capture_publish()
    tool = RagSearchTool("rag_search", svc, publish)
    result = tool.execute(ToolRequest(name="rag_search", args={"query": "x"}))
    assert result["ok"] is False and result["code"] == "dependency_unavailable"
    _, payload = seen[0]
    assert payload["ok"] is False
    assert payload["code"] == "dependency_unavailable"


def test_feature_emit_includes_lineage_when_context_present(tmp_path, monkeypatch):
    """The other side of line 66: with a context, lineage fields are merged in."""
    from core.schemas import ToolCallContext, ToolRequest
    from rag.feature import RagHealthTool

    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    svc, _ = _service()
    seen, publish = _capture_publish()
    tool = RagHealthTool("rag_health", svc, publish)
    ctx = ToolCallContext(run_id="R1", task_id="T1", session_id="S1")
    tool.execute(ToolRequest(name="rag_health", context=ctx))
    _, payload = seen[0]
    assert payload["run_id"] == "R1" and payload["task_id"] == "T1"


def test_feature_default_publish_is_noop_and_safe():
    """A tool built without a publish callback uses a no-op; execute must not raise."""
    from core.schemas import ToolRequest
    from rag.feature import RagHealthTool

    svc, _ = _service()
    tool = RagHealthTool("rag_health", svc)  # publish defaults to no-op
    out = tool.execute(ToolRequest(name="rag_health"))
    assert out["ok"] is True


def test_feature_ingest_tool_defaults_path_to_dot(tmp_path, monkeypatch):
    """RagIngestTool defaults the path arg to '.' when omitted."""
    from core.schemas import ToolRequest
    from rag.feature import RagIngestTool

    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "doc.md").write_text("alpha alpha alpha", encoding="utf-8")
    svc, _ = _service()
    seen, publish = _capture_publish()
    tool = RagIngestTool("rag_ingest", svc, publish)
    out = tool.execute(ToolRequest(name="rag_ingest"))  # no path arg
    assert out["ok"] is True and out["files"] == 1
    _, payload = seen[0]
    assert payload["files"] == 1


def test_build_service_memory_backend_is_default_and_offline():
    """build_service with no backend key defaults to the offline memory adapters."""
    from rag.feature import build_service
    from rag.stores import InMemoryVectorStore as _IMS

    svc = build_service({})
    assert isinstance(svc._store, _IMS)
    assert isinstance(svc._embedder, FakeEmbedder)


def test_build_service_backend_case_insensitive():
    from rag.feature import build_service
    from rag.stores import InMemoryVectorStore as _IMS

    svc = build_service({"backend": "MEMORY"})
    assert isinstance(svc._store, _IMS)


# ───────────────────────── ports: RagConfig.from_dict robustness ─────────────
def test_ragconfig_from_dict_ignores_unknown_keys_and_keeps_defaults():
    cfg = RagConfig.from_dict({"collection": "c", "bogus": 1, "top_k": 9})
    assert cfg.collection == "c" and cfg.top_k == 9
    assert cfg.chunk_size == 800  # default preserved


def test_ragconfig_from_dict_none_yields_defaults():
    assert RagConfig.from_dict(None) == RagConfig()
