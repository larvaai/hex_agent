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
    if backend == "qdrant":  # pragma: no cover — needs Qdrant (see tests/test_rag_qdrant.py)
        from rag.embedders import FastEmbedEmbedder
        from rag.stores_qdrant import QdrantVectorStore

        store = QdrantVectorStore(cfg)
        embedder = FastEmbedEmbedder(cfg.model)
        return RagService(store, embedder, cfg)
    raise ValueError(f"Unknown rag backend: {backend!r}")


# ── tool wrappers ────────────────────────────────────────────────────────────
# Each wrapper publishes a semantic ``rag.*`` event in addition to the kernel's
# transport-level ``tool.*`` events, tagged with the call's session lineage so the
# event log stays filterable by run/task. The kernel chokepoint still wraps the
# returned dict into a CapabilityResult, so the service stays a pure logic object.
Publish = Any  # Callable[[str, dict], None]


class _RagTool:
    topic = ""

    def __init__(self, name: str, service: RagService, publish: Publish | None = None) -> None:
        self.name = name
        self._service = service
        self._publish = publish or (lambda topic, payload: None)

    def _emit(self, request: ToolRequest, result: dict[str, Any], **extra: Any) -> None:
        ctx = request.context
        payload: dict[str, Any] = dict(ctx.event_fields()) if ctx is not None else {}
        payload["ok"] = bool(result.get("ok"))
        if result.get("code"):
            payload["code"] = result["code"]
        payload.update({k: v for k, v in extra.items() if v is not None})
        self._publish(self.topic, payload)


class RagHealthTool(_RagTool):
    topic = "rag.health"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        result = self._service.health()
        self._emit(request, result, collection=result.get("collection"), count=result.get("count"))
        return result


class RagIngestTool(_RagTool):
    topic = "rag.ingest"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        result = self._service.ingest(str(request.args.get("path", ".")))
        self._emit(request, result, files=result.get("files"), chunks=result.get("chunks"))
        return result


class RagSearchTool(_RagTool):
    topic = "rag.search"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        args = request.args
        result = self._service.search(
            str(args.get("query", "")),
            top_k=args.get("top_k"),
            score_threshold=args.get("score_threshold"),
        )
        self._emit(
            request,
            result,
            count=result.get("count"),
            top_k=result.get("top_k"),
            score_threshold=result.get("score_threshold"),
        )
        return result


def install(kernel: AgentKernel, *, service: RagService | None = None) -> None:
    svc = service or build_service(getattr(kernel, "config", {}).get("rag"))
    publish = kernel.events.publish
    kernel.registry.register_feature(FEATURE)
    kernel.registry.register_tool(
        "rag_health", RagHealthTool("rag_health", svc, publish), feature_name=FEATURE.name
    )
    kernel.registry.register_tool(
        "rag_ingest", RagIngestTool("rag_ingest", svc, publish), feature_name=FEATURE.name
    )
    kernel.registry.register_tool(
        "rag_search", RagSearchTool("rag_search", svc, publish), feature_name=FEATURE.name
    )
