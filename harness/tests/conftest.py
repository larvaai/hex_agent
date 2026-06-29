"""Shared test scaffolding for the spec-graph / fence / memory-gap suites.

Plain helpers (NOT fixtures) so call semantics stay identical to the source
suite this scaffolding mirrors. The valid-spec fixture tree is built
PROGRAMMATICALLY into a temp dir at import instead of being committed as
files: the repo only carries markdown under plans/ and docs/, so test data
lives in code and materializes per run.

  - ``VALID``     — the read-only valid-spec tree every ``make_proj`` copies.
  - ``make_proj`` — writable copy of the fixture, optional git-init baseline.
  - ``append_to`` — append a line to a docs/product artifact.
"""

import atexit
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


# The dev who configured THIS repo runs with HARNESS_* posture overrides exported
# (terminal voice / guard / stage point at .harness-dev/*, injected via the
# .claude/settings.json `env` block). Those must NOT bleed into the suite: every
# test asserts SHIPPED-default behavior unless it sets its own override via
# monkeypatch. Scrub the posture-config pointers once per test so a configured
# dev session and a clean CI run see identical defaults. Mirrors the pre-push
# hook's HARNESS_* scrub — posture input is the tracked/default file, never the
# ambient env. A test that needs an override re-sets it with monkeypatch (runs
# after this autouse fixture, so it wins).
_DEV_POSTURE_ENV = (
    "HARNESS_TERMINAL_VOICE",
    "HARNESS_GUARD_POLICY",
    "HARNESS_STAGE_POLICY",
)


@pytest.fixture(autouse=True)
def _scrub_dev_posture_env(monkeypatch):
    for name in _DEV_POSTURE_ENV:
        monkeypatch.delenv(name, raising=False)

# One small product spec: PRODUCT + vision + BRD (2 goals) + 1 PRD chain down
# to a story with acceptance criteria. The body-hash and AC-hash tests anchor
# on exact strings in here ("they reach the home page.", "$1M ARR") — keep
# those stable or update the test anchors with them.
_FIXTURE_FILES = {
    "docs/product/PRODUCT.md": """---
id: PRODUCT
type: product
status: approved
lang: en
owner: Jane Doe
version: 1.0.0
created: 2026-05-28
updated: 2026-05-28
name: "Acme Shop"
one_line_description: "A web storefront for boutique fashion brands."
current_implementation: "early prototype"
deployment: "Vercel + Supabase"
roadmap_one_liner: "Launch checkout flow this quarter."
core_value: "Help boutique brands sell directly to fans without middlemen."
personas: [shopper, store-admin]
---

# Acme Shop — Product Context

Thin labels for the Acme Shop fixture.
""",
    "docs/product/vision.md": """---
id: VISION
type: vision
status: approved
lang: en
owner: Jane Doe
version: 1.0.0
created: 2026-05-28
updated: 2026-05-28
personas: [shopper, store-admin]
---

# Vision — Acme Shop

## Problem Narrative

Boutique fashion brands sell through marketplaces that take 30%+ and bury
them under competitors. Their fans want to support them directly but have no
easy path. Acme Shop closes that gap.

## Value Proposition

For boutique brands, this is the only storefront that lets them keep 95% of
revenue and message fans directly.
""",
    "docs/product/brd.md": """---
id: BRD
type: brd
status: approved
lang: en
owner: Jane Doe
version: 1.0.0
created: 2026-05-28
updated: 2026-05-28
goals:
  - id: BRD-G1
    title: "Reach $1M ARR in 12 months"
    status: approved
    metrics: [arr]
  - id: BRD-G2
    title: "Hit 80% repeat-purchase rate"
    status: approved
    metrics: [repeat-rate]
---

# BRD

Reach the ARR goal by acquiring brands and converting their fans.
""",
    "docs/product/prds/auth.md": """---
id: PRD-AUTH
type: prd
brd_goals: [BRD-G1]
status: approved
lang: en
owner: Jane Doe
version: 1.0.0
created: 2026-05-28
updated: 2026-05-28
personas: [shopper]
scope: in
moscow: must
horizon: now
metrics: [signup-conversion]
---

# Auth PRD

Lets shoppers sign in.
""",
    "docs/product/epics/PRD-AUTH-E1.md": """---
id: PRD-AUTH-E1
type: epic
prd: PRD-AUTH
brd_goals: [BRD-G1]
status: draft
lang: en
owner: Jane Doe
version: 0.1.0
created: 2026-05-28
updated: 2026-05-28
personas: [shopper]
scope: in
moscow: must
horizon: now
---

# Sign-In Epic

Lets shoppers sign in with email + password.
""",
    "docs/product/stories/PRD-AUTH-E1-S1.md": """---
id: PRD-AUTH-E1-S1
type: story
epic: PRD-AUTH-E1
status: draft
lang: en
owner: Jane Doe
version: 0.1.0
created: 2026-05-28
updated: 2026-05-28
personas: [shopper]
scope: in
moscow: must
size: S
horizon: now
acceptance_criteria:
  - "Given a registered user, when they enter correct credentials, then they reach the home page."
  - "Given five failed attempts, when they try again, then they are rate-limited for 15 minutes."
---

# Sign-In Story

As a shopper I want to sign in so that I can resume my saved cart.
""",
}


def _build_valid() -> Path:
    base = Path(tempfile.mkdtemp(prefix="harness-valid-spec-"))
    atexit.register(shutil.rmtree, base, True)
    root = base / "valid-spec"
    for rel, content in _FIXTURE_FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


VALID = _build_valid()


def _git(root: Path, *args):
    subprocess.run(["git", *args], cwd=root, check=True,
                   capture_output=True, text=True)


def make_proj(tmp_path: Path, git: bool = True) -> Path:
    """A writable copy of the valid-spec fixture, optionally a committed git
    repo so the fence scan has a clean working-tree baseline (only NEW touches
    show)."""
    proj = tmp_path / "proj"
    shutil.copytree(VALID, proj)
    if git:
        _git(proj, "init", "-q")
        _git(proj, "config", "user.email", "t@t.t")
        _git(proj, "config", "user.name", "t")
        _git(proj, "add", "-A")
        _git(proj, "commit", "-q", "-m", "base")
    return proj


def append_to(proj: Path, rel: str, line: str):
    p = proj / "docs" / "product" / rel
    p.write_text(p.read_text(encoding="utf-8") + line, encoding="utf-8")
