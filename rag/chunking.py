"""Document collection + chunking. Epic E08."""
from __future__ import annotations

from pathlib import Path

INGEST_EXTS = (".md", ".txt", ".py")


def collect_files(root: Path) -> list[Path]:
    """Return ingestable files under ``root`` (recursive), filtered by extension."""
    if root.is_file():
        return [root] if root.suffix.lower() in INGEST_EXTS else []
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in INGEST_EXTS)


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Split text into overlapping character windows. Empty text -> no chunks."""
    text = text.strip()
    if not text:
        return []
    if size <= 0:
        return [text]
    step = max(1, size - max(0, overlap))
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunk = text[start : start + size].strip()
        if chunk:
            chunks.append(chunk)
        if start + size >= len(text):
            break
        start += step
    return chunks
