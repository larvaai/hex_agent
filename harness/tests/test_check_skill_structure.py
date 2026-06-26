"""test_check_skill_structure.py — structural lint for hs:* skills.

check_skill_structure is an advisory analyzer over a skill directory. It enforces
the thin-core discipline documented for the harness: a SKILL.md stays small and its
references/ stay bounded, so detail lives one level deep instead of bloating the
always-loaded core.

Contract mirrored from check_report_language: advisory by default (exit 0, never
mutates); with --strict a HARD finding exits non-zero. Description-shape problems are
advisory only — they flag but never block.
"""
import json
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import check_skill_structure as css  # noqa: E402


def _make_skill(root, name="hs:demo", desc="Do a demo thing. Use when you need a demo.",
                body_lines=10, refs=None, body=None):
    d = root / name.replace("hs:", "")
    d.mkdir(parents=True, exist_ok=True)
    fm = (
        "---\nname: %s\ndescription: %s\nuser-invocable: true\n"
        "metadata:\n  owner: harness\n  compliance-tier: workflow\n---\n" % (name, desc)
    )
    body_text = body if body is not None else "\n".join("body line %d" % i for i in range(body_lines))
    (d / "SKILL.md").write_text(fm + "# Title\n" + body_text + "\n", encoding="utf-8")
    if refs:
        rd = d / "references"
        rd.mkdir(exist_ok=True)
        for rname, rlines in refs.items():
            (rd / rname).write_text(
                "\n".join("ref line %d" % i for i in range(rlines)) + "\n", encoding="utf-8")
    return d


def _rules(result):
    return {f["rule"] for f in result["findings"]}


def _severity(result, rule):
    return next(f["severity"] for f in result["findings"] if f["rule"] == rule)


# --- well-formed skill --------------------------------------------------------

def test_wellformed_skill_passes(tmp_path):
    d = _make_skill(tmp_path)
    res = css.check_skill(str(d))
    assert res["verdict"] == "PASS"
    assert res["findings"] == []


# --- hard: line-count gates ---------------------------------------------------

def test_oversized_skill_md_is_hard(tmp_path):
    d = _make_skill(tmp_path, body_lines=200)
    res = css.check_skill(str(d))
    assert "skill-md-too-long" in _rules(res)
    assert _severity(res, "skill-md-too-long") == "hard"
    assert res["verdict"] == "FAIL"


def test_frontmatter_lines_excluded_from_size_limit(tmp_path):
    # The size gate governs GUIDANCE (body), not metadata. A large frontmatter plus a
    # body under the limit must NOT trip skill-md-too-long — otherwise the schema
    # frontmatter rollout would spuriously break near-limit skills.
    d = tmp_path / "demo"
    d.mkdir()
    fm = (
        "---\nname: hs:demo\ndescription: Do a thing. Use when needed.\n"
        "category: core\nlicense: AGPL-3.0\nkeywords: [a, b, c]\n"
        'when_to_use: "Use when needed."\nargument-hint: "<x>"\n'
        "user-invocable: true\nmetadata:\n  owner: harness\n  compliance-tier: workflow\n---\n"
    )
    body = "# Title\n" + "\n".join("body line %d" % i for i in range(145))  # 146 body lines
    (d / "SKILL.md").write_text(fm + body + "\n", encoding="utf-8")
    # total file is ~160 lines (> 150) but the body is under 150
    res = css.check_skill(str(d))
    assert "skill-md-too-long" not in _rules(res)


def test_oversized_reference_is_hard(tmp_path):
    d = _make_skill(tmp_path, refs={"big.md": 400})
    res = css.check_skill(str(d))
    assert "reference-too-long" in _rules(res)
    assert _severity(res, "reference-too-long") == "hard"


# --- advisory: description shape ----------------------------------------------

def test_description_without_trigger_is_advisory(tmp_path):
    d = _make_skill(tmp_path, desc="Does a thing with no trigger clause.")
    res = css.check_skill(str(d))
    assert "description-missing-trigger" in _rules(res)
    assert _severity(res, "description-missing-trigger") == "advisory"
    # advisory-only findings never fail the skill
    assert res["verdict"] == "PASS_WITH_RISK"


def test_short_description_is_advisory(tmp_path):
    d = _make_skill(tmp_path, desc="Too short")
    res = css.check_skill(str(d))
    assert "description-length" in _rules(res)
    assert _severity(res, "description-length") == "advisory"


# --- hard: dangling local reference -------------------------------------------

def test_dangling_ref_is_hard(tmp_path):
    d = _make_skill(tmp_path, body="See references/nope.md for the detail.")
    res = css.check_skill(str(d))
    assert "broken-reference-link" in _rules(res)
    assert _severity(res, "broken-reference-link") == "hard"
    assert res["verdict"] == "FAIL"


def test_existing_local_ref_not_flagged(tmp_path):
    # The body links a reference that DOES exist on disk => no dangling, no orphan.
    d = _make_skill(tmp_path, body="Detail lives in references/detail.md here.",
                    refs={"detail.md": 20})
    res = css.check_skill(str(d))
    assert "broken-reference-link" not in _rules(res)
    assert "orphan-reference" not in _rules(res)


def test_absolute_path_prose_not_flagged(tmp_path):
    # An absolute-path mention is preceded by `/`, which the negative-lookbehind skips.
    d = _make_skill(
        tmp_path,
        body="Detail lives in harness/plugins/hs/skills/demo/references/x.md (absolute).")
    res = css.check_skill(str(d))
    assert "broken-reference-link" not in _rules(res)


# --- hard: birth-marker leak (tightened) --------------------------------------

def test_birth_marker_in_body_is_hard(tmp_path):
    d = _make_skill(tmp_path, body="generated_on: 2026-06-17 by the drafting pipeline.")
    res = css.check_skill(str(d))
    assert "birth-marker-leak" in _rules(res)
    assert _severity(res, "birth-marker-leak") == "hard"
    assert res["verdict"] == "FAIL"


def test_birth_marker_in_frontmatter_not_flagged(tmp_path):
    # The same marker inside frontmatter metadata is NOT a prose leak.
    d = tmp_path / "fmdemo"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: hs:fmdemo\ndescription: A demo skill. Use when demoing things.\n"
        "generated_on: 2026-06-17\n---\n# Title\nclean prose body\n",
        encoding="utf-8")
    res = css.check_skill(str(d))
    assert "birth-marker-leak" not in _rules(res)


def test_evidence_heading_not_birth_marker(tmp_path):
    d = _make_skill(tmp_path, body="## Evidence\n\nfile.py:42 proves the claim.")
    res = css.check_skill(str(d))
    assert "birth-marker-leak" not in _rules(res)


def test_doc_prose_not_birth_marker(tmp_path):
    # Belief-store documentation prose must NOT read as a machine provenance leak —
    # else the phases that document the belief store self-trip the gate this builds.
    d = _make_skill(
        tmp_path,
        body="The belief was reinforced from 3 episodes and the success rate held at 0.9.")
    res = css.check_skill(str(d))
    assert "birth-marker-leak" not in _rules(res)
    assert all(f["severity"] != "hard" for f in res["findings"])


# --- advisory: orphan reference -----------------------------------------------

def test_orphan_ref_advisory_not_hard(tmp_path):
    d = _make_skill(tmp_path, body="No links in this body.", refs={"unused.md": 5})
    res = css.check_skill(str(d))
    assert "orphan-reference" in _rules(res)
    assert _severity(res, "orphan-reference") == "advisory"
    assert res["verdict"] != "FAIL"  # advisory-only never fails


# --- write-gate decision (the skill_quality_gate hook brain) -------------------

def test_write_gate_blocks_on_dangling_ref(tmp_path):
    d = _make_skill(tmp_path, body="See references/nope.md.")
    reason = css.write_gate_reason(str(d / "SKILL.md"))
    assert reason is not None
    assert str(d / "SKILL.md") in reason  # actionable: names the path
    assert "broken-reference-link" in reason


def test_write_gate_failopen_on_shape_only(tmp_path):
    # A description-shape-only problem is advisory => the gate allows it (None).
    d = _make_skill(tmp_path, desc="Too short", body="clean body")
    assert css.write_gate_reason(str(d / "SKILL.md")) is None


def test_write_gate_inert_on_non_skill_md(tmp_path):
    other = tmp_path / "notes.md"
    other.write_text("references/nope.md\n", encoding="utf-8")
    assert css.write_gate_reason(str(other)) is None


# --- CLI contract -------------------------------------------------------------

def _run(args):
    return subprocess.run(
        [sys.executable, str(_SCRIPTS / "check_skill_structure.py"), *args],
        capture_output=True, text=True,
    )


def test_cli_advisory_exits_zero_even_with_hard(tmp_path):
    # Without --strict the lint is advisory: a hard finding is reported, never blocks.
    d = _make_skill(tmp_path, body_lines=200)
    r = _run([str(d)])
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["tool"] == "check_skill_structure"


def test_cli_strict_blocks_hard(tmp_path):
    d = _make_skill(tmp_path, body_lines=200)
    r = _run([str(d), "--strict"])
    assert r.returncode == 1


def test_cli_strict_clean_passes(tmp_path):
    d = _make_skill(tmp_path)
    r = _run([str(d), "--strict"])
    assert r.returncode == 0


def test_cli_missing_skill_is_inert(tmp_path):
    # A path with no SKILL.md never hard-fails the caller.
    r = _run([str(tmp_path / "nope"), "--strict"])
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out.get("skipped")


# --- hard: dangling ref is case-blind on the file part ------------------------

def test_dangling_ref_case_insensitive_on_file_part(tmp_path):
    # A reader clicking references/Detail.md gets the same 404 as references/detail.md,
    # so the broken-reference-link rule must catch a capitalized name or an uppercase
    # extension too — a case-sensitive lint silently passes a dead link.
    cap = _make_skill(tmp_path / "a", body="See references/Detail.md for the detail.")
    assert "broken-reference-link" in _rules(css.check_skill(str(cap)))
    ext = _make_skill(tmp_path / "b", body="See references/detail.MD for the detail.")
    assert "broken-reference-link" in _rules(css.check_skill(str(ext)))
    # and the write-time gate must block it, not just the lint
    assert css.write_gate_reason(cap / "SKILL.md") is not None


def test_existing_uppercase_ref_not_flagged(tmp_path):
    # The mirror: a capitalized ref that DOES resolve on disk is neither a dangling
    # link NOR an orphan. The orphan assertion makes this discriminate pre/post-fix:
    # pre-fix the old regex never matched `Detail.md`, so the on-disk file was an
    # unlinked orphan; post-fix the link is recognized, so the ref is fully clean.
    d = _make_skill(tmp_path, body="Detail lives in references/Detail.md here.",
                    refs={"Detail.md": 5})
    rules = _rules(css.check_skill(str(d)))
    assert "broken-reference-link" not in rules
    assert "orphan-reference" not in rules
