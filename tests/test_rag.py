"""E08 RAG — acceptance tests (offline, deterministic; no docker/network).

AC map (docs/rebuild_from_zero/E08_rag/acceptance.md):
  S08.1 health gate        -> test_search_blocked_when_unhealthy / test_ingest_blocked_when_unhealthy
  S08.2 ingest filters     -> test_ingest_filters_extensions
  S08.3 re-ingest replace  -> test_reingest_replaces_source
  S08.4 search threshold   -> test_search_threshold_and_fields
  S08.5 sandbox            -> test_ingest_outside_workspace_rejected
"""
from __future__ import annotations

import pytest

from core.bootstrap import build_kernel
from rag.embedders import FakeEmbedder
from rag.ports import RagConfig
from rag.service import RagService
from rag.stores import InMemoryVectorStore


def make_service(*, healthy: bool = True, threshold: float = 0.8) -> tuple[RagService, InMemoryVectorStore]:
    store = InMemoryVectorStore(healthy=healthy)
    cfg = RagConfig(score_threshold=threshold)
    return RagService(store, FakeEmbedder(), cfg), store


def write(tmp_path, name: str, text: str):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# ── S08.1 health gate ───────────────────────────────────────────────────────
def test_search_blocked_when_unhealthy():
    svc, _ = make_service(healthy=False)
    out = svc.search("anything")
    assert out["ok"] is False
    assert out["code"] == "dependency_unavailable"
    assert "hits" not in out  # search never ran


def test_ingest_blocked_when_unhealthy(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    write(tmp_path, "a.md", "hello world")
    svc, _ = make_service(healthy=False)
    out = svc.ingest(".")
    assert out["ok"] is False and out["code"] == "dependency_unavailable"


def test_health_reports_collection_and_count(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    write(tmp_path, "a.md", "alpha alpha alpha")
    svc, _ = make_service()
    assert svc.health() == {"ok": True, "collection": "agent_kb", "count": 0}
    svc.ingest(".")
    assert svc.health()["count"] >= 1


# ── S08.2 ingest filters extensions ─────────────────────────────────────────
def test_ingest_filters_extensions(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    write(tmp_path, "doc.md", "alpha")
    write(tmp_path, "code.py", "beta")
    write(tmp_path, "notes.txt", "gamma")
    write(tmp_path, "image.png", "ignored binary")
    write(tmp_path, "data.json", "ignored json")
    svc, _ = make_service()
    out = svc.ingest(".")
    assert out["ok"] is True
    assert out["files"] == 3  # md/py/txt only
    assert all(s.endswith((".md", ".py", ".txt")) for s in out["sources"])


# ── S08.3 re-ingest replace ─────────────────────────────────────────────────
def test_reingest_replaces_source(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    write(tmp_path, "a.md", "alpha alpha alpha")
    svc, store = make_service()
    first = svc.ingest(".")
    count_after_first = store.health()["count"]
    second = svc.ingest(".")
    count_after_second = store.health()["count"]
    assert first["chunks"] == second["chunks"]
    assert count_after_first == count_after_second  # no duplication


# ── S08.4 search threshold + fields ─────────────────────────────────────────
def test_search_threshold_and_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    write(tmp_path, "match.md", "alpha alpha alpha")
    write(tmp_path, "other.md", "zeta zeta zeta")
    svc, _ = make_service(threshold=0.8)
    svc.ingest(".")
    out = svc.search("alpha alpha alpha")
    assert out["ok"] is True
    assert out["count"] == 1  # disjoint "zeta" doc scores 0.0, filtered out
    hit = out["hits"][0]
    assert hit["score"] >= 0.8
    assert "match.md" in hit["source"]
    assert hit["chunk_index"] == 0


def test_search_threshold_override_relaxes_filter(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    write(tmp_path, "a.md", "alpha beta gamma")
    write(tmp_path, "b.md", "alpha delta")  # partial overlap -> 0 < score < 1
    svc, _ = make_service(threshold=0.8)
    svc.ingest(".")
    strict = svc.search("alpha beta gamma")
    relaxed = svc.search("alpha beta gamma", score_threshold=0.1)
    assert relaxed["count"] > strict["count"]


# ── S08.5 sandbox ───────────────────────────────────────────────────────────
def test_ingest_outside_workspace_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path / "ws"))
    (tmp_path / "ws").mkdir()
    svc, _ = make_service()
    out = svc.ingest("../../etc")
    assert out["ok"] is False and out["code"] == "sandbox"


# ── chokepoint wiring: tools cross execute_tool ─────────────────────────────
RAG_CFG = {
    "features": {"rag": {"enabled": True, "module": "rag.feature"}},
    "rag": {"backend": "memory"},
}


def test_rag_tools_via_execute_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    write(tmp_path, "kb.md", "alpha alpha alpha")
    kernel = build_kernel(RAG_CFG)

    health = kernel.execute_tool("rag_health")
    assert health["ok"] is True and health["capability"] == "rag_health"

    ingest = kernel.execute_tool("rag_ingest", {"path": "."})
    assert ingest["ok"] is True and ingest["data"]["files"] == 1

    search = kernel.execute_tool("rag_search", {"query": "alpha alpha alpha"})
    assert search["ok"] is True and search["data"]["count"] == 1


def test_build_service_rejects_unknown_backend():
    from rag.feature import build_service

    with pytest.raises(ValueError, match="backend"):
        build_service({"backend": "weaviate"})
