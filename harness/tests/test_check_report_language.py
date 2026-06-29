"""test_check_report_language.py — advisory language + AI-tell checker.

check_report_language is an OPTIONAL advisory analyzer. It reads a generated
report, compares its detected language against the configured output language
(harness/data/output.yaml), and scans for the AI-writing tells and Vietnamese
translation tells named in harness/rules/humanizer-and-anti-ai-tells.md.

It is advisory by contract: it ALWAYS exits 0 and never rewrites the report.
Findings carry a location so a writer can fix the source; evidence is never
mutated. The checker only ever returns PASS or PASS_WITH_RISK — it does not
block.
"""
import json
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import check_report_language as crl  # noqa: E402

_VI = "Hệ thống này dùng lại trạng thái cũ và kiểm tra ngay tại chỗ số liệu mới nhất."
_EN = "The loader reads the config once and stops loudly when the file is missing."


# --- language detection -------------------------------------------------------

def test_detect_language_vietnamese():
    assert crl.detect_language(_VI) == "vi"


def test_detect_language_english():
    assert crl.detect_language(_EN) == "en"


def test_detect_language_empty_defaults_to_en():
    # No diacritics → treat as en (the safe default; no false vi alarm).
    assert crl.detect_language("") == "en"


# --- clean report -------------------------------------------------------------

def test_clean_english_report_passes(tmp_path):
    p = tmp_path / "r.md"
    p.write_text("# Result\n\n" + _EN + "\n", encoding="utf-8")
    res = crl.check_report(str(p), expected="en")
    assert res["verdict"] == "PASS"
    assert res["language_match"] is True
    assert res["findings"] == []


# --- language mismatch --------------------------------------------------------

def test_language_mismatch_flagged(tmp_path):
    p = tmp_path / "r.md"
    p.write_text(_EN + "\n", encoding="utf-8")
    res = crl.check_report(str(p), expected="vi")
    assert res["language_match"] is False
    assert res["language_expected"] == "vi"
    assert res["language_detected"] == "en"
    assert res["verdict"] == "PASS_WITH_RISK"


# --- AI tells -----------------------------------------------------------------

def test_ai_vocab_and_dash_flagged(tmp_path):
    p = tmp_path / "r.md"
    p.write_text(
        "We leverage the cache to delve into the data — a testament to scale.\n",
        encoding="utf-8",
    )
    res = crl.check_report(str(p), expected="en")
    kinds = {f["kind"] for f in res["findings"]}
    terms = {f["term"] for f in res["findings"]}
    assert "ai-vocab" in kinds
    assert "dash" in kinds
    assert "leverage" in terms and "delve" in terms
    assert res["verdict"] == "PASS_WITH_RISK"
    # findings carry a line number so the writer can locate the source
    assert all("line" in f for f in res["findings"])


def test_code_fence_is_not_scanned(tmp_path):
    # A banned word inside a fenced code block is a citation, not a tell.
    p = tmp_path / "r.md"
    p.write_text(
        "Clean prose here.\n\n```python\nx = leverage(delve)\n```\n",
        encoding="utf-8",
    )
    res = crl.check_report(str(p), expected="en")
    assert res["findings"] == []
    assert res["verdict"] == "PASS"


# --- Vietnamese translation tells ---------------------------------------------

def test_vietnamese_calque_flagged_when_expected_vi(tmp_path):
    p = tmp_path / "r.md"
    # "tận dụng" + "một cách" are calque tells from the humanizer VN table.
    p.write_text("Chúng ta tận dụng bộ nhớ đệm một cách rõ ràng.\n", encoding="utf-8")
    res = crl.check_report(str(p), expected="vi")
    kinds = {f["kind"] for f in res["findings"]}
    assert "vi-tell" in kinds
    assert res["verdict"] == "PASS_WITH_RISK"


def test_vietnamese_calque_not_scanned_when_expected_en(tmp_path):
    # When the configured output is English, the VN-tell table does not apply.
    p = tmp_path / "r.md"
    p.write_text("Chúng ta tận dụng một cách rõ ràng.\n", encoding="utf-8")
    res = crl.check_report(str(p), expected="en")
    assert all(f["kind"] != "vi-tell" for f in res["findings"])


# --- CLI contract: advisory, always exit 0 ------------------------------------

def _run(args):
    return subprocess.run(
        [sys.executable, str(_SCRIPTS / "check_report_language.py"), *args],
        capture_output=True, text=True,
    )


def test_cli_exits_zero_and_emits_json(tmp_path):
    p = tmp_path / "r.md"
    p.write_text("We leverage the cache.\n", encoding="utf-8")
    r = _run([str(p), "--expected", "en"])
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["verdict"] in ("PASS", "PASS_WITH_RISK")
    assert out["tool"] == "check_report_language"


def test_cli_missing_file_is_inert(tmp_path):
    # Advisory: a missing input never hard-fails the caller.
    r = _run([str(tmp_path / "nope.md"), "--expected", "en"])
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["verdict"] == "PASS"
    assert out.get("skipped")


# --- diff-based severity (--base-ref) -----------------------------------------
# Only a LANGUAGE MISMATCH on a file CHANGED vs the base ref blocks. Tells
# (dash / AI vocab / VN calque) are advisory: they are reported but never block,
# so an internal report is not held to the cosmetic anti-AI bar. An
# unchanged/legacy file stays a warning, and an unresolvable base ref degrades to
# warn-only so a shallow checkout never fails spuriously.

def _tells_report(tmp_path):
    p = tmp_path / "r.md"
    p.write_text("We leverage the cache to delve in.\n", encoding="utf-8")
    return p


def test_base_ref_changed_language_mismatch_blocks(tmp_path, monkeypatch):
    # English report, expected vi → a real defect on a changed file → blocks.
    p = _tells_report(tmp_path)
    monkeypatch.setattr(crl, "_resolve_base_ref", lambda ref, cwd=None: "main", raising=False)
    monkeypatch.setattr(crl, "_changed_vs_base", lambda path, base, cwd=None: True, raising=False)
    res = crl.check_report(str(p), expected="vi", base_ref="__auto__")
    assert res["enforced"] is True
    assert res["changed"] is True
    assert res["language_match"] is False
    assert res["blocking"] is True
    assert res["verdict"] == "BLOCKED"


def test_base_ref_changed_tells_only_warns(tmp_path, monkeypatch):
    # Changed file with tells but the CORRECT language: tells are advisory, so it
    # warns and never blocks. Only a language mismatch blocks.
    p = _tells_report(tmp_path)
    monkeypatch.setattr(crl, "_resolve_base_ref", lambda ref, cwd=None: "main", raising=False)
    monkeypatch.setattr(crl, "_changed_vs_base", lambda path, base, cwd=None: True, raising=False)
    res = crl.check_report(str(p), expected="en", base_ref="__auto__")
    assert res["changed"] is True
    assert res["language_match"] is True
    assert res["findings"]            # tells are still reported
    assert res["blocking"] is False
    assert res["verdict"] == "PASS_WITH_RISK"


def test_base_ref_unchanged_is_warn_only(tmp_path, monkeypatch):
    p = _tells_report(tmp_path)
    monkeypatch.setattr(crl, "_resolve_base_ref", lambda ref, cwd=None: "main", raising=False)
    monkeypatch.setattr(crl, "_changed_vs_base", lambda path, base, cwd=None: False, raising=False)
    res = crl.check_report(str(p), expected="en", base_ref="__auto__")
    assert res["changed"] is False
    assert res["blocking"] is False
    assert res["verdict"] == "PASS_WITH_RISK"


def test_base_ref_unavailable_degrades_to_warn(tmp_path, monkeypatch):
    # Base ref cannot be resolved (shallow checkout / missing history) → warn-only.
    p = _tells_report(tmp_path)
    monkeypatch.setattr(crl, "_resolve_base_ref", lambda ref, cwd=None: None, raising=False)
    res = crl.check_report(str(p), expected="en", base_ref="__auto__")
    assert res["changed"] is None
    assert res["blocking"] is False
    assert res["verdict"] == "PASS_WITH_RISK"


def test_base_ref_changed_but_clean_not_blocked(tmp_path, monkeypatch):
    p = tmp_path / "r.md"
    p.write_text("# Result\n\n" + _EN + "\n", encoding="utf-8")
    monkeypatch.setattr(crl, "_resolve_base_ref", lambda ref, cwd=None: "main", raising=False)
    monkeypatch.setattr(crl, "_changed_vs_base", lambda path, base, cwd=None: True, raising=False)
    res = crl.check_report(str(p), expected="en", base_ref="__auto__")
    assert res["blocking"] is False
    assert res["verdict"] == "PASS"


def test_no_base_ref_preserves_advisory_contract(tmp_path):
    # Without --base-ref the dict is unchanged: no enforce keys, never blocks.
    p = _tells_report(tmp_path)
    res = crl.check_report(str(p), expected="en")
    assert res["verdict"] == "PASS_WITH_RISK"
    assert "enforced" not in res
    assert "blocking" not in res


# --- diff-based severity: real-git integration --------------------------------

def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)


def _init_repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "base.md").write_text("clean base\n", encoding="utf-8")
    _git(tmp_path, "add", "base.md")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "branch", "-M", "main")


def test_cli_base_ref_blocks_new_changed_file(tmp_path):
    _init_repo(tmp_path)
    # A brand-new (untracked) report in the WRONG language = changed vs base AND a
    # language mismatch → must block. (Tells alone would not block.)
    rpt = tmp_path / "report.md"
    rpt.write_text("We leverage the cache to delve in.\n", encoding="utf-8")
    r = _run([str(rpt), "--expected", "vi", "--base-ref"])
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert out["verdict"] == "BLOCKED"
    assert out["changed"] is True
    assert out["base_ref"] == "main"


def test_cli_base_ref_unchanged_committed_file_warns(tmp_path):
    _init_repo(tmp_path)
    # A file WITH tells, committed and unchanged vs base → warn-only, exit 0.
    leg = tmp_path / "legacy.md"
    leg.write_text("We leverage the cache.\n", encoding="utf-8")
    _git(tmp_path, "add", "legacy.md")
    _git(tmp_path, "commit", "-q", "-m", "legacy")
    r = _run([str(leg), "--expected", "en", "--base-ref", "main"])
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["changed"] is False
    assert out["verdict"] == "PASS_WITH_RISK"


# --- language detected from prose, not fenced code ----------------------------

def test_language_detected_from_prose_not_code_fence(tmp_path):
    # A vi report dominated by an English code fence must still detect as vi — the
    # fence is evidence (never translated), not the report's language. Detecting on
    # the WHOLE text dilutes the diacritic ratio and falsely flags en; under
    # --base-ref that would BLOCK a legitimate vi report. The tells pass already
    # excludes fences; detection must too.
    code = "\n".join("def compute_function_%d(): return process_the_value(x)" % i
                     for i in range(60))
    p = tmp_path / "r.md"
    p.write_text("# Báo cáo\n\n" + _VI + "\n\n```python\n" + code + "\n```\n",
                 encoding="utf-8")
    res = crl.check_report(str(p), expected="vi")
    assert res["language_detected"] == "vi"
    assert res["language_match"] is True
