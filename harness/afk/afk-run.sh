#!/usr/bin/env bash
# afk-run.sh — the GREEN-branch launcher for AFK (Ralph) mode.
#
# Preflight has already vouched for the host; this script's job is the narrow,
# load-bearing part: launch Ralph in the *isolated* posture and refuse to give
# up that isolation by accident.
#
#   afk-run.sh [--i-know] "<plan> <prd>" <N> [extra ralph-afk flags...]
#
# Posture (safe by default):
#   - RALPH_IMAGE       = ralph-sandbox-harness  (the harness sandbox image;
#                         an existing RALPH_IMAGE override is honored — that is
#                         the break-glass digest pin
#   - RALPH_DOCKER_SOCK = 0                       (no host docker socket mount)
#
# Mounting the host docker socket hands the sandbox root-equivalent control of
# this machine's Docker daemon. So a non-zero RALPH_DOCKER_SOCK is REFUSED
# unless the caller passes --i-know — an informed opt-out, with the blast radius
# printed, not a silent default.
#
# The loop only ever commits. It never pushes, opens a PR, or ships — that
# boundary is the in-loop stage gate plus a human reviewing the diff before any
# merge. This launcher does not change that.
set -euo pipefail

AFK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RALPH_AFK_BIN="${RALPH_AFK_BIN:-ralph-afk}"

# --- parse args: --i-know flag anywhere; first two positionals = inputs, N ---
IKNOW=0
INPUTS=""
ITERATIONS=""
EXTRA=()
seen_positional=0
for arg in "$@"; do
  case "$arg" in
    --i-know) IKNOW=1 ;;
    *)
      if [ "$seen_positional" -eq 0 ]; then
        INPUTS="$arg"; seen_positional=1
      elif [ -z "$ITERATIONS" ]; then
        ITERATIONS="$arg"
      else
        EXTRA+=("$arg")
      fi
      ;;
  esac
done

if [ -z "$INPUTS" ]; then
  echo "usage: afk-run.sh [--i-know] \"<plan> <prd>\" <N> [ralph-afk flags...]" >&2
  exit 64
fi
ITERATIONS="${ITERATIONS:-1}"
if ! printf '%s' "$ITERATIONS" | grep -qE '^[0-9]+$' || [ "$ITERATIONS" -lt 1 ]; then
  echo "error: <N> must be a positive integer, got: $ITERATIONS" >&2
  exit 64
fi

# --- posture: image + socket -------------------------------------------------
export RALPH_IMAGE="${RALPH_IMAGE:-ralph-sandbox-harness}"

SOCK="${RALPH_DOCKER_SOCK:-0}"
if [ "$SOCK" != "0" ]; then
  if [ "$IKNOW" -ne 1 ]; then
    cat >&2 <<EOF
REFUSING to launch: RALPH_DOCKER_SOCK=$SOCK would bind-mount the host docker
socket into the sandbox.
Blast radius: the unattended loop would gain root-equivalent control of this
machine's Docker daemon — it could start privileged containers, read other
containers' data, or mount the host filesystem. That defeats the isolation AFK
mode exists to provide.
If you genuinely need it, re-run with --i-know to opt in knowingly.
EOF
    exit 2
  fi
  cat >&2 <<EOF
WARNING (--i-know): mounting the host docker socket (RALPH_DOCKER_SOCK=$SOCK).
Blast radius: the loop has root-equivalent control of the host Docker daemon.
Proceeding because you opted in.
EOF
fi
export RALPH_DOCKER_SOCK="$SOCK"

echo "afk-run: RALPH_IMAGE=$RALPH_IMAGE RALPH_DOCKER_SOCK=$RALPH_DOCKER_SOCK inputs=[$INPUTS] N=$ITERATIONS"

# --- self-heal: build the harness image if absent (local image, not a pull) --
if ! docker image inspect "$RALPH_IMAGE" >/dev/null 2>&1; then
  if [ "$RALPH_IMAGE" = "ralph-sandbox-harness" ]; then
    echo "afk-run: image absent — building from $AFK_DIR/Dockerfile"
    docker build -f "$AFK_DIR/Dockerfile" -t ralph-sandbox-harness "$AFK_DIR"
  else
    echo "afk-run: note — $RALPH_IMAGE not present locally; Ralph will resolve it" >&2
  fi
fi

if [ "${AFK_NATIVE_LOOP:-0}" = "0" ] && ! command -v "$RALPH_AFK_BIN" >/dev/null 2>&1; then
  echo "error: $RALPH_AFK_BIN not on PATH — install the Ralph CLI" >&2
  exit 69
fi

# --- run: probe with one iteration, then the remaining N-1 -------------------
# A single probe iteration first: if the very first round fails (auth, egress,
# a wedged image) there is no point burning the rest of the budget.
# Native-loop mode: the harness drives the iteration loop itself via the loop
# controller, run INSIDE the sandbox image so isolation is preserved — a host-side
# run would bypass the container boundary. No host docker socket is mounted here
# regardless of RALPH_DOCKER_SOCK. Default stays on Ralph until the native image
# path is validated against a live image.
#
# Probe-abort threshold differs by mode. Ralph: any non-zero exit is a failed
# probe. Native loop controller: exit 1 means a HEALTHY run hit its iteration
# budget (a one-iteration probe always exhausts at N=1), which is NOT a failure —
# only exit >= 2 signals a genuine guard trip or error worth aborting on. So the
# native probe tolerates exit 1 and aborts only at exit >= 2.
NATIVE_LOOP=0
if [ "${AFK_NATIVE_LOOP:-0}" != "0" ]; then
  NATIVE_LOOP=1
  echo "afk-run: native loop-controller mode (in-sandbox)"
  # The in-sandbox claude must authenticate before it can do anything, so the
  # native loop is non-functional without the operator's credentials. Bind-mount
  # the host ~/.claude READ-ONLY into the container home. This is MANDATORY for
  # native mode, not a posture toggle: the sandbox still contains the loop's
  # blast radius (no host filesystem, no docker socket) — it does not hide the
  # operator's own token from the loop that has to use it.
  AUTH_MOUNT=()
  if [ -d "${HOME}/.claude" ]; then
    AUTH_MOUNT=(-v "${HOME}/.claude":/home/agent/.claude:ro)
  else
    echo "afk-run: WARNING — no ~/.claude on host: the in-sandbox claude will be" \
         "unauthenticated and the loop will fail at the first model call. Run" \
         "'claude' once to log in before a native run." >&2
  fi
  run_iter() {
    docker run --rm -v "$PWD":/work "${AUTH_MOUNT[@]}" -w /work \
      -e HARNESS_ROOT=/work "$RALPH_IMAGE" \
      python3 /work/harness/afk/loop_controller.py "$INPUTS" "$1" \
        --repo-root /work --state-dir /work/harness/state/afk
  }
else
  run_iter() {
    "$RALPH_AFK_BIN" "$INPUTS" "$1" "${EXTRA[@]}"
  }
fi

# Run the probe and decide whether its exit code means "abort the rest".
# Returns 0 to continue, 1 to abort.
probe_failed() {
  local rc=0
  run_iter 1 || rc=$?
  if [ "$NATIVE_LOOP" -eq 1 ]; then
    # exit 1 == clean max-iterations on the probe; abort only on a real error.
    [ "$rc" -ge 2 ]
  else
    [ "$rc" -ne 0 ]
  fi
}

echo "afk-run: probe iteration (1 of $ITERATIONS)"
if probe_failed; then
  echo "afk-run: the first (probe) iteration failed — stopping before burning" \
       "the remaining $((ITERATIONS - 1)) iteration(s). Check auth/egress and" \
       "the .ralph-tmp logs, then re-run." >&2
  exit 1
fi

remaining=$((ITERATIONS - 1))
if [ "$remaining" -gt 0 ]; then
  echo "afk-run: probe ok — running remaining $remaining iteration(s)"
  # Same exit-code contract as the probe: in native mode a controller exit 1 is a
  # clean max-iterations finish, not a failure — only exit >= 2 is a real error.
  rc=0
  run_iter "$remaining" || rc=$?
  if [ "$NATIVE_LOOP" -eq 1 ]; then
    [ "$rc" -ge 2 ] && exit "$rc"
  else
    [ "$rc" -ne 0 ] && exit "$rc"
  fi
fi

echo "afk-run: done ($ITERATIONS iteration(s)). Review the diff before any merge/push."
