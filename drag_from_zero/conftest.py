import importlib.util
import os
import sys

import pytest

# Flat layout: make `dragzero` importable when running pytest from the repo root.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def pytest_collection_modifyitems(config, items):
    """Skip opt-in layers cleanly when their prerequisite is absent.

    The default suite already deselects `browser`/`real_llm` via addopts. This is
    the belt-and-suspenders for `pytest -m browser` / `-m real_llm` run explicitly
    on a host that lacks playwright / a local model: the items SKIP, never error.
    """
    no_browser = importlib.util.find_spec("playwright") is None
    no_real_llm = not os.environ.get("OPENAI_BASE_URL")
    skip_browser = pytest.mark.skip(reason="needs playwright: pip install -e '.[test-browser]' && playwright install chromium")
    skip_real_llm = pytest.mark.skip(reason="needs OPENAI_BASE_URL pointing at a running local model")
    for item in items:
        if "browser" in item.keywords and no_browser:
            item.add_marker(skip_browser)
        if "real_llm" in item.keywords and no_real_llm:
            item.add_marker(skip_real_llm)
