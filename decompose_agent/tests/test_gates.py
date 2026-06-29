"""Gate-1: code is the sole PASS/FAIL authority. Closed CHECK_VOCAB, artifact assertion
(exists/non-empty/jail/fresh) BEFORE the predicate, verdict written only by run_checks."""
from __future__ import annotations

import json
import os
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from decompose_agent import gates
from decompose_agent.node import Node


def mknode(done_when, activated_at=0.0):
    n = Node.from_dict({"id": "n", "kind": "work", "status": "active", "done_when": done_when})
    return replace(n, activated_at=activated_at)


def write(p: Path, text: str) -> Path:
    p.write_text(text, encoding="utf-8")
    return p


# ── unknown check: FAIL, never raise (anti-gaming: prose carries no check key) ──

def test_unknown_check_fails_without_raising(tmp_path):
    write(tmp_path / "a.txt", "x")
    node = mknode([{"check": "totally_bogus", "artifact": "a.txt"}])
    v = gates.run_checks(node, tmp_path)
    assert v.node_verdict == "FAIL"
    assert "unknown check" in v.results[0].reason.lower()


# ── artifact assertion runs BEFORE the predicate ──────────────────────────────

def test_missing_artifact_fails(tmp_path):
    node = mknode([{"check": "file_exists", "artifact": "missing.txt"}])
    v = gates.run_checks(node, tmp_path)
    assert not v.ok
    assert "missing" in v.results[0].reason.lower() or "not found" in v.results[0].reason.lower()


def test_empty_artifact_fails_even_file_exists(tmp_path):
    write(tmp_path / "empty.txt", "")  # size 0
    node = mknode([{"check": "file_exists", "artifact": "empty.txt"}])
    v = gates.run_checks(node, tmp_path)
    assert not v.ok
    assert "empty" in v.results[0].reason.lower()


def test_stale_artifact_auto_fails(tmp_path):
    p = write(tmp_path / "a.json", '{"x": 1}')
    activated = os.path.getmtime(p) + 1000.0  # node activated AFTER the artifact was written
    node = mknode([{"check": "file_exists", "artifact": "a.json"}], activated_at=activated)
    v = gates.run_checks(node, tmp_path)
    assert not v.ok
    assert "stale" in v.results[0].reason.lower()


def test_fresh_nonempty_artifact_passes(tmp_path):
    write(tmp_path / "a.txt", "content")
    node = mknode([{"check": "file_exists", "artifact": "a.txt"}], activated_at=0.0)
    assert gates.run_checks(node, tmp_path).ok


def test_jail_helper_rejects_escape(tmp_path):
    with pytest.raises(ValueError):
        gates.resolve_in_workspace(tmp_path, "../escape.txt")
    # a safe relative path resolves fine
    assert gates.resolve_in_workspace(tmp_path, "sub/ok.txt") == (tmp_path / "sub/ok.txt").resolve()


# ── per-check PASS/FAIL ───────────────────────────────────────────────────────

def test_file_nonempty_lines(tmp_path):
    write(tmp_path / "f.txt", "a\n\nb\nc\n")  # 3 non-empty lines
    assert gates.run_checks(mknode([{"check": "file_nonempty_lines", "params": {"min": 3}, "artifact": "f.txt"}]), tmp_path).ok
    assert not gates.run_checks(mknode([{"check": "file_nonempty_lines", "params": {"min": 4}, "artifact": "f.txt"}]), tmp_path).ok


def test_json_field_equals(tmp_path):
    write(tmp_path / "m.json", json.dumps({"metric": "cosine"}))
    ok = mknode([{"check": "json_field_equals", "params": {"ptr": "/metric", "value": "cosine"}, "artifact": "m.json"}])
    bad = mknode([{"check": "json_field_equals", "params": {"ptr": "/metric", "value": "l2"}, "artifact": "m.json"}])
    assert gates.run_checks(ok, tmp_path).ok
    assert not gates.run_checks(bad, tmp_path).ok


@pytest.mark.parametrize("val,expect", [(0.80, True), (0.79, False), (1.01, False), (1.0, True)])
def test_json_field_in_range_boundaries(tmp_path, val, expect):
    write(tmp_path / "r.json", json.dumps({"recall_at_5": val}))
    node = mknode([{"check": "json_field_in_range", "params": {"ptr": "/recall_at_5", "min": 0.80, "max": 1.0}, "artifact": "r.json"}])
    assert gates.run_checks(node, tmp_path).ok is expect


def test_json_field_exists(tmp_path):
    write(tmp_path / "r.json", json.dumps({"recall_at_5": 0.9}))
    assert gates.run_checks(mknode([{"check": "json_field_exists", "params": {"ptr": "/recall_at_5"}, "artifact": "r.json"}]), tmp_path).ok
    assert not gates.run_checks(mknode([{"check": "json_field_exists", "params": {"ptr": "/nope"}, "artifact": "r.json"}]), tmp_path).ok


def test_json_len_gte(tmp_path):
    write(tmp_path / "q.json", json.dumps({"queries": list(range(50))}))
    assert gates.run_checks(mknode([{"check": "json_len_gte", "params": {"ptr": "/queries", "n": 50}, "artifact": "q.json"}]), tmp_path).ok
    assert not gates.run_checks(mknode([{"check": "json_len_gte", "params": {"ptr": "/queries", "n": 51}, "artifact": "q.json"}]), tmp_path).ok


def test_row_count_gte(tmp_path):
    write(tmp_path / "c.jsonl", "\n".join(f'{{"i":{i}}}' for i in range(3)) + "\n")
    assert gates.run_checks(mknode([{"check": "row_count_gte", "params": {"n": 3}, "artifact": "c.jsonl"}]), tmp_path).ok
    assert not gates.run_checks(mknode([{"check": "row_count_gte", "params": {"n": 4}, "artifact": "c.jsonl"}]), tmp_path).ok


def test_grep_matches(tmp_path):
    write(tmp_path / "q.jsonl", '{"gold_id": 1}\n{"gold_id": 2}\n')
    assert gates.run_checks(mknode([{"check": "grep_matches", "params": {"pattern": "gold_id", "min": 2}, "artifact": "q.jsonl"}]), tmp_path).ok
    assert not gates.run_checks(mknode([{"check": "grep_matches", "params": {"pattern": "gold_id", "min": 3}, "artifact": "q.jsonl"}]), tmp_path).ok


def test_grep_absent(tmp_path):
    write(tmp_path / "ok.log", "all good\nstarting up\n")
    write(tmp_path / "bad.log", "all good\nTraceback (most recent call last)\n")
    assert gates.run_checks(mknode([{"check": "grep_absent", "params": {"pattern": "Traceback|ERROR"}, "artifact": "ok.log"}]), tmp_path).ok
    assert not gates.run_checks(mknode([{"check": "grep_absent", "params": {"pattern": "Traceback|ERROR"}, "artifact": "bad.log"}]), tmp_path).ok


# ── all_children_done: ≥1 child AND all done; 0 children FAILs (F1) ────────────

def test_all_children_done(tmp_path):
    node = mknode([{"check": "all_children_done"}])
    assert gates.run_checks(node, tmp_path, child_statuses=["done", "done"]).ok
    assert not gates.run_checks(node, tmp_path, child_statuses=["done", "pending"]).ok


def test_all_children_done_empty_fails_F1(tmp_path):
    node = mknode([{"check": "all_children_done"}])
    # all([]) is True in Python — the gate must block the empty case explicitly
    assert not gates.run_checks(node, tmp_path, child_statuses=[]).ok
    assert not gates.run_checks(node, tmp_path, child_statuses=None).ok


# ── AND semantics + verdict integrity ─────────────────────────────────────────

def test_node_done_iff_all_criteria_pass(tmp_path):
    write(tmp_path / "a.txt", "x")
    write(tmp_path / "r.json", json.dumps({"v": 0.5}))
    passing = {"check": "file_exists", "artifact": "a.txt"}
    failing = {"check": "json_field_in_range", "params": {"ptr": "/v", "min": 0.8, "max": 1.0}, "artifact": "r.json"}
    assert not gates.run_checks(mknode([passing, failing]), tmp_path).ok  # 1 FAIL → node FAIL
    good = {"check": "json_field_in_range", "params": {"ptr": "/v", "min": 0.0, "max": 1.0}, "artifact": "r.json"}
    assert gates.run_checks(mknode([passing, good]), tmp_path).ok


def test_verdict_is_frozen_and_code_written(tmp_path):
    write(tmp_path / "a.txt", "x")
    v = gates.run_checks(mknode([{"check": "file_exists", "artifact": "a.txt"}]), tmp_path)
    assert v.node == "n"
    assert v.results[0].check == "file_exists"
    with pytest.raises(FrozenInstanceError):
        v.node_verdict = "PASS"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        v.results[0].ok = True  # type: ignore[misc]


def test_test_passes_runs_whitelisted_cmd(tmp_path):
    import sys

    from decompose_agent import exec_cmd as E
    E.register_cmd("g_ok", [sys.executable, "-c", "raise SystemExit(0)"])
    E.register_cmd("g_fail", [sys.executable, "-c", "raise SystemExit(1)"])
    ok = mknode([{"check": "test_passes", "params": {"cmd_id": "g_ok"}}])
    fail = mknode([{"check": "test_passes", "params": {"cmd_id": "g_fail"}}])  # exit 1 → FAIL (success fixed at 0)
    unwhitelisted = mknode([{"check": "test_passes", "params": {"cmd_id": "g_ghost"}}])
    assert gates.run_checks(ok, tmp_path).ok
    assert not gates.run_checks(fail, tmp_path).ok
    assert not gates.run_checks(unwhitelisted, tmp_path).ok  # raw/unknown cmd_id can't pass a gate


def test_donewhen_construction_forbids_expect_code():
    from decompose_agent.node import DoneWhen
    with pytest.raises(ValueError):  # the worker can't pick the passing exit code
        DoneWhen.from_dict({"check": "test_passes", "params": {"cmd_id": "x", "expect_code": 0}})


@pytest.mark.parametrize("body", ['not json', '{}', '[1,2,3]', '{"x":"str"}', '{"x":null}', '   ', '{"x":'])
def test_json_field_in_range_never_raises_on_junk(tmp_path, body):
    write(tmp_path / "j.json", body)
    node = mknode([{"check": "json_field_in_range", "params": {"ptr": "/x", "min": 0.0, "max": 1.0}, "artifact": "j.json"}])
    v = gates.run_checks(node, tmp_path)  # must not raise
    assert v.node_verdict in ("PASS", "FAIL")
