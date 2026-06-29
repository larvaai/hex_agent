"""Adversarial rigor for the inspect CLI + EventLogger durability — empty/missing/malformed run dirs, arg-parsing errors, and the run_id path-traversal guard."""
from __future__ import annotations

import itertools
import json
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from observability import EventLogger, attach_to_bus
from observability import inspect as insp
from observability.event_log import runs_dir

from core.events import EventBus

PROJECT_DIR = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# Empty / absent runs directory — covers _run_dirs base-missing and _resolve   #
# returning None (inspect.py lines 15, 22, 38, 48).                            #
# --------------------------------------------------------------------------- #


@pytest.mark.audit
def test_absent_runs_dir_yields_empty_not_crash():
    """AGENT_RUNS_DIR points at a not-yet-created path: every reader degrades to empty."""
    # The audit autouse fixture sets AGENT_RUNS_DIR -> tmp/runs which does NOT exist
    # until a logger creates it; assert nothing has materialised it.
    assert not runs_dir().exists()
    assert insp.list_runs() == []
    assert insp.read_summary() is None
    assert insp.read_summary("latest") is None
    assert insp.read_summary("anything") is None
    assert insp.read_events() == []
    assert insp.read_events("latest") == []
    assert insp.read_events("ghost", kind="X") == []


@pytest.mark.audit
def test_empty_existing_runs_dir_resolves_to_none():
    """Base dir exists but holds no run subdirs -> _resolve has no candidate (line 22)."""
    runs_dir().mkdir(parents=True, exist_ok=True)
    # A stray file (not a dir) in the base must be ignored by _run_dirs' is_dir() filter.
    (runs_dir() / "index.jsonl").write_text("{}\n", encoding="utf-8")
    (runs_dir() / "loose.txt").write_text("noise", encoding="utf-8")
    assert insp.list_runs() == []
    assert insp.read_summary() is None
    assert insp.read_events() == []


@pytest.mark.audit
def test_main_dispatch_over_empty_dir_prints_friendly_messages(capsys):
    """The CLI surface over an empty corpus is graceful: no traceback, exit 0."""
    runs_dir().mkdir(parents=True, exist_ok=True)
    assert insp.main(["list"]) == 0
    assert capsys.readouterr().out == ""  # no runs -> no lines

    assert insp.main(["summary"]) == 0
    assert "No summary found." in capsys.readouterr().out

    assert insp.main(["events"]) == 0
    assert capsys.readouterr().out == ""  # no events -> no lines


# --------------------------------------------------------------------------- #
# Unknown run id — _resolve scans and falls through (line 28); downstream      #
# readers then return None / [] for missing summary/events (lines 41, 51).     #
# --------------------------------------------------------------------------- #


@pytest.mark.audit
def test_unknown_run_id_resolves_to_none_even_when_others_exist():
    """A populated corpus with a wrong id must NOT silently fall back to latest."""
    real = EventLogger("real-run")
    real.finish("completed")
    assert "real-run" in insp.list_runs()

    assert insp.read_summary("does-not-exist") is None
    assert insp.read_events("does-not-exist") == []
    # but the real one is reachable
    assert insp.read_summary("real-run")["status"] == "completed"


@pytest.mark.audit
def test_summary_missing_file_returns_none_while_events_present(monkeypatch):
    """A run that emitted events but never finished has no summary.json (line 41)."""
    logger = EventLogger("unfinished")
    logger.emit("ActionEvent", tool="echo")
    # No finish() -> no summary.json on disk.
    assert (logger.run_dir / "events.jsonl").exists()
    assert not (logger.run_dir / "summary.json").exists()

    assert insp.read_summary("unfinished") is None
    # events.jsonl IS present, so read_events does not short-circuit on line 51.
    assert [e["kind"] for e in insp.read_events("unfinished")] == ["StateEvent", "ActionEvent"]


@pytest.mark.audit
def test_events_missing_file_returns_empty_when_dir_exists(monkeypatch):
    """A run dir with a summary but no events.jsonl -> read_events short-circuits (line 51)."""
    run = runs_dir() / "summary-only"
    run.mkdir(parents=True, exist_ok=True)
    (run / "summary.json").write_text(json.dumps({"run_id": "summary-only", "status": "x"}), encoding="utf-8")
    assert not (run / "events.jsonl").exists()

    assert insp.read_events("summary-only") == []
    assert insp.read_summary("summary-only")["status"] == "x"


# --------------------------------------------------------------------------- #
# 'latest' semantics & ordering — _run_dirs sorts by name DESC.                #
# --------------------------------------------------------------------------- #


@pytest.mark.audit
def test_latest_and_default_select_lexicographically_newest_dir():
    """run_id None and 'latest' both resolve to the reverse-name-sorted head."""
    for name in ("20240101_a", "20240301_c", "20240201_b"):
        run = runs_dir() / name
        run.mkdir(parents=True)
        (run / "summary.json").write_text(json.dumps({"run_id": name, "status": name}), encoding="utf-8")

    assert insp.list_runs() == ["20240301_c", "20240201_b", "20240101_a"]
    assert insp.read_summary()["status"] == "20240301_c"
    assert insp.read_summary("latest")["status"] == "20240301_c"
    assert insp.read_summary(None)["status"] == "20240301_c"


# --------------------------------------------------------------------------- #
# Inspect-layer malformed handling beyond what durability.py already pins.     #
# read_events skips non-dict JSON (list/scalar) AND honours filters together.  #
# --------------------------------------------------------------------------- #


@pytest.mark.audit
def test_read_events_skips_non_dict_json_and_blank_lines():
    """Valid JSON that is a list/number/string is not an event object -> dropped."""
    logger = EventLogger("mixedbag")
    logger.emit("Real", topic="t")
    with logger.events_path.open("a", encoding="utf-8") as h:
        h.write("\n")                 # blank
        h.write("   \n")              # whitespace-only
        h.write("{not valid json\n")  # truncated/garbage -> JSONDecodeError, skipped
        h.write("[1, 2, 3]\n")        # JSON list, not a dict
        h.write("42\n")               # JSON scalar
        h.write('"a string"\n')       # JSON string
        h.write('{"kind": "Tail"}\n')  # a real trailing dict

    kinds = [e.get("kind") for e in insp.read_events("mixedbag")]
    assert kinds == ["StateEvent", "Real", "Tail"]


@pytest.mark.audit
def test_kind_filter_excludes_nonmatching_and_keeps_matching():
    """Filtering is exact-equality on the 'kind' field."""
    logger = EventLogger("kinds")
    logger.emit("A", n=1)
    logger.emit("B", n=2)
    logger.emit("A", n=3)
    got = insp.read_events("kinds", kind="A")
    assert [e["n"] for e in got] == [1, 3]
    assert insp.read_events("kinds", kind="ZZZ") == []


@pytest.mark.audit
def test_topic_filter_drops_nonmatching_topics():
    """The topic= filter (inspect.py line 65) keeps only exact-topic events."""
    logger = EventLogger("topics")
    logger.emit("KernelEvent", topic="alpha", n=1)
    logger.emit("KernelEvent", topic="beta", n=2)
    logger.emit("KernelEvent", topic="alpha", n=3)
    got = insp.read_events("topics", topic="alpha")
    assert [e["n"] for e in got] == [1, 3]
    # kind AND topic together are conjunctive AND both filters can co-exclude.
    assert insp.read_events("topics", kind="KernelEvent", topic="missing") == []


# --------------------------------------------------------------------------- #
# CLI arg dispatch — the --kind happy path (line 90) and exit-code contract.   #
# Existing durability test pins the trailing-"--kind" error; we pin the rest.  #
# --------------------------------------------------------------------------- #


@pytest.mark.audit
def test_events_kind_flag_filters_and_prints_only_matching(capsys):
    """`events <run> --kind K` parses the value (line 90) and prints filtered JSONL."""
    logger = EventLogger("cliflt")
    logger.emit("Keep", marker="yes")
    logger.emit("Drop", marker="no")

    rc = insp.main(["events", "cliflt", "--kind", "Keep"])
    assert rc == 0
    out_lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    parsed = [json.loads(l) for l in out_lines]
    assert all(e["kind"] == "Keep" for e in parsed)
    assert {e["marker"] for e in parsed} == {"yes"}


@pytest.mark.audit
def test_events_flag_in_run_slot_resolves_latest_then_filters(capsys):
    """`events --kind K` (no explicit run id) resolves the latest run, then filters by kind.

    A token starting with '-' in the run-id slot is treated as a flag, not a run id, so
    the parser falls back to 'latest'. This pins the improved behaviour: the filter works
    with or without an explicit run id before it.
    """
    logger = EventLogger("only-run")
    logger.emit("Pick", v=1)
    logger.emit("Skip", v=2)

    rc = insp.main(["events", "--kind", "Pick"])
    assert rc == 0  # graceful, never crashes
    parsed = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert [e["v"] for e in parsed] == [1]  # latest run resolved, filtered to kind=Pick
    # The explicit-run-id form still works identically:
    rc2 = insp.main(["events", "only-run", "--kind", "Pick"])
    assert rc2 == 0
    parsed2 = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert [e["v"] for e in parsed2] == [1]


@pytest.mark.audit
def test_summary_cli_prints_indented_json_for_real_run(capsys):
    """summary subcommand pretty-prints the summary dict."""
    logger = EventLogger("sumcli")
    logger.count("tool_calls", 3)
    logger.finish("completed")

    rc = insp.main(["summary", "sumcli"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "completed"
    assert payload["metrics"]["tool_calls"] == 3


@pytest.mark.audit
def test_list_alias_ls_prints_run_names(capsys):
    """`list` and `ls` are aliases and print one run id per line."""
    EventLogger("aa").finish()
    EventLogger("bb").finish()
    for cmd in ("list", "ls"):
        assert insp.main([cmd]) == 0
        names = set(capsys.readouterr().out.split())
        assert {"aa", "bb"} <= names


@pytest.mark.audit
@pytest.mark.parametrize(
    ("argv", "expected_rc"),
    [
        ([], 0),                                  # default cmd == "list"
        (["list"], 0),
        (["ls"], 0),
        (["summary"], 0),
        (["summary", "nope"], 0),                 # missing run -> "No summary found."
        (["events"], 0),
        (["events", "nope"], 0),                  # missing run -> empty
        (["events", "x", "--kind"], 2),           # dangling --kind -> usage, rc 2
        (["events", "--kind"], 2),                # dangling --kind with no run -> rc 2
        (["totally-unknown-cmd"], 2),             # unknown subcommand -> usage, rc 2
        (["--help"], 2),                          # unknown flag treated as unknown cmd
    ],
)
def test_main_exit_codes_are_stable_and_never_raise(argv, expected_rc, capsys):
    """Argv dispatch returns documented exit codes and always emits *some* output."""
    # Ensure the corpus exists so 'latest' resolution paths are exercised too.
    EventLogger("seed").finish()
    assert insp.main(argv) == expected_rc
    # Drain output; the contract under test is the exit code + no exception.
    capsys.readouterr()


@pytest.mark.audit
def test_dangling_kind_flag_prints_usage_to_stdout(capsys):
    """The --kind error branch emits a usage hint (line 88) and returns 2."""
    EventLogger("u").finish()
    rc = insp.main(["events", "u", "--kind"])
    assert rc == 2
    assert "usage: inspect events" in capsys.readouterr().out


@pytest.mark.audit
def test_unknown_command_prints_top_level_usage(capsys):
    """Unknown subcommand hits the final usage line (line 94)."""
    rc = insp.main(["frobnicate"])
    assert rc == 2
    out = capsys.readouterr().out
    assert "usage: inspect" in out and "summary" in out and "events" in out


# --------------------------------------------------------------------------- #
# __main__ guard (inspect.py line 99): run the module as a script.            #
# --------------------------------------------------------------------------- #


@pytest.mark.audit
def test_module_runs_as_script_via_dash_m(tmp_path):
    """`python -m observability.inspect list` exits 0 and reaches the __main__ guard."""
    import os
    env = dict(os.environ)
    env["AGENT_RUNS_DIR"] = str(tmp_path / "scriptruns")
    # Seed one run so list has output, exercising the real code path end to end.
    seed_code = "from observability import EventLogger; EventLogger('script-seed').finish()"
    subprocess.run([sys.executable, "-c", seed_code], cwd=str(PROJECT_DIR), env=env, check=True)

    proc = subprocess.run(
        [sys.executable, "-m", "observability.inspect", "list"],
        cwd=str(PROJECT_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "script-seed" in proc.stdout


@pytest.mark.audit
def test_module_as_script_unknown_cmd_exits_2(tmp_path):
    """The __main__ guard propagates main()'s non-zero rc via SystemExit (line 99)."""
    import os
    env = dict(os.environ)
    env["AGENT_RUNS_DIR"] = str(tmp_path / "r")
    proc = subprocess.run(
        [sys.executable, "-m", "observability.inspect", "nope-not-a-cmd"],
        cwd=str(PROJECT_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "usage: inspect" in proc.stdout


# --------------------------------------------------------------------------- #
# SECURITY: EventLogger run_id path-traversal guard (event_log.py line 49).    #
# A path-like run_id would escape runs_dir(); the ctor must reject it.         #
# --------------------------------------------------------------------------- #


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.parametrize(
    "evil",
    [
        "../escape",
        "../../etc",
        "a/b",
        "a\\b",
        "..",
        "nested/../../x",
        "/abs/path",
        "/etc/passwd",
    ],
)
def test_path_like_run_id_is_rejected(evil):
    """Path-like run_ids must raise ValueError before any directory is created."""
    before = set(runs_dir().glob("*")) if runs_dir().exists() else set()
    with pytest.raises(ValueError, match="single path segment"):
        EventLogger(evil)
    after = set(runs_dir().glob("*")) if runs_dir().exists() else set()
    # The guard fires before mkdir, so no traversal directory leaks onto disk.
    assert after == before


@pytest.mark.audit
@pytest.mark.security
def test_absolute_run_id_does_not_write_outside_runs_dir(tmp_path):
    """An absolute run_id pointing at a sentinel dir must be refused, not honoured."""
    sentinel = tmp_path / "outside"
    sentinel.mkdir()
    with pytest.raises(ValueError):
        EventLogger(str(sentinel / "evil"))
    assert list(sentinel.iterdir()) == []  # nothing was written outside runs_dir


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.parametrize("ok", ["plain", "with_underscore", "20240101-120000", "abc123", "a.b"])
def test_safe_single_segment_run_ids_are_accepted(ok):
    """Benign single-segment ids (incl. a dot, but no slash/..) are allowed."""
    logger = EventLogger(ok)
    assert logger.run_id == ok
    assert logger.run_dir == runs_dir() / ok
    assert logger.run_dir.exists()
    # And the run is round-trippable through the inspector.
    assert ok in insp.list_runs()


# --------------------------------------------------------------------------- #
# EventLogger durability: JSONL is append-only valid, summary maps metrics.    #
# --------------------------------------------------------------------------- #


@pytest.mark.audit
def test_every_emitted_line_is_independently_valid_json():
    """The log is line-delimited JSON: each line parses to a dict on its own."""
    logger = EventLogger("jsonl")
    for i in range(25):
        logger.emit("Tick", i=i)
    logger.finish("completed")

    raw = logger.events_path.read_text(encoding="utf-8").splitlines()
    assert raw, "log should not be empty"
    for line in raw:
        obj = json.loads(line)  # must not raise
        assert isinstance(obj, dict)
        assert {"sequence", "timestamp", "run_id", "kind"} <= obj.keys()
    # sequence is 1-based, gapless, strictly increasing.
    seqs = [json.loads(l)["sequence"] for l in raw]
    assert seqs == list(range(1, len(seqs) + 1))


@pytest.mark.audit
def test_summary_metrics_match_counts_and_round_trip_through_inspect():
    """finish()'s metrics snapshot equals live counters and matches on-disk summary."""
    logger = EventLogger("metricmap")
    logger.count("tool_calls", 4)
    logger.count("llm_calls", 2)
    logger.count("parse_errors")
    summary = logger.finish("completed")

    assert summary["metrics"]["tool_calls"] == 4
    assert summary["metrics"]["llm_calls"] == 2
    assert summary["metrics"]["parse_errors"] == 1
    # Untouched metrics stay at zero (full keyset is always present).
    assert summary["metrics"]["tool_failures"] == 0

    on_disk = insp.read_summary("metricmap")
    assert on_disk == summary  # inspect reads back exactly what finish wrote


@pytest.mark.audit
def test_unknown_metric_is_ignored_not_invented():
    """count() of an unregistered key is a no-op; the metrics keyset is fixed."""
    logger = EventLogger("badmetric")
    keys_before = set(logger.metrics)
    logger.count("not_a_real_metric", 99)
    assert set(logger.metrics) == keys_before
    assert "not_a_real_metric" not in logger.metrics


@pytest.mark.audit
def test_bus_to_log_mirrors_topic_and_increments_metric():
    """attach_to_bus mirrors a published event into JSONL and bumps the right metric."""
    bus = EventBus()
    logger = EventLogger("bridge")
    attach_to_bus(logger, bus)
    bus.publish("tool.completed", {"tool": "echo"})
    bus.publish("tool.completed", {"tool": "llm.chat"})

    assert logger.metrics["tool_calls"] == 2
    assert logger.metrics["llm_calls"] == 1
    kinds = [e["kind"] for e in insp.read_events("bridge")]
    assert "KernelEvent" in kinds       # echo tool
    assert "LLMCallEvent" in kinds      # llm.* tool


@pytest.mark.audit
def test_bus_sink_covers_every_topic_to_metric_branch():
    """Exhaustively drive each topic branch in attach_to_bus' sink (event_log.py 111-132)."""
    bus = EventBus()
    logger = EventLogger("allbranches", enabled=False)
    attach_to_bus(logger, bus)

    bus.publish("tool.completed", {"tool": "echo"})              # tool_calls
    bus.publish("tool.failed", {"tool": "echo"})                 # tool_calls + tool_failures
    bus.publish("tool.completed", {"tool": "llm.chat"})          # tool_calls + llm_calls
    bus.publish("tool.failed", {"tool": "llm.chat"})             # +llm_calls +llm_failures
    bus.publish("graph.step", {})                                # steps
    bus.publish("graph.parse_error", {})                         # parse_errors
    bus.publish("graph.finish_blocked", {})                     # finish_gate_blocks
    bus.publish("delegation.started", {})                        # delegations
    bus.publish("delegation.progress", {})                       # delegation_progress
    bus.publish("delegation.finished", {"outcome": "failed"})    # delegation_failures
    bus.publish("delegation.finished", {"outcome": "success"})  # NO failure counted
    bus.publish("totally.unmapped", {})                          # no metric at all

    m = logger.metrics
    assert m["tool_calls"] == 4
    assert m["tool_failures"] == 2
    assert m["llm_calls"] == 2
    assert m["llm_failures"] == 1
    assert m["steps"] == 1
    assert m["parse_errors"] == 1
    assert m["finish_gate_blocks"] == 1
    assert m["delegations"] == 1
    assert m["delegation_progress"] == 1
    assert m["delegation_failures"] == 1  # only the non-success finish counted


@pytest.mark.audit
def test_finish_is_idempotent_for_side_effects_but_return_reflects_args():
    """Idempotent finish (event_log.py line 88): the second call performs NO new side
    effects (no extra terminal event, summary.json, or index line), yet it returns a
    freshly-built summary reflecting the SECOND call's args — so the returned dict and
    the persisted summary.json can legitimately diverge. We pin BOTH facts honestly.
    """
    logger = EventLogger("twice")
    first = logger.finish("completed", note="hi")
    events_after_first = logger.events_path.read_text(encoding="utf-8").splitlines()
    index_path = logger.run_dir.parent / "index.jsonl"
    index_after_first = index_path.read_text(encoding="utf-8").splitlines()
    disk_after_first = (logger.run_dir / "summary.json").read_text(encoding="utf-8")

    second = logger.finish("ignored-status")

    # The RETURN value reflects the 2nd call's args (the code rebuilds summary before the
    # first/not-first check) — this is the documented "callers stay simple" behaviour.
    assert second["status"] == "ignored-status"
    assert second["run_id"] == "twice"

    # SIDE EFFECTS are frozen at the first finish: no new terminal event, no new index
    # line, and the PERSISTED summary.json still says "completed".
    assert logger.events_path.read_text(encoding="utf-8").splitlines() == events_after_first
    assert index_path.read_text(encoding="utf-8").splitlines() == index_after_first
    assert (logger.run_dir / "summary.json").read_text(encoding="utf-8") == disk_after_first
    assert json.loads(disk_after_first)["status"] == "completed"
    # Exactly one run_finished terminal event (started + finished == 2 StateEvents total).
    assert [json.loads(l)["kind"] for l in events_after_first].count("StateEvent") == 2
    # And the inspector reads the durable disk truth, not the throwaway return value.
    assert insp.read_summary("twice")["status"] == "completed"


# --------------------------------------------------------------------------- #
# Property invariants over the inspect read path.                              #
# --------------------------------------------------------------------------- #


_PROP_RUN_SEQ = itertools.count()


@pytest.mark.audit
@pytest.mark.property
@given(
    kinds=st.lists(
        st.sampled_from(["Alpha", "Beta", "Gamma"]),
        min_size=0,
        max_size=30,
    )
)
def test_read_events_kind_filter_is_a_faithful_subsequence(kinds, tmp_path, monkeypatch):
    """For any emitted kind-sequence, filtering by K returns exactly the K-subsequence, in order."""
    # tmp_path is shared across hypothesis examples (function-scoped), so give each
    # example its OWN runs base via a monotonic counter — no cross-example log bleed,
    # robust even when hypothesis re-tries an identical input during shrinking.
    run_id = "prop-run"
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path / f"prop-{next(_PROP_RUN_SEQ)}"))
    logger = EventLogger(run_id)
    for i, k in enumerate(kinds):
        logger.emit(k, idx=i)

    all_events = insp.read_events(run_id)
    # The leading StateEvent (run_started) plus our emissions, order-preserved.
    emitted = [e for e in all_events if e["kind"] in {"Alpha", "Beta", "Gamma"}]
    assert [e["kind"] for e in emitted] == kinds

    for target in ("Alpha", "Beta", "Gamma"):
        filtered = insp.read_events(run_id, kind=target)
        assert [e["kind"] for e in filtered] == [k for k in kinds if k == target]
        # idx values stay monotonic within the filtered subsequence.
        idxs = [e["idx"] for e in filtered]
        assert idxs == sorted(idxs)


@pytest.mark.audit
@pytest.mark.property
@given(name=st.text(alphabet=st.characters(blacklist_characters="/\\", blacklist_categories=("Cs",)), min_size=1, max_size=20))
def test_single_segment_run_ids_round_trip(name, tmp_path, monkeypatch):
    """Any name without slash/backslash and not '..' survives ctor->disk->inspect."""
    # Exclude the exact traversal token and pure-whitespace/dot edge cases the OS rejects.
    if name == ".." or name == "." or name.strip() == "":
        return
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path / "rt"))
    try:
        logger = EventLogger(name)
    except (ValueError, OSError):
        # OSError: some unicode/control names are invalid filenames on the host FS.
        return
    logger.finish("completed")
    assert name in insp.list_runs()
    assert insp.read_summary(name)["run_id"] == name
