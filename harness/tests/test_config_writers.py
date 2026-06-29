"""test_config_writers.py — narrow write CLIs for the two gate-adjacent configs
that were read-only until now: team.yaml (roster + claims) and output.yaml
(generated-prose language). /hs:setup drives these.

team.yaml is gate config: the writer accepts reviewers + lease_s, but REFUSES
allow_self_review — flipping solo-mode on is a posture decision that must be a
deliberate, git-visible hand edit, not a one-liner the setup flow can do for you
(the plan-approval role check is the backstop). An explicit --file keeps the
no-ambient-env-override property: only a visible argument can redirect the write,
never an environment variable.
"""
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import output_config as oc  # noqa: E402
import team_config as tc  # noqa: E402

_SEED_TEAM = (
    "# team.yaml — roster + claims (hand note kept across writes)\n"
    "reviewers: []\n"
    "allow_self_review: false\n"
    "claims:\n"
    "  lease_s: 14400\n"
)
_SEED_OUTPUT = "# output.yaml\nlanguage: vi\nhumanize: true\n"


def _seed(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


# --- team_config.save_team (library) ------------------------------------------

def test_save_team_writes_reviewers_prefix_normalized(tmp_path):
    p = _seed(tmp_path, "team.yaml", _SEED_TEAM)
    tc.save_team({"reviewers": ["a@x.com", "user:b@y.com"]}, path=p)
    loaded = tc.load_team(path=p)
    assert loaded["reviewers"] == ["user:a@x.com", "user:b@y.com"]


def test_save_team_writes_lease_s(tmp_path):
    p = _seed(tmp_path, "team.yaml", _SEED_TEAM)
    tc.save_team({"lease_s": 3600}, path=p)
    assert tc.load_team(path=p)["claims"]["lease_s"] == 3600


def test_save_team_preserves_allow_self_review_and_header(tmp_path):
    p = _seed(tmp_path, "team.yaml",
              _SEED_TEAM.replace("allow_self_review: false",
                                 "allow_self_review: true"))
    tc.save_team({"lease_s": 7200}, path=p)
    text = p.read_text(encoding="utf-8")
    assert "hand note kept across writes" in text   # header preserved
    assert tc.load_team(path=p)["allow_self_review"] is True  # untouched


def test_save_team_refuses_allow_self_review(tmp_path):
    p = _seed(tmp_path, "team.yaml", _SEED_TEAM)
    before = p.read_text(encoding="utf-8")
    try:
        tc.save_team({"allow_self_review": True}, path=p)
        raised = False
    except tc.TeamConfigError:
        raised = True
    assert raised
    assert p.read_text(encoding="utf-8") == before  # nothing written


def test_save_team_rejects_reviewer_with_quote_or_newline(tmp_path):
    # a reviewer value containing a quote/newline must not be hand-interpolated
    # into the YAML (it would corrupt team.yaml and silently disable the gate).
    p = _seed(tmp_path, "team.yaml", _SEED_TEAM)
    before = p.read_text(encoding="utf-8")
    for bad in ['user:a"x@e.com', "user:a\ninjected: true"]:
        try:
            tc.save_team({"reviewers": [bad]}, path=p)
            raised = False
        except tc.TeamConfigError:
            raised = True
        assert raised, repr(bad)
    assert p.read_text(encoding="utf-8") == before  # nothing written


def test_save_team_output_round_trips_through_loader(tmp_path):
    # whatever save_team writes MUST parse back cleanly (no corruption)
    p = _seed(tmp_path, "team.yaml", _SEED_TEAM)
    tc.save_team({"reviewers": ["user:a@x.com", "user:b@y.com"], "lease_s": 900}, path=p)
    loaded = tc.load_team(path=p)  # raises TeamConfigError if corrupt
    assert loaded["reviewers"] == ["user:a@x.com", "user:b@y.com"]
    assert loaded["claims"]["lease_s"] == 900


def test_save_team_rejects_bad_lease(tmp_path):
    p = _seed(tmp_path, "team.yaml", _SEED_TEAM)
    before = p.read_text(encoding="utf-8")
    for bad in (0, -5, "soon"):
        try:
            tc.save_team({"lease_s": bad}, path=p)
            raised = False
        except tc.TeamConfigError:
            raised = True
        assert raised, bad
    assert p.read_text(encoding="utf-8") == before


# --- team_config CLI ----------------------------------------------------------

def _run_team(*args):
    return subprocess.run([sys.executable, str(_SCRIPTS / "team_config.py"), *args],
                          capture_output=True, text=True)


def test_cli_team_set_reviewers(tmp_path):
    p = _seed(tmp_path, "team.yaml", _SEED_TEAM)
    r = _run_team("--file", str(p), "--set", "reviewers=a@x.com,b@y.com")
    assert r.returncode == 0, r.stderr
    assert tc.load_team(path=p)["reviewers"] == ["user:a@x.com", "user:b@y.com"]


def test_cli_team_set_allow_self_review_refused(tmp_path):
    p = _seed(tmp_path, "team.yaml", _SEED_TEAM)
    r = _run_team("--file", str(p), "--set", "allow_self_review=true")
    assert r.returncode != 0
    assert "allow_self_review" in (r.stderr + r.stdout)


def test_cli_team_unknown_key_refused(tmp_path):
    p = _seed(tmp_path, "team.yaml", _SEED_TEAM)
    r = _run_team("--file", str(p), "--set", "bogus=1")
    assert r.returncode != 0


# --- output_config.save_output + CLI ------------------------------------------

def test_save_output_writes_language_and_humanize(tmp_path):
    p = _seed(tmp_path, "output.yaml", _SEED_OUTPUT)
    oc.save_output({"language": "en", "humanize": False}, path=p)
    loaded = oc.load_output(path=p)
    assert loaded["language"] == "en"
    assert loaded["humanize"] is False


def test_save_output_rejects_bad_language(tmp_path):
    p = _seed(tmp_path, "output.yaml", _SEED_OUTPUT)
    before = p.read_text(encoding="utf-8")
    try:
        oc.save_output({"language": "fr"}, path=p)
        raised = False
    except oc.OutputConfigError:
        raised = True
    assert raised
    assert p.read_text(encoding="utf-8") == before


def _run_output(*args):
    return subprocess.run([sys.executable, str(_SCRIPTS / "output_config.py"), *args],
                          capture_output=True, text=True)


def test_cli_output_set_language(tmp_path):
    p = _seed(tmp_path, "output.yaml", _SEED_OUTPUT)
    r = _run_output("--file", str(p), "--set", "language=en")
    assert r.returncode == 0, r.stderr
    assert oc.load_output(path=p)["language"] == "en"
