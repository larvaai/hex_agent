"""Offline, exhaustive contract tests for the production Qdrant adapter."""
from __future__ import annotations

import sys
import threading
import types
from concurrent.futures import ThreadPoolExecutor

import pytest
from hypothesis import given, strategies as st

from rag.embedders import FakeEmbedder
from rag.ports import Chunk, RagConfig
from rag.service import RagService
from rag.stores import InMemoryVectorStore
from rag.stores_qdrant import QdrantVectorStore, _point_id


class Record:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __eq__(self, other):
        return type(self) is type(other) and self.__dict__ == other.__dict__


class VectorParams(Record):
    pass


class Filter(Record):
    pass


class FieldCondition(Record):
    pass


class MatchValue(Record):
    pass


class PointStruct(Record):
    pass


@pytest.fixture(autouse=True)
def fake_qdrant_models(monkeypatch):
    models = types.SimpleNamespace(
        VectorParams=VectorParams,
        Distance=types.SimpleNamespace(COSINE="cosine"),
        PayloadSchemaType=types.SimpleNamespace(KEYWORD="keyword"),
        Filter=Filter,
        FieldCondition=FieldCondition,
        MatchValue=MatchValue,
        PointStruct=PointStruct,
    )
    package = types.ModuleType("qdrant_client")
    package.models = models
    monkeypatch.setitem(sys.modules, "qdrant_client", package)


class FakeClient:
    def __init__(self):
        self.exists = False
        self.points = []
        self.calls = []
        self.count_value = 0
        self.query_response = types.SimpleNamespace(points=[])

    def collection_exists(self, collection):
        self.calls.append(("collection_exists", collection))
        return self.exists

    def create_collection(self, collection, *, vectors_config):
        self.calls.append(("create_collection", collection, vectors_config))
        self.exists = True

    def create_payload_index(self, collection, *, field_name, field_schema):
        self.calls.append(("create_payload_index", collection, field_name, field_schema))

    def count(self, collection, **kwargs):
        self.calls.append(("count", collection, kwargs))
        return types.SimpleNamespace(count=self.count_value)

    def delete(self, collection, *, points_selector):
        self.calls.append(("delete", collection, points_selector))

    def upsert(self, collection, *, points):
        self.calls.append(("upsert", collection, points))
        self.points.extend(points)

    def query_points(self, collection, **kwargs):
        self.calls.append(("query_points", collection, kwargs))
        return self.query_response


def _store(client=None):
    client = client or FakeClient()
    return QdrantVectorStore(RagConfig(collection="audit_collection"), client=client), client


@pytest.mark.audit
@pytest.mark.property
@given(
    source=st.text(st.characters(blacklist_categories=("Cs",)), max_size=100),
    index=st.integers(min_value=0, max_value=2**31 - 1),
)
def test_point_ids_are_deterministic_valid_and_collision_resistant_for_adjacent_indices(source, index):
    first = _point_id(source, index)
    assert first == _point_id(source, index)
    assert first != _point_id(source, index + 1)
    import uuid

    assert str(uuid.UUID(first)) == first


@pytest.mark.audit
def test_health_never_raises_and_reports_collection_count():
    store, client = _store()
    assert store.health() == {"ok": True, "collection": "audit_collection", "count": 0}
    client.exists = True
    client.count_value = 7
    assert store.health() == {"ok": True, "collection": "audit_collection", "count": 7}

    class Broken(FakeClient):
        def collection_exists(self, collection):
            raise ConnectionError("offline")

    broken, _ = _store(Broken())
    assert broken.health() == {
        "ok": False,
        "collection": "audit_collection",
        "count": 0,
        "error": "offline",
    }


@pytest.mark.audit
def test_first_upsert_creates_cosine_collection_index_and_exact_payloads():
    store, client = _store()
    chunks = [
        Chunk("source.md", 0, "alpha", [1.0, 0.0, 0.5]),
        Chunk("source.md", 1, "beta", [0.0, 1.0, 0.5]),
    ]

    assert store.upsert(chunks) == 2

    create = next(call for call in client.calls if call[0] == "create_collection")
    assert create[1] == "audit_collection"
    assert create[2].size == 3 and create[2].distance == "cosine"
    assert ("create_payload_index", "audit_collection", "source", "keyword") in client.calls
    assert [(point.id, point.vector, point.payload) for point in client.points] == [
        (_point_id("source.md", 0), [1.0, 0.0, 0.5], {"source": "source.md", "chunk_index": 0, "text": "alpha"}),
        (_point_id("source.md", 1), [0.0, 1.0, 0.5], {"source": "source.md", "chunk_index": 1, "text": "beta"}),
    ]


@pytest.mark.audit
@pytest.mark.parametrize(
    "chunks",
    [
        [Chunk("a", 0, "missing", None)],
        [Chunk("a", 0, "dim2", [1.0, 2.0]), Chunk("a", 1, "dim1", [1.0])],
        [Chunk("a", 0, "empty", [])],
    ],
)
def test_upsert_rejects_missing_inconsistent_or_empty_vectors_before_network(chunks):
    store, client = _store()
    with pytest.raises(ValueError, match="vector|dimension|embedded"):
        store.upsert(chunks)
    assert not any(call[0] in {"create_collection", "upsert"} for call in client.calls)


@pytest.mark.audit
def test_delete_by_source_uses_exact_keyword_filter_and_avoids_empty_delete():
    store, client = _store()
    assert store.delete_by_source("source.md") == 0
    assert not any(call[0] == "delete" for call in client.calls)

    client.exists = True
    client.count_value = 3
    assert store.delete_by_source("source.md") == 3
    delete = next(call for call in client.calls if call[0] == "delete")
    condition = delete[2].must[0]
    assert condition.key == "source"
    assert condition.match.value == "source.md"


@pytest.mark.audit
def test_search_forwards_limits_threshold_and_maps_missing_payload_defaults():
    store, client = _store()
    assert store.search([1.0], 5, 0.5) == []
    client.exists = True
    client.query_response = types.SimpleNamespace(
        points=[
            types.SimpleNamespace(payload={"source": "a", "chunk_index": 2, "text": "hit"}, score=0.9),
            types.SimpleNamespace(payload=None, score=0.5),
        ]
    )

    hits = store.search([1.0, 2.0], 7, 0.25)

    query = next(call for call in client.calls if call[0] == "query_points")
    assert query == (
        "query_points",
        "audit_collection",
        {"query": [1.0, 2.0], "limit": 7, "score_threshold": 0.25, "with_payload": True},
    )
    assert [(hit.source, hit.chunk_index, hit.text, hit.score) for hit in hits] == [
        ("a", 2, "hit", 0.9),
        ("", 0, "", 0.5),
    ]


@pytest.mark.audit
@pytest.mark.concurrency
def test_lazy_collection_creation_is_singleton_under_concurrent_first_upsert():
    barrier = threading.Barrier(16)

    class RacingClient(FakeClient):
        def collection_exists(self, collection):
            existed = self.exists
            barrier.wait(timeout=5)
            return existed

    client = RacingClient()
    store, _ = _store(client)
    chunks = [Chunk("a", 0, "text", [1.0, 0.0])]
    with ThreadPoolExecutor(max_workers=16) as pool:
        errors = list(pool.map(lambda _: _capture(lambda: store.upsert(chunks)), range(16)))

    assert errors == [None] * 16
    assert len([call for call in client.calls if call[0] == "create_collection"]) == 1
    assert len([call for call in client.calls if call[0] == "create_payload_index"]) == 1


def _capture(call):
    try:
        call()
    except Exception as exc:
        return exc
    return None


@pytest.mark.audit
def test_service_rejects_embedding_cardinality_mismatch_without_partial_write(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "doc.md").write_text("one two three four", encoding="utf-8")
    store = InMemoryVectorStore()

    class ShortEmbedder:
        dim = 1

        def embed(self, texts):
            return [[1.0]] * max(0, len(texts) - 1)

    service = RagService(store, ShortEmbedder(), RagConfig(chunk_size=3, chunk_overlap=0))
    with pytest.raises(ValueError, match="embedding.*count"):
        service.ingest(".")
    assert store.health()["count"] == 0


@pytest.mark.audit
@pytest.mark.parametrize(
    ("query", "top_k", "threshold", "message"),
    [
        ("", 5, 0.5, "query"),
        ("x", 0, 0.5, "top_k"),
        ("x", -1, 0.5, "top_k"),
        ("x", 5, -0.1, "score_threshold"),
        ("x", 5, 1.1, "score_threshold"),
    ],
)
def test_service_validates_search_inputs_before_embedding(query, top_k, threshold, message):
    service = RagService(InMemoryVectorStore(), FakeEmbedder(), RagConfig())
    with pytest.raises(ValueError, match=message):
        service.search(query, top_k=top_k, score_threshold=threshold)
