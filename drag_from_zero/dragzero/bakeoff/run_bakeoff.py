"""Drive the substrate bake-off and hand off to the REAL bakeoff_rank.py (never reimplement verdict).

    python -m dragzero.bakeoff.run_bakeoff --plan-dir <plan>/artifacts

Runs each AVAILABLE candidate through the standard scenario twice (determinism gate, spread==0),
scores ONE scalar each, and:
  * < 2 candidates  -> REFUSE ("insufficient candidates — install .[bakeoff]"), no verdict, Z not crowned.
  * >= 2 candidates -> shell `bakeoff_rank.py record` per candidate, then `rank --plan-dir` -> verdict.

langgraph/burr are lazy: `import dragzero` never pulls them; missing ones are simply absent here.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .candidate_zerodep import ZeroDepSubstrate
from .scenario import run_scenario
from .score import score

REFUSE_EXIT = 4


def available_candidates() -> list:
    """(name, factory) for every candidate whose dependency is importable. Z is always present."""
    avail = [("zerodep", ZeroDepSubstrate)]
    if importlib.util.find_spec("langgraph") is not None:
        from .candidate_langgraph import LangGraphSubstrate
        avail.append(("langgraph", LangGraphSubstrate))
    if importlib.util.find_spec("burr") is not None:
        from .candidate_burr import BurrSubstrate
        avail.append(("burr", BurrSubstrate))
    return avail


def evaluate(factory) -> tuple:
    """Run the scenario twice; return (score, result, deterministic). Determinism = identical events."""
    r1 = run_scenario(factory())
    r2 = run_scenario(factory())
    return score(r1), r1, (r1.events == r2.events)


def score_candidates(candidates) -> tuple:
    """-> (scored:{name:scalar}, rationale:{name:str}). Non-deterministic candidates are dropped."""
    scored, rationale = {}, {}
    for name, factory in candidates:
        s, result, deterministic = evaluate(factory)
        if not deterministic:
            rationale[name] = "dropped: non-deterministic events (spread>0)"
            continue
        scored[name] = s
        passed = [k for k, v in result.capabilities.items() if v]
        rationale[name] = (f"inject_clean={int(result.inject_clean)} recomposed={int(result.recomposed)} "
                           f"observability={len(passed)}/{len(result.capabilities)} ({','.join(passed) or 'none'})")
    return scored, rationale


def under_two_reason(scored: dict) -> str | None:
    if len(scored) < 2:
        return ("insufficient candidates — install drag_from_zero[bakeoff] (langgraph/burr) to give Z a "
                "challenger; scored: %s. Z is NOT crowned unopposed." % list(scored))
    return None


def find_rank_script(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    env = os.environ.get("DRAGZERO_BAKEOFF_RANK")
    if env and Path(env).is_file():
        return env
    here = Path(__file__).resolve()
    for base in list(here.parents):
        cand = base / "harness" / "scripts" / "bakeoff_rank.py"
        if cand.is_file():
            return str(cand)
    return None


def _rank(scored: dict, rationale: dict, plan_dir: str, rank_script: str, run_id: str,
          direction="higher", noise="low") -> tuple:
    for name, value in scored.items():
        subprocess.run([sys.executable, rank_script, "record", "--run", run_id,
                        "--candidate", name, "--trial", "0", "--value", str(value)], check=True)
    proc = subprocess.run([sys.executable, rank_script, "rank", "--run", run_id,
                           "--direction", direction, "--noise", noise, "--rel-band", "0.05",
                           "--plan-dir", plan_dir], capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout)
    print("rationale:", json.dumps(rationale, ensure_ascii=False))
    return proc.returncode, (json.loads(proc.stdout) if proc.stdout.strip() else {})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="run_bakeoff")
    ap.add_argument("--plan-dir", required=True, help="dir to write bakeoff-verdict.json into")
    ap.add_argument("--rank-script", default=None, help="path to harness/scripts/bakeoff_rank.py")
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args(argv)

    scored, rationale = score_candidates(available_candidates())
    refuse = under_two_reason(scored)
    if refuse:
        print("REFUSE:", refuse)
        print("rationale:", json.dumps(rationale, ensure_ascii=False))
        return REFUSE_EXIT

    rank_script = find_rank_script(args.rank_script)
    if rank_script is None:
        print("ERROR: bakeoff_rank.py not found (pass --rank-script or set DRAGZERO_BAKEOFF_RANK)", file=sys.stderr)
        return 5
    run_id = args.run_id or f"substrate-bakeoff-{int(time.time())}"
    rc, _ = _rank(scored, rationale, args.plan_dir, rank_script, run_id)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
