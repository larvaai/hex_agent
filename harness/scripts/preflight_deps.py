#!/usr/bin/env python3
"""preflight_deps.py — check that external deps the harness needs are importable.

Policy: external deps are allowed but CONTROLLED — this script is the
single registry. Run it once per machine after clone (and in CI before tests).
Missing deps: prints the exact install command and exits non-zero.

Posture downstream when someone skips this step:
  - compliance hooks fail CLOSED (exit 2 + the same install command),
  - telemetry/nudge hooks skip silently.

Usage:
    python3 harness/scripts/preflight_deps.py            # human report
    python3 harness/scripts/preflight_deps.py --quiet    # exit code only (hooks/CI)
"""

import importlib
import sys

# module-to-import -> pip distribution name
REQUIRED = {
    "yaml": "pyyaml",   # human-edited config files (harness-hooks/stage-policy/ownership)
    "pytest": "pytest", # official test runner
}


def missing_deps() -> list:
    """Return pip names of required deps that cannot be imported."""
    out = []
    for module, pip_name in REQUIRED.items():
        try:
            importlib.import_module(module)
        except ImportError:
            out.append(pip_name)
    return out


def install_command(missing: list) -> str:
    return "pip install " + " ".join(sorted(missing))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    quiet = "--quiet" in argv
    missing = missing_deps()
    if not missing:
        if not quiet:
            print("preflight OK: " + ", ".join(sorted(REQUIRED.values())))
        return 0
    if not quiet:
        sys.stderr.write(
            "preflight FAILED — missing dependencies: %s\n"
            "Install with:\n    %s\n" % (", ".join(missing), install_command(missing))
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
