"""Shared fixtures for the decompose_agent unit suite (no LLM)."""
from __future__ import annotations

import pathlib

import pytest


@pytest.fixture
def fixtures_dir() -> pathlib.Path:
    return pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def rag_tree_path(fixtures_dir: pathlib.Path) -> pathlib.Path:
    return fixtures_dir / "rag_tree.yaml"
