"""Local RAG — health/ingest/search behind ports, with offline fakes. Epic E08.

Production uses Qdrant + fastembed, but all logic sits behind ``VectorStorePort``
and ``EmbedderPort`` so the acceptance suite runs fully offline against
``InMemoryVectorStore`` + ``FakeEmbedder`` (no docker, no network). See
``docs/rebuild_from_zero/E08_rag/BUILD_PLAN.md``.
"""
from __future__ import annotations

from rag.ports import Chunk, EmbedderPort, Hit, RagConfig, VectorStorePort
from rag.service import RagService

__all__ = [
    "Chunk",
    "Hit",
    "RagConfig",
    "EmbedderPort",
    "VectorStorePort",
    "RagService",
]
