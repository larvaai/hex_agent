"""RAG feature — register rag_health/rag_ingest/rag_search behind the chokepoint. Epic E08.

``install(kernel)`` builds a :class:`RagService` from ``kernel.config['rag']`` and
registers three tools. Backend defaults to the offline ``memory`` adapters so the
feature works without docker; ``backend: qdrant`` selects the production adapters
(Slice S2). Each tool returns the service's dict envelope, which the kernel wraps
into a CapabilityResult.
"""
from __future__ import annotations

from typing import Any

from core.kernel import AgentKernel
from core.schemas import FeatureDescriptor, ToolRequest
from rag.embedders import FakeEmbedder
from rag.ports import RagConfig
from rag.service import RagService
from rag.stores import InMemoryVectorStore

FEATURE = FeatureDescriptor(
    name="rag",
    capabilities=("rag_health", "rag_ingest", "rag_search"),
    description="Local RAG: health-gated ingest/search over a vector store (Qdrant or in-memory).",
)


def build_service(config: dict[str, Any] | None) -> RagService:
    config = config or {}
    cfg = RagConfig.from_dict(config)
    backend = (config.get("backend") or "memory").lower()
    if backend == "memory":
        store = InMemoryVectorStore(collection=cfg.collection)
        embedder = FakeEmbedder()
        return RagService(store, embedder, cfg)
    if backend == "qdrant":  # pragma: no cover — Slice S2
        from rag.embedders import FastEmbedEmbedder
        from rag.stores_qdrant import QdrantVectorStore  # not yet implemented

        store = QdrantVectorStore(cfg)
        embedder = FastEmbedEmbedder(cfg.model)
        return RagService(store, embedder, cfg)
    raise ValueError(f"Unknown rag backend: {backend!r}")


class _RagTool:
    def __init__(self, name: str, service: RagService) -> None:
        self.name = name
        self._service = service


class RagHealthTool(_RagTool):
    def execute(self, request: ToolRequest) -> dict[str, Any]:
        return self._service.health()


class RagIngestTool(_RagTool):
    def execute(self, request: ToolRequest) -> dict[str, Any]:
        return self._service.ingest(str(request.args.get("path", ".")))


class RagSearchTool(_RagTool):
    def execute(self, request: ToolRequest) -> dict[str, Any]:
        args = request.args
        return self._service.search(
            str(args.get("query", "")),
            top_k=args.get("top_k"),
            score_threshold=args.get("score_threshold"),
        )


def install(kernel: AgentKernel, *, service: RagService | None = None) -> None:
    svc = service or build_service(getattr(kernel, "config", {}).get("rag"))
    kernel.registry.register_feature(FEATURE)
    kernel.registry.register_tool("rag_health", RagHealthTool("rag_health", svc), feature_name=FEATURE.name)
    kernel.registry.register_tool("rag_ingest", RagIngestTool("rag_ingest", svc), feature_name=FEATURE.name)
    kernel.registry.register_tool("rag_search", RagSearchTool("rag_search", svc), feature_name=FEATURE.name)
