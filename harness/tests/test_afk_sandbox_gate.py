"""test_afk_sandbox_gate.py — the sandbox image carries the guardrail.

Three claims about the ``ralph-sandbox-harness`` image, all proven by actually
running the container (no mocks):

  - it carries python3 + PyYAML (the in-loop gate's only hard dependency — a
    missing dep wedges every Bash call fail-closed inside the loop);
  - ``HARNESS_ROOT`` resolves to the bind-mount path, so the hooks registered
    as ``python3 $HARNESS_ROOT/harness/hooks/*.py`` find the harness on the
    workspace mount;
  - the stage gate is LIVE inside the container — a ``git push`` with no
    verification artifact is blocked with exit 2 (reused gate-live probe).

Docker-gated: a host without a docker daemon skips cleanly rather than
faking green. Where docker IS present the image must exist — until it is
built these fail (the intended red), and pass once built (green).
"""
import subprocess
import sys
from pathlib import Path

import pytest

_AFK = Path(__file__).resolve().parent.parent / "afk"
if str(_AFK) not in sys.path:
    sys.path.insert(0, str(_AFK))

import gate_live_probe  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
IMAGE = "ralph-sandbox-harness"

requires_docker = pytest.mark.skipif(
    not gate_live_probe.docker_available(),
    reason="docker daemon not available — sandbox proof runs where docker is",
)


@requires_docker
def test_image_has_python_yaml():
    # PyYAML is the gate's only non-stdlib dependency; absent it the
    # compliance hooks fail-closed on every command inside the loop.
    proc = subprocess.run(
        ["docker", "run", "--rm", IMAGE, "python3", "-c", "import yaml"],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr


@requires_docker
def test_harness_root_resolves():
    # The hooks are registered as `python3 $HARNESS_ROOT/harness/hooks/*.py`;
    # the image bakes HARNESS_ROOT so Ralph's fixed argv needs no --settings.
    proc = subprocess.run(
        ["docker", "run", "--rm", IMAGE, "sh", "-c", "echo $HARNESS_ROOT"],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "/home/agent/workspace"


@requires_docker
def test_gate_blocks_push_in_container():
    # The whole thesis: the in-loop guardrail is live inside the sandbox.
    result = gate_live_probe.probe(IMAGE, _REPO_ROOT)
    assert result.fired, (
        "gate did not block git push inside the image (exit=%r): %s"
        % (result.exit_code, result.detail))
    assert result.exit_code == 2
