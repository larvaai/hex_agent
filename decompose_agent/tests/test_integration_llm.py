"""Integration: a real local-35B drives a trivial 1-leaf tree to PASS.
Marked `integration` and SKIPPED unless LLM_BASE_URL is reachable (DEC-D3)."""
from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

import pytest

from decompose_agent import worker as W
from decompose_agent.solve import solve
from decompose_agent.tree import load_tree

pytestmark = pytest.mark.integration


def _llm_reachable() -> bool:
    url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
    parsed = urlparse(url)
    host, port = parsed.hostname or "localhost", parsed.port or 1234
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


@pytest.mark.skipif(not _llm_reachable(), reason="LLM_BASE_URL unreachable")
def test_real_35b_solves_trivial_leaf(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text(
        "- {id: t.leaf, parent: null, kind: work, status: pending, depends_on: [],\n"
        "   done_when: [{check: json_field_equals, params: {ptr: /ok, value: true}, artifact: out.json}]}\n"
    )
    tree = load_tree(p)
    res = solve(tree, W.LocalLLMWorker(), root="t", workspace_root=tmp_path)
    assert tree.nodes["t.leaf"].status == "done", f"blocked={res.blocked}"
