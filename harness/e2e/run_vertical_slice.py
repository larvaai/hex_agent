#!/usr/bin/env python3
"""run_vertical_slice.py — end-to-end acceptance: block-then-pass in a temp dir.

Proves the vertical slice end to end the way Claude Code would drive it:
hooks are invoked as SUBPROCESSES with real stdin JSON (simulated transport —
no import cheating), against a COPY of fixture-mini in a temp dir with
HARNESS_ROOT pointing there, so nothing touches the real repo's plans/ or
manifest.

Scenario:
  1. session_init runs → session file + trace with actor.
  2. `git push` with a plan but NO artifacts → gate_stage BLOCKS (exit 2).
  3. Write verification.json → gate PASSES (exit 0).
  4. Disable the gate via config → gate SKIPS with a traced reason.
  5. git-pre-push-hook.sh smoke: blocks without artifacts, passes with.
  6. Every gate decision in the trace carries an actor.

Appends a run summary to harness/e2e/RUN-LOG.md (gitignored).

Usage: python3 harness/e2e/run_vertical_slice.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_E2E = Path(__file__).resolve().parent
_HARNESS = _E2E.parent
_REPO = _HARNESS.parent
_FIXTURE = _E2E / "fixture-mini"

_PASSED = []
_FAILED = []


def _check(name: str, ok: bool, detail: str = "") -> None:
    (_PASSED if ok else _FAILED).append((name, detail))
    print("  %s %s%s" % ("✓" if ok else "✗", name,
                         (" — " + detail) if (detail and not ok) else ""))


def _env(root: Path) -> dict:
    env = dict(os.environ)
    env.pop("PYTEST_CURRENT_TEST", None)
    env.pop("HARNESS_TELEMETRY_DISABLED", None)
    env.pop("HARNESS_HOOK_CONFIG", None)
    env.pop("HARNESS_ACTIVE_PLAN", None)
    env.pop("HARNESS_STAGE_POLICY", None)
    for ci in ("CI", "GITLAB_CI", "GITHUB_ACTIONS"):
        env.pop(ci, None)
    env["HARNESS_ROOT"] = str(root)
    env["HARNESS_STATE_DIR"] = str(root / "harness" / "state")
    env["HARNESS_HOOK_LOG_DIR"] = str(root / "harness" / "state" / "logs")
    env["HARNESS_USER"] = "e2e-runner"
    return env


def _hook(root: Path, script: Path, payload: dict, extra_env=None):
    env = _env(root)
    for k, v in (extra_env or {}).items():
        env[k] = v
    return subprocess.run([sys.executable, str(script)],
                          input=json.dumps(payload), capture_output=True,
                          text=True, env=env)


def _trace_events(root: Path):
    out = []
    trace = root / "harness" / "state" / "trace"
    if trace.is_dir():
        for f in sorted(trace.glob("trace-*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                out.append(json.loads(line))
    return out


def seed_git_repo(root: Path, email: str, name: str) -> None:
    """Init a fixture repo and make the seed commit WITHOUT writing identity
    into .git/config. Identity is passed per-command via `git -c user.x=...`,
    so the commit is attributed but the local config is never touched. The
    AFK sandbox bind-mounts the host repo's .git read-write — a `git config
    user.*` here would silently rewrite the human's committer identity on their
    own machine. Per-command config is the hermetic alternative."""
    subprocess.run(["git", "init", "-q"], cwd=str(root), check=True,
                   capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True,
                   capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=%s" % email, "-c", "user.name=%s" % name,
         "commit", "-qm", "seed fixture"],
        cwd=str(root), check=True, capture_output=True)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="harness-e2e-"))
    print("e2e vertical slice in %s (simulated transport: stdin JSON "
          "subprocess, not native Claude Code)" % tmp)
    try:
        root = tmp / "proj"
        shutil.copytree(_FIXTURE, root)
        # The slice under test is the REAL harness code, copied so the run
        # cannot write into the repo tree.
        shutil.copytree(_HARNESS / "hooks", root / "harness" / "hooks")
        shutil.copytree(_HARNESS / "scripts", root / "harness" / "scripts")
        shutil.copytree(_HARNESS / "data", root / "harness" / "data")
        shutil.copytree(_HARNESS / "install", root / "harness" / "install")
        # The fixture must be a real git repo: the pre-push hook resolves its
        # root via `git rev-parse --show-toplevel` after scrubbing HARNESS_*
        # (transport posture), so a bare copytree dir cannot host it. Identity
        # is set per-command (no .git/config write) — see seed_git_repo.
        seed_git_repo(root, "e2e@local", "e2e")

        gate = root / "harness" / "hooks" / "gate_stage.py"
        session_init = root / "harness" / "hooks" / "session_init.py"
        push_payload = {"session_id": "e2e-s1", "tool_name": "Bash",
                        "tool_input": {"command": "git push"}}

        # 1. session attribution
        proc = _hook(root, session_init, {"session_id": "e2e-s1"})
        _check("session_init continues", proc.returncode == 0, proc.stderr)
        sess = root / "harness" / "state" / "sessions" / "e2e-s1.json"
        _check("session file written with actor",
               sess.is_file() and "e2e-runner" in sess.read_text(encoding="utf-8"))

        # 2. plan exists but artifacts missing → BLOCK
        plan = root / "plans" / "260612-0900-fixture-feature"
        plan.mkdir(parents=True)
        (plan / "plan.md").write_text(
            "---\ntitle: fixture feature\nstatus: in_progress\n---\n",
            encoding="utf-8")
        proc = _hook(root, gate, push_payload)
        _check("push without artifact BLOCKS exit 2", proc.returncode == 2,
               "rc=%s stderr=%s" % (proc.returncode, proc.stderr[:200]))
        _check("block reason names the missing artifact",
               "verification" in proc.stderr, proc.stderr[:200])

        # 3. add artifacts → PASS
        art = plan / "artifacts"
        art.mkdir()
        (art / "verification.json").write_text(json.dumps({
            "stage": "push", "plan": plan.name, "actor": "user:e2e-runner",
            "ts": datetime.now(timezone.utc).isoformat(),
            "checks": [{"name": "pytest", "status": "PASS"}],
            "verdict": "PASS",
        }), encoding="utf-8")
        proc = _hook(root, gate, push_payload)
        _check("push with artifact PASSES exit 0", proc.returncode == 0,
               proc.stderr[:200])

        # 4. disabled gate → skip with traced reason
        cfg = root / "disabled-hooks.yaml"
        cfg.write_text("hooks:\n  gate_stage:\n    enabled: false\n",
                       encoding="utf-8")
        proc = _hook(root, gate, push_payload,
                     extra_env={"HARNESS_HOOK_CONFIG": str(cfg)})
        _check("disabled gate skips exit 0", proc.returncode == 0)

        # 5. pre-push transport hook smoke (artifact present → pass)
        prepush = root / "harness" / "install" / "git-pre-push-hook.sh"
        proc = subprocess.run(["sh", str(prepush)], capture_output=True,
                              text=True, env=_env(root), cwd=str(root))
        _check("pre-push hook passes with artifact", proc.returncode == 0,
               proc.stderr[:200])
        (art / "verification.json").unlink()
        proc = subprocess.run(["sh", str(prepush)], capture_output=True,
                              text=True, env=_env(root), cwd=str(root))
        _check("pre-push hook blocks without artifact", proc.returncode != 0)

        # 6. audit trail: decisions carry actor
        events = _trace_events(root)
        gate_events = [e for e in events if e["event"].startswith("gate_")]
        _check("trace has gate events", bool(gate_events))
        _check("every gate event carries an actor",
               all(e.get("actor") for e in gate_events))
        _check("both block and pass were traced",
               {"gate_block", "gate_pass"} <=
               {e["event"] for e in gate_events})
        _check("skip was traced with reason",
               any(e["event"] == "gate_skip" and e.get("note")
                   for e in events))

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    ok = not _FAILED
    summary = "%s | %d passed, %d failed | transport=simulated-stdin" % (
        datetime.now(timezone.utc).isoformat(), len(_PASSED), len(_FAILED))
    print("\ne2e:", summary)
    try:
        with open(_E2E / "RUN-LOG.md", "a", encoding="utf-8") as fh:
            fh.write("- %s\n" % summary)
            for name, detail in _FAILED:
                fh.write("  - FAILED: %s — %s\n" % (name, detail))
    except OSError:
        pass
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
