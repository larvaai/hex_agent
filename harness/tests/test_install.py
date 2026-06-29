"""test_install.py — packaged installer: materialize hooks, merge, copy, verify.

The installer turns the source harness tree into an installed-and-wired copy in
a target repo: it copies the tracked harness/ tree, materializes
hooks-registration.yaml into the target's .claude/settings.json (Claude Code
shape, $HARNESS_ROOT -> "$CLAUDE_PROJECT_DIR"), installs the pre-push transport
gate, writes the reviewer roster into the TARGET (never the source), and ends in
a verify_install-clean state. Every mutation is idempotent and dry-run-able; an
uninstall reverses the settings and pre-push edits.

These cover: command substitution, materialization shape + event allow-list,
additive merge (preserves user hooks, dedup, idempotent), roster normalization,
and end-to-end install/dry-run/uninstall into a temp git repo that ends
verify-clean.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INSTALL_DIR = _REPO_ROOT / "harness" / "install"
_SCRIPTS = _REPO_ROOT / "harness" / "scripts"
for _p in (str(_INSTALL_DIR), str(_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import install as installer  # noqa: E402


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo)] + list(args),
                          capture_output=True, text=True, check=True)


@pytest.fixture()
def target_repo(tmp_path):
    """An empty git repo to install INTO."""
    repo = tmp_path / "target"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    return repo


# --- pure helpers --------------------------------------------------------


class TestPathContainment:
    """A bundle's manifest is the authoritative file list when the source has no
    .git (the `sh install.sh <tarball> <repo>` path). The bundle is user-supplied
    and its sibling .sha256 only proves transit-integrity, not authorship — so a
    crafted entry that climbs out of harness/ must be refused, never copied
    outside the install target."""

    def test_rel_escapes_predicate(self):
        assert installer._rel_escapes("harness/../../tmp/evil")
        assert installer._rel_escapes("/etc/passwd")
        assert installer._rel_escapes("harness/../secret")
        assert not installer._rel_escapes("harness/hooks/session_init.py")
        assert not installer._rel_escapes("harness/manifest.json")

    def test_copy_tree_refuses_manifest_path_escaping_target(self, tmp_path):
        source = tmp_path / "src"
        (source / "harness").mkdir(parents=True)
        (source / "harness" / "manifest.json").write_text(
            json.dumps({"files": {"harness/../../evil.txt": "x"}}),
            encoding="utf-8")
        target = tmp_path / "target"
        target.mkdir()
        escaped = (target / ".." / "evil.txt").resolve()
        with pytest.raises(installer.InstallError):
            installer._copy_tree(source, target, dry_run=False)
        assert not escaped.exists()  # nothing written outside the target


class TestCommandSubstitution:
    def test_harness_root_becomes_project_dir(self):
        raw = "python3 $HARNESS_ROOT/harness/hooks/session_init.py"
        assert installer.to_command(raw) == (
            'python3 "$CLAUDE_PROJECT_DIR"/harness/hooks/session_init.py')

    def test_non_harness_text_is_preserved(self):
        assert installer.to_command("echo hi") == "echo hi"


class TestMaterializeHooks:
    def test_claude_code_shape_and_grouping(self):
        reg = {"hooks": [
            {"event": "SessionStart",
             "command": "python3 $HARNESS_ROOT/harness/hooks/session_init.py"},
            {"event": "PreToolUse", "matcher": "Bash",
             "command": "python3 $HARNESS_ROOT/harness/hooks/gate_stage.py"},
            {"event": "PreToolUse", "matcher": "Bash",
             "command": "python3 $HARNESS_ROOT/harness/hooks/mark_bash_start.py"},
        ]}
        hooks, skipped = installer.materialize_hooks(reg)
        # SessionStart: no matcher key, one command, substituted
        ss = hooks["SessionStart"]
        assert ss == [{"hooks": [{"type": "command",
                                  "command": 'python3 "$CLAUDE_PROJECT_DIR"'
                                  '/harness/hooks/session_init.py'}]}]
        # Two Bash entries collapse into ONE matcher group with two commands
        pre = hooks["PreToolUse"]
        assert len(pre) == 1
        assert pre[0]["matcher"] == "Bash"
        assert [h["command"] for h in pre[0]["hooks"]] == [
            'python3 "$CLAUDE_PROJECT_DIR"/harness/hooks/gate_stage.py',
            'python3 "$CLAUDE_PROJECT_DIR"/harness/hooks/mark_bash_start.py']
        assert skipped == []

    def test_unknown_event_is_skipped_and_reported(self):
        reg = {"hooks": [
            {"event": "TotallyFakeEvent",
             "command": "python3 $HARNESS_ROOT/harness/hooks/track_skill_invocation.py"},
            {"event": "Stop",
             "command": "python3 $HARNESS_ROOT/harness/hooks/emit_session_summary.py"},
        ]}
        hooks, skipped = installer.materialize_hooks(reg)
        assert "TotallyFakeEvent" not in hooks
        assert "Stop" in hooks
        assert any(ev == "TotallyFakeEvent" for ev, _cmd in skipped)

    def test_userpromptexpansion_is_materialized(self):
        # UserPromptExpansion is a live Claude Code event (verified via capture:
        # it fires on slash_command expansion carrying command_name) — it must be
        # wired, not skipped, so user-typed /hs:* invocations get captured.
        reg = {"hooks": [
            {"event": "UserPromptExpansion",
             "command": "python3 $HARNESS_ROOT/harness/hooks/track_skill_invocation.py"},
        ]}
        hooks, skipped = installer.materialize_hooks(reg)
        assert "UserPromptExpansion" in hooks
        assert not any(ev == "UserPromptExpansion" for ev, _cmd in skipped)


class TestMergeHooks:
    def _harness_new(self):
        return {"PreToolUse": [
            {"matcher": "Bash", "hooks": [
                {"type": "command",
                 "command": 'python3 "$CLAUDE_PROJECT_DIR"/harness/hooks/gate_stage.py'}]}]}

    def test_preserves_pre_existing_user_hook(self):
        existing = {"PreToolUse": [
            {"matcher": "Bash", "hooks": [
                {"type": "command", "command": "echo user-hook"}]}]}
        merged = installer.merge_hooks(existing, self._harness_new())
        cmds = [h["command"] for h in merged["PreToolUse"][0]["hooks"]]
        assert "echo user-hook" in cmds
        assert 'python3 "$CLAUDE_PROJECT_DIR"/harness/hooks/gate_stage.py' in cmds

    def test_merge_is_idempotent(self):
        new = self._harness_new()
        once = installer.merge_hooks({}, new)
        twice = installer.merge_hooks(once, new)
        assert once == twice
        assert len(twice["PreToolUse"][0]["hooks"]) == 1

    def test_strip_removes_only_harness_hooks(self):
        existing = {"PreToolUse": [
            {"matcher": "Bash", "hooks": [
                {"type": "command", "command": "echo user-hook"},
                {"type": "command",
                 "command": 'python3 "$CLAUDE_PROJECT_DIR"/harness/hooks/gate_stage.py'}]}]}
        stripped = installer.strip_harness_hooks(existing)
        cmds = [h["command"] for h in stripped["PreToolUse"][0]["hooks"]]
        assert cmds == ["echo user-hook"]

    def test_strip_keeps_user_hook_that_merely_mentions_the_dir(self):
        # a user hook whose command CONTAINS the substring 'harness/hooks/' but
        # does not INVOKE a harness hook .py (e.g. an audit grep) must survive
        # uninstall — substring matching would delete it (data loss).
        existing = {"PreToolUse": [
            {"matcher": "Bash", "hooks": [
                {"type": "command", "command": "grep -r harness/hooks/ . || true"},
                {"type": "command",
                 "command": 'python3 "$CLAUDE_PROJECT_DIR"/harness/hooks/gate_stage.py'}]}]}
        stripped = installer.strip_harness_hooks(existing)
        cmds = [h["command"] for h in stripped["PreToolUse"][0]["hooks"]]
        assert cmds == ["grep -r harness/hooks/ . || true"]

    def test_strip_prunes_emptied_event(self):
        existing = {"Stop": [
            {"hooks": [
                {"type": "command",
                 "command": 'python3 "$CLAUDE_PROJECT_DIR"/harness/hooks/emit_session_summary.py'}]}]}
        assert installer.strip_harness_hooks(existing) == {}


class TestRosterNormalize:
    def test_bare_email_gets_user_prefix(self):
        assert installer.normalize_reviewers(["a@x.com", "user:b@y.com", " "]) == [
            "user:a@x.com", "user:b@y.com"]


# --- end to end into a temp repo ----------------------------------------


class TestInstallEndToEnd:
    def test_install_wires_settings_copies_tree_and_verifies(self, target_repo):
        res = installer.install(_REPO_ROOT, target_repo)
        assert res["ok"], res["problems"]
        # tree copied
        assert (target_repo / "harness" / "hooks" / "session_init.py").is_file()
        assert (target_repo / "harness" / "manifest.json").is_file()
        # settings wired with substituted command
        settings = json.loads(
            (target_repo / ".claude" / "settings.json").read_text())
        cmds = [h["command"]
                for groups in settings["hooks"].values()
                for g in groups for h in g["hooks"]]
        assert any('"$CLAUDE_PROJECT_DIR"/harness/hooks/session_init.py' in c
                   for c in cmds)
        assert all("$HARNESS_ROOT" not in c for c in cmds)
        # pre-push installed + executable
        pp = target_repo / ".git" / "hooks" / "pre-push"
        assert pp.is_file()
        import os
        assert os.access(pp, os.X_OK)
        # final verify clean (manifest matches the copied tree)
        assert res["problems"] == []

    def test_existing_foreign_prepush_is_backed_up(self, target_repo):
        hooks_dir = target_repo / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        (hooks_dir / "pre-push").write_text("#!/bin/sh\necho mine\n")
        installer.install(_REPO_ROOT, target_repo)
        assert (hooks_dir / "pre-push.bak").read_text() == "#!/bin/sh\necho mine\n"
        # the active hook is now the harness one
        assert "pre-push" in (hooks_dir / "pre-push").read_text()

    def test_rerun_is_idempotent(self, target_repo):
        installer.install(_REPO_ROOT, target_repo)
        settings_path = target_repo / ".claude" / "settings.json"
        first = settings_path.read_text()
        installer.install(_REPO_ROOT, target_repo)
        assert settings_path.read_text() == first

    def test_merge_preserves_user_authored_settings(self, target_repo):
        claude = target_repo / ".claude"
        claude.mkdir(parents=True)
        (claude / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [
                {"type": "command", "command": "echo user-hook"}]}]}}))
        installer.install(_REPO_ROOT, target_repo)
        settings = json.loads((claude / "settings.json").read_text())
        assert "echo user-hook" in json.dumps(settings["hooks"])

    def test_userpromptexpansion_wired_in_real_install(self, target_repo):
        # The real registration declares UserPromptExpansion → track_skill_invocation;
        # the install must materialize it into settings.json (not skip it).
        installer.install(_REPO_ROOT, target_repo)
        settings = json.loads(
            (target_repo / ".claude" / "settings.json").read_text())
        assert "UserPromptExpansion" in settings["hooks"]
        cmds = [h["command"]
                for g in settings["hooks"]["UserPromptExpansion"]
                for h in g["hooks"]]
        assert any("track_skill_invocation.py" in c for c in cmds)

    def test_dry_run_writes_nothing(self, target_repo):
        res = installer.install(_REPO_ROOT, target_repo, dry_run=True)
        assert res["ok"]
        assert not (target_repo / ".claude").exists()
        assert not (target_repo / "harness").exists()
        assert res["actions"]  # it still PLANNED actions

    def test_roster_written_to_target_not_source(self, target_repo):
        # strict=True so a regression where the roster write trips the final
        # verify (team.yaml diverges from its shipped manifest hash) fails here.
        src_team_path = _REPO_ROOT / "harness" / "data" / "team.yaml"
        src_before = src_team_path.read_text()
        res = installer.install(_REPO_ROOT, target_repo,
                                reviewers=["a@x.com", "b@y.com"], strict=True)
        assert res["ok"], res["problems"]
        # the file the installer localized must NOT count as hard drift
        assert all(rel != "harness/data/team.yaml" for rel, _ in res["problems"])
        team = (target_repo / "harness" / "data" / "team.yaml").read_text()
        assert 'reviewers: ["user:a@x.com", "user:b@y.com"]' in team
        # source roster file untouched by the localize-to-target write. Value-
        # agnostic: this dev repo's tracked team.yaml may run solo-mode; the
        # invariant guarded is "installer never mutates source", not a literal
        # empty default.
        assert src_team_path.read_text() == src_before

    def test_source_equals_target_is_noop_copy(self, tmp_path):
        # Pointing source at target must not attempt to copy/clobber the source.
        res = installer.install(_REPO_ROOT, _REPO_ROOT, dry_run=True)
        assert res["source_is_target"] is True
        assert not any("copy" in a.lower() and "tree" in a.lower()
                       and "skip" not in a.lower() for a in res["actions"])

    def test_uninstall_reverses_settings_and_prepush(self, target_repo):
        # seed a user hook so we can prove uninstall keeps it
        installer.install(_REPO_ROOT, target_repo)
        settings_path = target_repo / ".claude" / "settings.json"
        s = json.loads(settings_path.read_text())
        s["hooks"].setdefault("PreToolUse", []).insert(0, {
            "matcher": "Bash", "hooks": [
                {"type": "command", "command": "echo user-hook"}]})
        settings_path.write_text(json.dumps(s))
        installer.install(_REPO_ROOT, target_repo, uninstall=True)
        after = json.dumps(json.loads(settings_path.read_text()))
        assert "harness/hooks/" not in after
        assert "echo user-hook" in after
        # pre-push removed (no backup existed)
        assert not (target_repo / ".git" / "hooks" / "pre-push").exists()


class TestClaudeMdOnboarding:
    """The installer injects a self-loading onboarding block into the target's
    CLAUDE.md so a fresh agent session knows the harness is present and how to
    drive it. Replace-BETWEEN-markers (not skip-if-present) so a version bump
    refreshes the block instead of leaving a stale one; prose OUTSIDE the markers
    is always preserved; re-running never duplicates."""

    def _result(self):
        return {"actions": [], "warnings": [], "problems": [], "ok": True}

    def test_creates_claude_md_when_absent(self, tmp_path):
        installer._write_claude_md(tmp_path, self._result(), dry_run=False)
        text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert installer._CLAUDE_BEGIN in text and installer._CLAUDE_END in text
        assert "/hs:" in text            # how to invoke the skills
        assert "harness/rules" in text   # pointer to the rule layer

    def test_preserves_user_prose_when_appending(self, tmp_path):
        p = tmp_path / "CLAUDE.md"
        p.write_text("# My Project\n\nHand-written guidance.\n", encoding="utf-8")
        installer._write_claude_md(tmp_path, self._result(), dry_run=False)
        text = p.read_text(encoding="utf-8")
        assert "# My Project" in text
        assert "Hand-written guidance." in text
        assert installer._CLAUDE_BEGIN in text

    def test_replace_between_markers_drops_stale_keeps_outside(self, tmp_path):
        p = tmp_path / "CLAUDE.md"
        p.write_text("intro line\n\n%s\nSTALE OLD BLOCK\n%s\n\noutro line\n"
                     % (installer._CLAUDE_BEGIN, installer._CLAUDE_END),
                     encoding="utf-8")
        installer._write_claude_md(tmp_path, self._result(), dry_run=False)
        text = p.read_text(encoding="utf-8")
        assert "STALE OLD BLOCK" not in text              # block refreshed
        assert "intro line" in text and "outro line" in text  # prose preserved
        assert text.count(installer._CLAUDE_BEGIN) == 1
        assert "/hs:" in text

    def test_idempotent_block_appears_once(self, tmp_path):
        r = self._result()
        installer._write_claude_md(tmp_path, r, dry_run=False)
        installer._write_claude_md(tmp_path, r, dry_run=False)
        text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert text.count(installer._CLAUDE_BEGIN) == 1
        assert text.count(installer._CLAUDE_END) == 1

    def test_dry_run_writes_nothing(self, tmp_path):
        installer._write_claude_md(tmp_path, self._result(), dry_run=True)
        assert not (tmp_path / "CLAUDE.md").exists()

    def test_reversed_markers_do_not_corrupt(self, tmp_path):
        # a hand-mangled file with END before BEGIN must not garble — fall back
        # to a clean append, preserving the user's prose.
        p = tmp_path / "CLAUDE.md"
        p.write_text("prose A\n%s\nprose B\n%s\nprose C\n"
                     % (installer._CLAUDE_END, installer._CLAUDE_BEGIN),
                     encoding="utf-8")
        installer._write_claude_md(tmp_path, self._result(), dry_run=False)
        text = p.read_text(encoding="utf-8")
        assert "prose A" in text and "prose B" in text and "prose C" in text
        assert "/hs:" in text  # a valid block was written
        # the appended block is well-formed: a BEGIN that precedes its END exists
        assert text.rindex(installer._CLAUDE_BEGIN) < text.rindex(installer._CLAUDE_END)

    def test_install_injects_block_into_target(self, target_repo):
        installer.install(_REPO_ROOT, target_repo)
        text = (target_repo / "CLAUDE.md").read_text(encoding="utf-8")
        assert installer._CLAUDE_BEGIN in text

    def test_dogfood_install_does_not_touch_source_claude_md(self):
        # source == target: our hand-authored CLAUDE.md must not get a block.
        res = installer.install(_REPO_ROOT, _REPO_ROOT, dry_run=True)
        assert not any("CLAUDE.md" in a for a in res["actions"])


class TestNoTrack:
    """--no-track installs a RUNNING harness that the adopter's git ignores
    (harness/ added to .gitignore). Because the roster's whole safety model is
    'tamper-visible via git diff', a no-track install refuses to localize the
    roster and says why — the gate needs harness/ tracked to mean anything."""

    def _gitignore_lines(self, repo):
        p = repo / ".gitignore"
        return p.read_text(encoding="utf-8").splitlines() if p.is_file() else []

    def test_no_track_gitignores_harness_tree(self, target_repo):
        installer.install(_REPO_ROOT, target_repo, no_track=True)
        assert "harness/" in self._gitignore_lines(target_repo)
        # ...but the tree is really installed and runnable
        assert (target_repo / "harness" / "hooks" / "session_init.py").is_file()

    def test_default_install_does_not_gitignore_harness_tree(self, target_repo):
        installer.install(_REPO_ROOT, target_repo)
        assert "harness/" not in self._gitignore_lines(target_repo)

    def test_no_track_refuses_roster_with_warning(self, target_repo):
        res = installer.install(_REPO_ROOT, target_repo, no_track=True,
                                reviewers=["a@x.com", "b@y.com"])
        assert not any("write roster" in a for a in res["actions"])
        assert any("no-track" in w.lower() or "track" in w.lower()
                   for w in res["warnings"])

    def test_no_track_is_idempotent(self, target_repo):
        installer.install(_REPO_ROOT, target_repo, no_track=True)
        installer.install(_REPO_ROOT, target_repo, no_track=True)
        assert self._gitignore_lines(target_repo).count("harness/") == 1

    def test_cli_no_track_flag_parses(self, target_repo):
        proc = subprocess.run(
            [sys.executable, str(_INSTALL_DIR / "install.py"),
             "--target", str(target_repo), "--no-track", "--non-interactive"],
            capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        assert "harness/" in self._gitignore_lines(target_repo)


class TestCli:
    def test_cli_dry_run_exit_zero(self, target_repo):
        proc = subprocess.run(
            [sys.executable, str(_INSTALL_DIR / "install.py"),
             "--target", str(target_repo), "--dry-run"],
            capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        assert not (target_repo / ".claude").exists()


class TestRobustness:
    """A team adopting the harness may already have a hand-edited
    .claude/settings.json. A JSON syntax error in it must surface as a clean,
    actionable message naming the file — never a raw JSONDecodeError traceback."""

    def _seed_bad_settings(self, target_repo, text="{ broken json, }"):
        claude = target_repo / ".claude"
        claude.mkdir(parents=True, exist_ok=True)
        (claude / "settings.json").write_text(text)

    def test_malformed_settings_raises_clean_error_on_install(self, target_repo):
        self._seed_bad_settings(target_repo)
        with pytest.raises(installer.InstallError) as ei:
            installer.install(_REPO_ROOT, target_repo)
        assert "settings.json" in str(ei.value)

    def test_malformed_settings_raises_clean_error_on_uninstall(self, target_repo):
        self._seed_bad_settings(target_repo, "{ nope ")
        with pytest.raises(installer.InstallError):
            installer.install(_REPO_ROOT, target_repo, uninstall=True)

    def test_cli_malformed_settings_exits_nonzero_naming_file(self, target_repo):
        self._seed_bad_settings(target_repo, "{ bad ")
        proc = subprocess.run(
            [sys.executable, str(_INSTALL_DIR / "install.py"),
             "--target", str(target_repo)],
            capture_output=True, text=True)
        assert proc.returncode != 0
        assert "settings.json" in (proc.stderr + proc.stdout)
        # a clean message, not a Python traceback
        assert "Traceback" not in proc.stderr


class TestGitignoreFragment:
    """The installer adds a managed block so the target never commits harness
    runtime state. Idempotent and additive: a pre-existing .gitignore survives."""

    def test_writes_harness_ignore_block(self, target_repo):
        installer.install(_REPO_ROOT, target_repo)
        gi = (target_repo / ".gitignore").read_text()
        assert "harness/state/" in gi
        assert "harness/standards/.snapshots/" in gi
        assert "RUN-LOG.md" in gi

    def test_gitignore_is_idempotent(self, target_repo):
        installer.install(_REPO_ROOT, target_repo)
        first = (target_repo / ".gitignore").read_text()
        installer.install(_REPO_ROOT, target_repo)
        assert (target_repo / ".gitignore").read_text() == first

    def test_preserves_existing_gitignore(self, target_repo):
        (target_repo / ".gitignore").write_text("node_modules/\n")
        installer.install(_REPO_ROOT, target_repo)
        gi = (target_repo / ".gitignore").read_text()
        assert "node_modules/" in gi
        assert "harness/state/" in gi


class TestStandardsLengthWarning:
    """An over-length standards doc is advisory only: many skills load it, so a
    long file costs tokens and is easy to skim past — but the installer warns,
    never blocks. The threshold is tunable via HARNESS_STANDARDS_MAXLOC."""

    def test_overlength_standards_warns_not_blocks(self, tmp_path, monkeypatch):
        base = tmp_path / "harness" / "standards"
        base.mkdir(parents=True)
        (base / "system-architecture.md").write_text("line\n" * 50)
        (base / "code-standards.md").write_text("x" * 60 + "\n")  # not thin, short
        monkeypatch.setenv("HARNESS_STANDARDS_MAXLOC", "10")
        result = {"warnings": []}
        installer._check_standards(tmp_path, result)
        assert any("system-architecture.md" in w and "token" in w.lower()
                   for w in result["warnings"])
        assert not any("code-standards.md" in w for w in result["warnings"])

    def test_within_threshold_is_silent(self, tmp_path, monkeypatch):
        base = tmp_path / "harness" / "standards"
        base.mkdir(parents=True)
        (base / "system-architecture.md").write_text("x" * 60 + "\n")
        (base / "code-standards.md").write_text("y" * 60 + "\n")
        monkeypatch.setenv("HARNESS_STANDARDS_MAXLOC", "800")
        result = {"warnings": []}
        installer._check_standards(tmp_path, result)
        assert result["warnings"] == []


class TestInteractiveInstall:
    """On a TTY the installer suggests a reviewer (from git config) and prompts;
    --non-interactive / --yes force the non-prompt path even on a TTY (the CI
    case), and a non-TTY stays silent regardless."""

    def test_git_user_email_reads_config(self, monkeypatch, target_repo):
        monkeypatch.chdir(target_repo)  # fixture sets user.email = t@t
        assert installer._git_user_email() == "t@t"

    def test_prompt_uses_suggestion_on_blank(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *a: "")  # accept default
        assert installer._prompt_reviewers("me@x.com") == ["me@x.com"]

    def test_prompt_keeps_typed_over_suggestion(self, monkeypatch):
        answers = iter(["other@x.com", ""])
        monkeypatch.setattr("builtins.input", lambda *a: next(answers))
        assert installer._prompt_reviewers("me@x.com") == ["other@x.com"]

    def test_yes_skips_prompt_even_when_tty(self, monkeypatch, target_repo):
        monkeypatch.setattr(installer, "_stdin_is_tty", lambda: True)
        monkeypatch.setattr(
            "builtins.input",
            lambda *a: pytest.fail("must not prompt with --yes"))
        rc = installer.main(["--target", str(target_repo),
                             "--source", str(_REPO_ROOT), "--yes"])
        assert rc == 0

    def test_non_interactive_alias_skips_prompt(self, monkeypatch, target_repo):
        monkeypatch.setattr(installer, "_stdin_is_tty", lambda: True)
        monkeypatch.setattr(
            "builtins.input",
            lambda *a: pytest.fail("must not prompt with --non-interactive"))
        rc = installer.main(["--target", str(target_repo),
                             "--source", str(_REPO_ROOT), "--non-interactive"])
        assert rc == 0

    def test_tty_without_yes_prompts(self, monkeypatch, target_repo):
        monkeypatch.setattr(installer, "_stdin_is_tty", lambda: True)
        seen = []
        monkeypatch.setattr("builtins.input",
                            lambda *a: seen.append(a) or "")  # blank → finish
        rc = installer.main(["--target", str(target_repo),
                             "--source", str(_REPO_ROOT)])
        assert rc == 0
        assert seen  # the reviewer prompt was shown


class TestNonGitSource:
    """A shipped bundle extracts to a plain directory with no .git. The
    installer's file list must then come from manifest.json — `git ls-files`
    exits 128 outside a work tree and must not abort the install."""

    def _fake_source(self, tmp_path):
        src = tmp_path / "extracted"
        (src / "harness" / "data").mkdir(parents=True)
        (src / "harness" / "hooks").mkdir(parents=True)
        (src / "harness" / "hooks" / "a.py").write_text("x\n")
        (src / "harness" / "data" / "b.yaml").write_text("y\n")
        manifest = {"files": {
            "harness/hooks/a.py": "0" * 64,
            "harness/data/b.yaml": "1" * 64,
        }}
        (src / "harness" / "manifest.json").write_text(json.dumps(manifest))
        return src

    def test_tracked_files_fall_back_to_manifest(self, tmp_path):
        src = self._fake_source(tmp_path)
        rels = installer._tracked_harness_files(src)
        # manifest keys PLUS manifest.json itself (the target needs it to verify)
        assert sorted(rels) == [
            "harness/data/b.yaml", "harness/hooks/a.py", "harness/manifest.json"]

    def test_copy_tree_works_without_git(self, tmp_path):
        src = self._fake_source(tmp_path)
        target = tmp_path / "target"
        target.mkdir()
        installer._copy_tree(src, target, dry_run=False)
        assert (target / "harness" / "hooks" / "a.py").is_file()
        assert (target / "harness" / "data" / "b.yaml").is_file()


class TestGitRepoUntrackedHarness:
    """Source IS a git work tree, but harness/ was copied in without being
    committed — e.g. the bundle extracted into an existing repo, then install run
    from there (and the harness's own test suite re-installing from a freshly
    installed copy). `git ls-files -- harness/` then exits 0 with NO output; the
    file list must still come from manifest.json, not collapse to an empty
    install. The error-only fallback misses this because git did not error."""

    def _git_untracked_source(self, tmp_path):
        src = tmp_path / "repo"
        (src / "harness" / "data").mkdir(parents=True)
        (src / "harness" / "hooks").mkdir(parents=True)
        (src / "harness" / "hooks" / "a.py").write_text("x\n")
        (src / "harness" / "data" / "b.yaml").write_text("y\n")
        manifest = {"files": {
            "harness/hooks/a.py": "0" * 64,
            "harness/data/b.yaml": "1" * 64,
        }}
        (src / "harness" / "manifest.json").write_text(json.dumps(manifest))
        subprocess.run(["git", "-C", str(src), "init", "-q"], check=True)
        return src

    def test_tracked_files_fall_back_when_git_lists_nothing(self, tmp_path):
        src = self._git_untracked_source(tmp_path)
        rels = installer._tracked_harness_files(src)
        assert sorted(rels) == [
            "harness/data/b.yaml", "harness/hooks/a.py", "harness/manifest.json"]

    def test_copy_tree_populates_from_manifest_in_untracked_repo(self, tmp_path):
        src = self._git_untracked_source(tmp_path)
        target = tmp_path / "installed"
        target.mkdir()
        installer._copy_tree(src, target, dry_run=False)
        assert (target / "harness" / "hooks" / "a.py").is_file()
        assert (target / "harness" / "manifest.json").is_file()
