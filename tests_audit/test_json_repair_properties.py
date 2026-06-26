"""Property tests for the JSON repair pipeline: superset-of-valid + mangle round-trips. Epic E02."""
from __future__ import annotations

import json

import pytest
from hypothesis import given, strategies as st

from discipline.json_gate import JsonGateError, parse_json_object

pytestmark = [pytest.mark.audit, pytest.mark.property]

safe_text = st.text(st.characters(blacklist_categories=("Cs",)), max_size=60)
json_scalar = st.none() | st.booleans() | st.integers() | safe_text
json_value = st.recursive(
    json_scalar,
    lambda children: st.lists(children, max_size=4) | st.dictionaries(safe_text, children, max_size=4),
    max_leaves=12,
)
json_object = st.dictionaries(safe_text, json_value, max_size=8)


@given(obj=json_object)
def test_valid_object_is_recovered_unchanged(obj):
    """Any valid JSON object survives the gate byte-for-byte (raw-first ladder)."""
    assert parse_json_object(json.dumps(obj, ensure_ascii=False)) == obj


@given(obj=json_object.filter(lambda d: bool(d)))
def test_trailing_comma_mangle_round_trips(obj):
    encoded = json.dumps(obj, ensure_ascii=False)
    mangled = encoded[:-1] + ",}"  # inject a trailing comma before the closing brace
    assert parse_json_object(mangled) == obj


@given(obj=json_object, fenced=st.booleans(), prefix=st.text(alphabet=" ab:;\n\t", max_size=12))
def test_fenced_or_prose_wrapped_round_trips(obj, fenced, prefix):
    encoded = json.dumps(obj, ensure_ascii=False)
    raw = ("```json\n" + encoded + "\n```") if fenced else (prefix + encoded)
    # Only assert recovery when the wrapper cannot itself be confused for content.
    if "{" in prefix or "}" in prefix:
        return
    assert parse_json_object(raw) == obj


@given(raw=st.binary(max_size=200))
def test_never_leaks_non_domain_exception(raw):
    text = raw.decode("utf-8", errors="replace")
    try:
        result = parse_json_object(text)
    except JsonGateError:
        return
    assert isinstance(result, dict)
