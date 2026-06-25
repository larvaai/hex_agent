"""Property/fuzz tests for parsers, budgets, condensation, chunking and vector math."""
from __future__ import annotations

import json
import math

import pytest
from hypothesis import given, strategies as st

from discipline import Budget, JsonGateError, condense, parse_action, parse_json_object
from rag.chunking import chunk_text
from rag.embedders import FakeEmbedder
from rag.ports import Chunk
from rag.stores import InMemoryVectorStore, _cosine

pytestmark = [pytest.mark.audit, pytest.mark.property]

safe_text = st.text(st.characters(blacklist_categories=("Cs",)), max_size=100)
json_scalar = st.none() | st.booleans() | st.integers() | safe_text
json_value = st.recursive(
    json_scalar,
    lambda children: st.lists(children, max_size=5)
    | st.dictionaries(safe_text, children, max_size=5),
    max_leaves=20,
)


@given(action_name=safe_text, payload=st.dictionaries(safe_text, json_value, max_size=8))
def test_parse_action_roundtrips_arbitrary_valid_json_object(action_name, payload):
    payload = {**payload, "action": action_name}
    encoded = json.dumps(payload, ensure_ascii=False)
    assert parse_action(encoded) == payload


@given(
    action_name=safe_text,
    prefix=st.text(alphabet=" abcXYZ:;\n\t", max_size=30),
    suffix=st.text(alphabet=" abcXYZ:;\n\t", max_size=30),
)
def test_json_gate_extracts_embedded_action_without_consuming_surrounding_noise(action_name, prefix, suffix):
    obj = {"action": action_name, "message": "ok"}
    raw = prefix + json.dumps(obj) + suffix
    assert parse_action(raw) == obj


@given(action_name=safe_text, fenced=st.booleans())
def test_json_gate_repairs_trailing_comma_with_or_without_fence(action_name, fenced):
    raw = json.dumps({"action": action_name, "values": [1, 2]})
    raw = raw[:-1] + ",}"
    if fenced:
        raw = "```json\n" + raw + "\n```"
    assert parse_action(raw)["action"] == action_name


@given(value=st.one_of(st.none(), st.booleans(), st.integers(), st.lists(json_scalar, max_size=5), safe_text))
def test_parse_json_object_rejects_every_non_mapping_json_value(value):
    with pytest.raises(JsonGateError):
        parse_json_object(json.dumps(value, ensure_ascii=False))


@given(raw=st.binary(max_size=300))
def test_json_gate_never_leaks_non_domain_exception_for_arbitrary_bytes(raw):
    text = raw.decode("utf-8", errors="replace")
    try:
        result = parse_json_object(text)
    except JsonGateError:
        return
    assert isinstance(result, dict)


@given(name=safe_text, args=st.dictionaries(safe_text, json_value, max_size=8))
def test_budget_tool_key_is_deterministic_across_dict_insertion_order(name, args):
    forward = dict(args.items())
    reverse = dict(reversed(list(args.items())))
    assert Budget.tool_key(name, forward) == Budget.tool_key(name, reverse)


def test_budget_thresholds_have_exact_not_off_by_one_semantics():
    budget = Budget(max_steps=2, max_parse_errors=2, max_same_tool_calls=2)
    assert not budget.step_exceeded()
    budget.record_step()
    budget.record_step()
    assert not budget.step_exceeded()
    budget.record_step()
    assert budget.step_exceeded()

    budget.record_parse_error()
    assert not budget.parse_exceeded()
    budget.record_parse_error()
    assert budget.parse_exceeded()

    key = Budget.tool_key("x", {})
    budget.record_tool_call(key)
    budget.record_tool_call(key)
    assert not budget.same_tool_exceeded(key)
    budget.record_tool_call(key)
    assert budget.same_tool_exceeded(key)


@given(text=safe_text, max_chars=st.integers(0, 50))
def test_condense_string_retains_exact_prefix_and_reports_exact_omitted_count(text, max_chars):
    result = condense(text, max_chars=max_chars)
    if len(text) <= max_chars:
        assert result == text
    else:
        assert result.startswith(text[:max_chars])
        assert result.endswith(f"... [+{len(text) - max_chars} chars]")


@given(values=st.lists(json_value, max_size=30), max_list=st.integers(0, 10))
def test_condense_list_never_retains_more_than_budgeted_items(values, max_list):
    result = condense(values, max_list=max_list)
    expected_size = len(values) if len(values) <= max_list else max_list + 1
    assert len(result) == expected_size
    if len(values) > max_list:
        assert result[-1] == f"... [+{len(values) - max_list} items]"


def _reference_chunks(text: str, size: int, overlap: int) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    if size <= 0:
        return [stripped]
    step = max(1, size - max(0, overlap))
    out: list[str] = []
    start = 0
    while start < len(stripped):
        candidate = stripped[start : start + size].strip()
        if candidate:
            out.append(candidate)
        if start + size >= len(stripped):
            break
        start += step
    return out


@given(text=safe_text, size=st.integers(-2, 40), overlap=st.integers(-5, 50))
def test_chunk_text_matches_independent_reference_implementation(text, size, overlap):
    assert chunk_text(text, size, overlap) == _reference_chunks(text, size, overlap)


@given(texts=st.lists(safe_text, min_size=1, max_size=20), dim=st.integers(1, 128))
def test_fake_embedder_is_deterministic_finite_and_normalized(texts, dim):
    embedder = FakeEmbedder(dim=dim)
    first = embedder.embed(texts)
    second = embedder.embed(texts)
    assert first == second
    for text, vector in zip(texts, first):
        assert len(vector) == dim
        assert all(math.isfinite(item) for item in vector)
        norm = math.sqrt(sum(item * item for item in vector))
        if any(char.isalnum() or char == "_" for char in text):
            assert norm == pytest.approx(1.0)
        else:
            assert norm == 0.0


@given(
    left=st.lists(st.floats(-100, 100, allow_nan=False, allow_infinity=False), min_size=1, max_size=20),
    right=st.lists(st.floats(-100, 100, allow_nan=False, allow_infinity=False), min_size=1, max_size=20),
)
def test_cosine_is_symmetric_finite_and_bounded(left, right):
    size = min(len(left), len(right))
    left = left[:size]
    right = right[:size]
    lr = _cosine(left, right)
    rl = _cosine(right, left)
    assert math.isfinite(lr)
    assert lr == pytest.approx(rl, abs=1e-12)
    assert -1.0000000001 <= lr <= 1.0000000001


def test_vector_store_sorting_is_total_and_deterministic_under_score_ties():
    store = InMemoryVectorStore()
    vector = [1.0, 0.0]
    store.upsert(
        [
            Chunk("z.md", 2, "z", vector),
            Chunk("a.md", 4, "a4", vector),
            Chunk("a.md", 1, "a1", vector),
        ]
    )
    hits = store.search(vector, top_k=10, score_threshold=0)
    assert [(hit.source, hit.chunk_index) for hit in hits] == [
        ("a.md", 1),
        ("a.md", 4),
        ("z.md", 2),
    ]
