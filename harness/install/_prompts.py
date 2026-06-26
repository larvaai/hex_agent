#!/usr/bin/env python3
"""_prompts.py — interactive install prompts (extracted from install.py).

Pure terminal UX: read the reviewer roster / component selection / opt-in
toggles from a TTY. No install orchestration and no InstallError — the caller
acts on the returned values. Kept separate so install.py reads as orchestration.
"""
import subprocess
import sys


def _prompt_statusline() -> bool:
    """Ask once whether to enable the ccstatusline terminal status bar. Default is
    NO (Enter keeps it off — opt-in). Only called from a TTY when --statusline was
    not supplied."""
    print("Optional: ccstatusline — a terminal status bar (model, git branch, "
          "context %) at the bottom of Claude Code. Wires a statusLine command "
          "and copies a default config (both no-clobber).")
    try:
        ans = input("  enable ccstatusline? [y/N]> ").strip().lower()
    except EOFError:
        ans = ""
    return ans in ("y", "yes")

def _prompt_cli() -> bool:
    """Ask once whether to put the `hs-cli` launcher on PATH. Default NO (Enter
    keeps it off — opt-in). Only called from a TTY when --cli was not supplied."""
    print("Optional: hs-cli — an on-PATH launcher for harness operator verbs "
          "(doctor, list, components, migrate, version). Symlinks "
          "~/.local/bin/hs-cli at the shipped wrapper (no-clobber).")
    try:
        ans = input("  install the hs-cli launcher? [y/N]> ").strip().lower()
    except EOFError:
        ans = ""
    return ans in ("y", "yes")

def _prompt_components(optional_list, defaults=None) -> str:
    """Interactively choose which OPTIONAL components to enable (the install
    UX). Core is never asked — it is always on. Each component's default follows
    the shipped component-policy (default-only-hs: themed groups default OFF, so
    enabling a group is an opt-in); Enter keeps that default. Returns a
    `--components` value: 'all' when every component ends up on, otherwise a CSV
    of the kept names. Only called from a TTY when --components was not supplied."""
    if not optional_list:
        return "all"
    defaults = defaults or {}
    print("Optional components — Enter keeps the shipped default "
          "(themed groups default OFF; opt-in to enable). "
          "Core ships always-on and is not asked.")
    kept = []
    for name in optional_list:
        default_on = bool(defaults.get(name, False))
        hint = "Y/n" if default_on else "y/N"
        try:
            ans = input("  enable %s? [%s]> " % (name, hint)).strip().lower()
        except EOFError:
            ans = ""
        if ans == "":
            on = default_on
        else:
            on = ans in ("y", "yes", "on", "true")
        if on:
            kept.append(name)
    if len(kept) == len(optional_list):
        return "all"
    return ",".join(kept)

def _stdin_is_tty() -> bool:
    """Seam over sys.stdin.isatty() so the interactive decision is testable."""
    return sys.stdin.isatty()

def _git_user_email() -> str:
    """The invoker's git email, used only as a reviewer SUGGESTION. Attribution,
    never authentication. Empty when git or the config is absent."""
    try:
        out = subprocess.run(["git", "config", "user.email"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:  # noqa: BLE001 — a missing git must not abort the install
        return ""

def _prompt_reviewers(suggestion: str = "") -> list:
    """Interactively collect reviewer emails (one per line, blank to finish).
    Only called from a TTY when --reviewers was not supplied. A git-derived
    suggestion seeds the first entry (Enter accepts it). The deployer is warned
    that the approval gate needs at least one reviewer OTHER than the change
    author, so a roster of only their own address can never approve their work."""
    print("Reviewer roster for the approval gate "
          "(one email per line, blank to finish).")
    print("  NOTE: the gate requires an approver who is NOT the change author — "
          "add at least one teammate; a roster of only your own address can "
          "never approve your own changes.")
    out = []
    if suggestion:
        try:
            first = input("  reviewer [%s]> " % suggestion).strip()
        except EOFError:
            first = ""
        out.append(first or suggestion)
    while True:
        try:
            line = input("  reviewer> ").strip()
        except EOFError:
            break
        if not line:
            break
        out.append(line)
    return out
