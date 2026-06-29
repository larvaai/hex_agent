"""test_decision_register.py — the Decision Register (DEC-<n>), ported PS
semantics + harness changes.

Append-only register at docs/decisions.md, written through the fs_guard
"docs" zone. Script owns the deterministic structure: monotonic id alloc
(max+1, never reused, corrupt-but-id-bearing blocks still count), grammar
validation, append-without-overwrite, list. Injection escape covers the
multiline rationale AND the single-line title/affects fields. BOTH append
paths (--append and --append-alloc) run inside the register lock so two
concurrent processes cannot overwrite each other's records.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import decision_register as dr  # noqa: E402
from decision_register import (  # noqa: E402
    DECISION_ID_RE, DecisionError, alloc_id, append_decision,
    list_active, parse_decisions,
)
import fs_guard  # noqa: E402 — exception class looked up live: other test
# files reload fs_guard (new class identity), so an import-time binding here
# would make pytest.raises order-dependent.


def _decisions_path(root: Path) -> Path:
    return root / "docs" / "decisions.md"


def _seed(root: Path, *records: str) -> Path:
    p = _decisions_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    header = "# Decision Register\n\n"
    p.write_text(header + "\n".join(records) + ("\n" if records else ""),
                 encoding="utf-8")
    return p


def _record(dec_id: str, status: str = "active", supersedes: str = "") -> str:
    sup = "supersedes: %s\n" % supersedes if supersedes else ""
    return (
        "---\n"
        "id: %s\n"
        "status: %s\n"
        "date: 2026-06-01\n"
        "%s"
        "---\n"
        "## %s — sample ruling\n\n"
        "Rationale prose here.\n" % (dec_id, status, sup, dec_id)
    )


# ---------- alloc_id ----------

class TestAllocId:
    def test_first(self, tmp_path):
        assert alloc_id(tmp_path) == "DEC-1"
        _seed(tmp_path)
        assert alloc_id(tmp_path) == "DEC-1"

    def test_increments(self, tmp_path):
        _seed(tmp_path, _record("DEC-1"), _record("DEC-2"))
        assert alloc_id(tmp_path) == "DEC-3"

    def test_superseded_still_counts(self, tmp_path):
        _seed(tmp_path, _record("DEC-1", status="active"),
              _record("DEC-2", status="superseded", supersedes="DEC-1"))
        assert alloc_id(tmp_path) == "DEC-3"

    def test_gap_uses_max_plus_one(self, tmp_path):
        _seed(tmp_path, _record("DEC-1"), _record("DEC-5"))
        assert alloc_id(tmp_path) == "DEC-6"

    def test_corrupt_but_id_bearing_block_reserves_its_number(self, tmp_path):
        corrupt = (
            "---\n"
            "id: DEC-5\n"
            "status: active\n"
            "affects: [unterminated\n"
            "---\n"
            "## DEC-5 — corrupt block\n\nRationale.\n"
        )
        _seed(tmp_path, _record("DEC-1"), corrupt)
        assert sorted(r["id"] for r in parse_decisions(tmp_path)) == ["DEC-1"]
        assert alloc_id(tmp_path) == "DEC-6"


# ---------- append_decision ----------

class TestAppend:
    def test_validates_grammar(self, tmp_path):
        _seed(tmp_path)
        with pytest.raises(DecisionError):
            append_decision(tmp_path, dec_id="DEC-abc", title="bad", rationale="x")
        with pytest.raises(DecisionError):
            append_decision(tmp_path, dec_id="DECISION-1", title="bad", rationale="x")

    def test_append_only_prior_records_survive(self, tmp_path):
        _seed(tmp_path, _record("DEC-1"))
        before = _decisions_path(tmp_path).read_text(encoding="utf-8")
        out = append_decision(
            tmp_path, dec_id="DEC-2", title="actor format",
            rationale="user:<u>/agent:<a> — attribution, not authentication",
        )
        after = out.read_text(encoding="utf-8")
        assert before.rstrip() in after
        recs = parse_decisions(tmp_path)
        assert [r["id"] for r in recs] == ["DEC-1", "DEC-2"]
        assert recs[1]["status"] == "active"

    def test_rejects_duplicate_id(self, tmp_path):
        _seed(tmp_path, _record("DEC-1"))
        with pytest.raises(DecisionError):
            append_decision(tmp_path, dec_id="DEC-1", title="dup", rationale="x")

    def test_supersede_records_link_and_flips_old(self, tmp_path):
        _seed(tmp_path, _record("DEC-1"))
        append_decision(tmp_path, dec_id="DEC-2", title="switch", rationale="y",
                        supersedes="DEC-1")
        dr._supersede_in_place(tmp_path, "DEC-1")
        by_id = {r["id"]: r for r in parse_decisions(tmp_path)}
        assert by_id["DEC-2"]["supersedes"] == "DEC-1"
        assert by_id["DEC-1"]["status"] == "superseded"

    def test_supersede_preserves_blank_line_before_heading(self, tmp_path):
        append_decision(tmp_path, dec_id="DEC-1", title="first", rationale="z")
        text_before = _decisions_path(tmp_path).read_text(encoding="utf-8")
        assert "---\n\n## DEC-1" in text_before
        assert dr._supersede_in_place(tmp_path, "DEC-1")
        text = _decisions_path(tmp_path).read_text(encoding="utf-8")
        assert "status: superseded" in text
        assert "---\n\n## DEC-1" in text
        assert "---\n## DEC-1" not in text

    def test_supersede_without_status_line_reports_no_flip(self, tmp_path):
        # A hand-edited record missing its `status:` line cannot be flipped;
        # the function must say so (False), not report success while the old
        # ruling silently stays active.
        _seed(tmp_path, (
            "---\n"
            "id: DEC-1\n"
            "date: 2026-06-01\n"
            "---\n"
            "## DEC-1 — sample ruling\n\n"
            "Rationale prose here.\n"
        ))
        assert dr._supersede_in_place(tmp_path, "DEC-1") is False

    def test_invalid_append_with_supersedes_leaves_register_untouched(self, tmp_path, monkeypatch):
        seeded = _seed(tmp_path, _record("DEC-1"))
        before = seeded.read_text(encoding="utf-8")
        argv = ["decision_register.py", "--root", str(tmp_path), "--append",
                "--id", "DEC-2", "--title", "second", "--supersedes", "DEC-1"]
        monkeypatch.setattr(sys, "argv", argv)
        rc = dr.main()
        assert rc == 0  # bad input → JSON finding, not crash
        assert seeded.read_text(encoding="utf-8") == before
        assert sorted(r["id"] for r in list_active(tmp_path)) == ["DEC-1"]

    def test_append_cli_refuses_unflippable_supersede_untouched(self, tmp_path, monkeypatch):
        # The --append CLI path delegates to the SAME locked critical section as
        # --append-alloc, so its supersede-feasibility gate must also refuse a
        # target with no status: line BEFORE writing — never appending a second
        # active ruling. (Companion to test_append_alloc_surfaces_failed_supersede,
        # which exercises the library entry; this pins the CLI/explicit-id path.)
        seeded = _seed(tmp_path, (
            "---\n"
            "id: DEC-1\n"
            "date: 2026-06-01\n"
            "---\n"
            "## DEC-1 — sample ruling\n\nRationale prose here.\n"
        ))
        before = seeded.read_text(encoding="utf-8")
        argv = ["decision_register.py", "--root", str(tmp_path), "--append",
                "--id", "DEC-2", "--title", "switch", "--rationale", "y",
                "--supersedes", "DEC-1"]
        monkeypatch.setattr(sys, "argv", argv)
        rc = dr.main()
        assert rc == 0  # refusal surfaces as a JSON finding, not a crash
        assert seeded.read_text(encoding="utf-8") == before  # byte-untouched
        assert [r["id"] for r in list_active(tmp_path)] == ["DEC-1"]  # no DEC-2

    def test_record_carries_actor_and_ts(self, tmp_path, monkeypatch):
        # Every register record is machine-written state: it must carry an
        # actor (via resolve_actor) and a timestamp, like the other stores.
        monkeypatch.setenv("HARNESS_USER", "decider@local")
        append_decision(tmp_path, dec_id="DEC-1", title="t", rationale="r")
        rec = parse_decisions(tmp_path)[0]
        assert rec["actor"].startswith("user:decider@local")
        assert rec["ts"]  # ts present and non-empty

    def test_append_alloc_surfaces_failed_supersede(self, tmp_path, monkeypatch):
        # If the in-place supersede fails (e.g. the target has no status:
        # line), append_alloc must NOT leave two active rulings silently —
        # it surfaces an error rather than reporting a clean write.
        _seed(tmp_path, (
            "---\n"
            "id: DEC-1\n"
            "date: 2026-06-01\n"
            "---\n"
            "## DEC-1 — sample ruling\n\nRationale prose here.\n"
        ))
        with pytest.raises(DecisionError):
            dr.append_alloc(tmp_path, title="switch", rationale="y",
                            supersedes="DEC-1")
        # No second active ruling left behind by the failed supersede.
        assert sorted(r["id"] for r in list_active(tmp_path)) == ["DEC-1"]

    def test_dangling_supersedes_rejected(self, tmp_path):
        _seed(tmp_path)
        with pytest.raises(DecisionError):
            append_decision(tmp_path, dec_id="DEC-1", title="t", rationale="r",
                            supersedes="DEC-9")

    def test_write_lands_under_docs(self, tmp_path):
        out = append_decision(tmp_path, dec_id="DEC-1", title="first", rationale="z")
        assert out.is_relative_to(tmp_path / "docs")

    def test_fence_blocks_escape(self, tmp_path, monkeypatch):
        escape = tmp_path / "outside" / "decisions.md"
        monkeypatch.setattr(dr, "_decisions_path", lambda root: escape)
        with pytest.raises(fs_guard.FenceError):
            append_decision(tmp_path, dec_id="DEC-1", title="first", rationale="z")
        assert not escape.exists()


# ---------- injection (rationale + title + affects) ----------

class TestInjection:
    def test_rationale_fence_and_heading_escaped(self, tmp_path):
        evil = "para\n---\nid: DEC-99\n---\n## DEC-99 — fake\nmore"
        append_decision(tmp_path, dec_id="DEC-1", title="t", rationale=evil)
        recs = parse_decisions(tmp_path)
        assert [r["id"] for r in recs] == ["DEC-1"]  # no phantom DEC-99
        text = _decisions_path(tmp_path).read_text(encoding="utf-8")
        assert "\\---" in text and "\\## DEC-99" in text

    @pytest.mark.parametrize("sep,label", [
        ("\u2028", "line-separator"),
        ("\u0085", "NEL"),
        ("\x0b", "vertical-tab"),
        ("\x0c", "form-feed"),
    ])
    def test_unicode_separators_cannot_smuggle_records(self, tmp_path, sep, label):
        # These separators survive sanitize_field (it collapses only \r\n)
        # AND never create a line anchor for re MULTILINE (only \n does) —
        # that symmetry is what keeps them harmless. Pin it: a refactor of
        # either side (e.g. switching to a regex that treats them as
        # newlines) must not silently open a smuggling channel.
        evil_affects = "PRD-X%sstatus: superseded%sid: DEC-99" % (sep, sep)
        evil_rationale = "why%s---%s## DEC-88 — fake" % (sep, sep)
        append_decision(tmp_path, dec_id="DEC-1", title="t",
                        rationale=evil_rationale, affects=evil_affects)
        recs = parse_decisions(tmp_path)
        assert [r["id"] for r in recs] == ["DEC-1"]
        assert recs[0]["status"] == "active"  # no smuggled status override

    def test_title_newline_cannot_smuggle_record(self, tmp_path):
        evil_title = "ok\n---\nid: DEC-77\n---\n## DEC-77 — fake"
        append_decision(tmp_path, dec_id="DEC-1", title=evil_title, rationale="r")
        recs = parse_decisions(tmp_path)
        assert [r["id"] for r in recs] == ["DEC-1"]
        # heading stays one line: the whole title is inert on the DEC-1 line
        text = _decisions_path(tmp_path).read_text(encoding="utf-8")
        heading = [l for l in text.splitlines() if l.startswith("## DEC-1")]
        assert len(heading) == 1 and "DEC-77" in heading[0]

    def test_affects_newline_cannot_break_frontmatter(self, tmp_path):
        evil_affects = "PRD-X\nstatus: superseded"
        append_decision(tmp_path, dec_id="DEC-1", title="t", rationale="r",
                        affects=evil_affects)
        recs = parse_decisions(tmp_path)
        assert recs[0]["status"] == "active"  # injected status line did not win
        assert "PRD-X" in recs[0]["affects"]


# ---------- list_active ----------

class TestListActive:
    def test_only_active(self, tmp_path):
        _seed(tmp_path,
              _record("DEC-1", status="active"),
              _record("DEC-2", status="superseded", supersedes="DEC-1"),
              _record("DEC-3", status="active"))
        assert sorted(r["id"] for r in list_active(tmp_path)) == ["DEC-1", "DEC-3"]

    def test_empty_register(self, tmp_path):
        assert list_active(tmp_path) == []
        _seed(tmp_path)
        assert list_active(tmp_path) == []


def test_decision_id_regex():
    assert DECISION_ID_RE.match("DEC-1")
    assert DECISION_ID_RE.match("DEC-42")
    for bad in ("DEC-", "DEC-1a", "dec-1", "DECISION-1"):
        assert not DECISION_ID_RE.match(bad)


# ---------- concurrency (both append paths hold the register lock) ----------

def _cli(root, *args):
    return [sys.executable, str(_SCRIPTS / "decision_register.py"),
            "--root", str(root)] + list(args)


class TestConcurrency:
    def test_parallel_append_alloc_yields_distinct_monotonic_ids(self, tmp_path):
        procs = [subprocess.Popen(
            _cli(tmp_path, "--append-alloc", "--title", "t%d" % i,
                 "--rationale", "r%d" % i),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ) for i in range(6)]
        outs = [p.communicate() for p in procs]
        assert all(p.returncode == 0 for p in procs), outs
        ids = [r["id"] for r in parse_decisions(tmp_path)]
        assert sorted(ids) == ["DEC-%d" % n for n in range(1, 7)]
        assert len(set(ids)) == 6  # no collision, no lost record

    def test_explicit_append_waits_for_register_lock(self, tmp_path):
        # Hold the register lock from the test process; a concurrent --append
        # must WAIT (proving the explicit-id path is inside the critical
        # section too), then complete once released.
        fcntl = pytest.importorskip("fcntl")
        lock_path = dr._lock_path(tmp_path)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(lock_path, "w")
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        proc = subprocess.Popen(
            _cli(tmp_path, "--append", "--id", "DEC-1", "--title", "t",
                 "--rationale", "r"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(0.5)
        assert proc.poll() is None, "append finished while lock was held"
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()
        out, err = proc.communicate(timeout=10)
        assert proc.returncode == 0, err
        assert json.loads(out)["written"] is True
        assert [r["id"] for r in parse_decisions(tmp_path)] == ["DEC-1"]


def test_rationale_bare_optional_line_preserved(tmp_path):
    # The empty-optional strip must touch only the generated frontmatter, never the
    # caller's rationale body: a rationale line that is literally `affects:` /
    # `supersedes:` (a decision discussing those fields) must survive verbatim.
    append_decision(tmp_path, dec_id="DEC-1", title="meta",
                    rationale="intro line\naffects:\nsupersedes:\nconclusion",
                    affects="", supersedes="")
    body = (tmp_path / "docs" / "decisions.md").read_text(encoding="utf-8")
    assert "\naffects:\n" in body
    assert "\nsupersedes:\n" in body
