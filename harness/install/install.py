#!/usr/bin/env python3
"""install.py — one-command install of the harness into a target repo.

Turns the source harness tree into an installed-and-wired copy:
  1. copy the git-tracked harness/ tree into <target>/harness/ (the tracked set
     is exactly what manifest.json covers, so verify stays clean for free;
     untracked org standards under standards/ are INPUT, never shipped);
  2. materialize hooks-registration.yaml into <target>/.claude/settings.json in
     Claude Code shape, $HARNESS_ROOT -> "$CLAUDE_PROJECT_DIR", MERGED into any
     user-authored hooks (additive, dedup by command — never clobbers);
  3. install the pre-push transport gate into <target>/.git/hooks/pre-push,
     backing up a pre-existing foreign hook to pre-push.bak;
  4. write the reviewer roster into the TARGET's harness/data/team.yaml (the
     loader is no-env-override, so the roster must live tracked in the target,
     never committed back into the source);
  5. check the org standards are present (warn-only — authoring them is the
     org's job, the installer never fabricates);
  6. run verify_install as the final gate and report drift per file.

Every mutation is idempotent and previewable with --dry-run; --uninstall
reverses the settings and pre-push edits (the harness/ tree is left in place —
deleting it is the documented clean uninstall).

On a TTY with no --reviewers, the installer prompts for the roster, seeding a
suggestion from `git config user.email` and warning that the approval gate needs
a reviewer who is NOT the change author. --non-interactive (alias --yes) forces
the non-prompt path even on a TTY (the CI case); a non-TTY never prompts.

Usage:
    python3 harness/install/install.py [--target <repo>] [--reviewers a@x,b@y]
                                       [--local] [--dry-run] [--strict]
                                       [--non-interactive|--yes] [--uninstall]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from build_manifest import sha256_file  # noqa: E402
import verify_install  # noqa: E402

if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from _prompts import (  # noqa: E402 — sibling install-package module
    _stdin_is_tty, _git_user_email, _prompt_reviewers,
    _prompt_statusline, _prompt_cli, _prompt_components)
from _errors import InstallError  # noqa: E402
from _settings import (  # noqa: E402
    _settings_path, _read_json, _load_settings, _write_settings)
from _hooks import (  # noqa: E402 — sibling install-package module
    ALLOWED_EVENTS, to_command, load_registration, materialize_hooks,
    _find_group, merge_hooks, strip_harness_hooks, _invokes_harness_hook)

# The local plugin marketplace: name CC keys plugins under, the core plugin that
# is never disabled, and the directory CC loads plugins from (relative to the
# target repo root, the form CC expects in extraKnownMarketplaces).
MARKETPLACE = "hs-local"
CORE_PLUGIN = "hs"
_PLUGINS_REL = "./harness/plugins"

# Files the installer (or the deploying team) localizes per target ship as a
# baseline in the manifest, but post-install divergence is customization, not
# integrity drift — so the final verify reports it as a note rather than failing
# --strict over it. The classifier is verify_install.is_localized (single source
# of truth, shared with the verify CLI — no second copy of the rule here).


def normalize_reviewers(items) -> list:
    """Reviewer entries are `user:<email>` / `role:<name>` strings. A bare email
    gets the `user:` prefix; already-qualified entries pass through; blanks drop."""
    out = []
    for raw in items or []:
        r = (raw or "").strip()
        if not r:
            continue
        out.append(r if ":" in r else "user:" + r)
    return out


def render_roster(text: str, reviewers: list) -> str:
    """Replace the `reviewers:` line in team.yaml with a flow list, preserving
    the trailing comment and the rest of the file (comments, claims, etc.)."""
    flow = "[" + ", ".join('"%s"' % r for r in reviewers) + "]"
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("reviewers:"):
            comment = "  " + line[line.index("#"):] if "#" in line else ""
            lines[i] = "reviewers: %s%s" % (flow, comment)
            break
    else:
        lines.insert(0, "reviewers: %s" % flow)
    return "\n".join(lines) + "\n"


# --- filesystem steps (guarded by dry_run via the orchestrator) ----------


def _manifest_harness_files(source_root: Path) -> list:
    """The shipped file list straight from manifest.json — the fallback when the
    source is not a git work tree (an extracted bundle has no .git). The manifest
    enumerates exactly the tracked harness/ set, so this matches the git path."""
    manifest = Path(source_root) / "harness" / "manifest.json"
    if not manifest.is_file():
        raise InstallError(
            "%s has no .git and no harness/manifest.json — not an installable "
            "harness tree. Point --source at an extracted bundle or the harness "
            "repo." % source_root)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    rels = [rel for rel in data.get("files", {}) if rel.startswith("harness/")]
    # manifest.json is excluded from its own hash map but IS tracked (the git
    # path copies it) and the target needs it to verify — add it back so the
    # bundle and the git source install the same set.
    rels.append("harness/manifest.json")
    return rels


def _tracked_harness_files(source_root: Path) -> list:
    """Files to copy, preferring git (the dev/dogfood source) and falling back to
    manifest.json. The fallback fires in two cases: (1) no git work tree — an
    extracted bundle has no .git, so `git ls-files` errors; (2) a git work tree
    whose harness/ is untracked — the bundle was extracted into an existing repo
    (or the suite re-installs from a freshly installed copy), so `git ls-files`
    exits 0 with NO output. In both, the manifest is the authoritative file set;
    an empty git listing must not collapse the install to zero files."""
    try:
        out = subprocess.run(
            ["git", "-C", str(source_root), "ls-files", "--", "harness/"],
            capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return _manifest_harness_files(source_root)
    files = [l for l in out.stdout.splitlines() if l.strip()]
    return files or _manifest_harness_files(source_root)


def _rel_escapes(rel: str) -> bool:
    """True if a manifest/listing path is absolute or climbs out of its root via
    `..`. git ls-files never emits these; the manifest fallback is attacker-
    influenced (a crafted bundle), so `harness/../../tmp/evil` must be refused
    before it is joined to the target and copied — otherwise it writes outside
    the install target (arbitrary write). Paths are posix-style in the manifest."""
    p = PurePosixPath(rel)
    return p.is_absolute() or ".." in p.parts


def _copy_tree(source_root: Path, target_root: Path, dry_run: bool) -> str:
    rels = _tracked_harness_files(source_root)
    copied = 0
    for rel in rels:
        # Containment backstop: a crafted bundle manifest could list a path that
        # escapes the target; reject it before any mkdir/copy (single enforcement
        # point covering both the git and manifest file sources).
        if _rel_escapes(rel):
            raise InstallError(
                "refusing to install path that escapes the target: %r — "
                "harness/ paths must stay inside the target (a bundle manifest "
                "may be crafted)" % rel)
        src = source_root / rel
        if not src.is_file():
            continue  # tracked-but-deleted — verify's job, not ours
        copied += 1
        if not dry_run:
            dst = target_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    return "copy harness/ tree (%d tracked files)" % copied


def _wire_settings(target_root, registration, local, result, dry_run):
    new_hooks, skipped = materialize_hooks(registration)
    result["skipped_events"].extend(skipped)
    path = _settings_path(target_root, local)
    settings = _load_settings(path)
    settings["hooks"] = merge_hooks(settings.get("hooks", {}), new_hooks)
    _write_settings(path, settings, dry_run)
    result["actions"].append(
        "wire %d event(s) into %s" % (len(new_hooks), path.name))
    for event, _cmd in skipped:
        result["warnings"].append(
            "skipped non-Claude-Code event %r (not wired)" % event)


def _statusline_config_home(override) -> Path:
    """Where ccstatusline keeps its config. The documented default is
    ~/.config/ccstatusline; the override is an explicit install() param so the
    home write is testable without touching the real ~/.config."""
    if override is not None:
        return Path(override)
    return Path.home() / ".config" / "ccstatusline"


def _wire_statusline(source_root, target_root, local, result, dry_run, home_override):
    """Opt-in ccstatusline onboarding. Two no-clobber writes:
    (1) a `statusLine` block in the target's settings.json (the npx command
    auto-installs ccstatusline on first run), and (2) a shipped default config
    copied into the user's config home. An existing statusLine or an existing
    config file is left exactly as the user had it."""
    path = _settings_path(target_root, local)
    settings = _load_settings(path)
    if "statusLine" in settings:
        result["actions"].append(
            "statusLine already set in %s — left as-is" % path.name)
    else:
        settings["statusLine"] = {
            "type": "command",
            "command": "npx -y ccstatusline@latest",
            "padding": 0,
        }
        _write_settings(path, settings, dry_run)
        result["actions"].append(
            "wire statusLine (ccstatusline) into %s" % path.name)

    cfg_dir = _statusline_config_home(home_override)
    cfg = cfg_dir / "settings.json"
    asset = source_root / "harness" / "data" / "ccstatusline-default.json"
    if cfg.is_file():
        result["actions"].append(
            "ccstatusline config exists at %s — left as-is" % cfg)
    elif not asset.is_file():
        result["warnings"].append(
            "ccstatusline default config asset missing: %s" % asset)
    elif dry_run:
        result["actions"].append("ccstatusline config -> %s (dry-run)" % cfg)
    else:
        cfg_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(asset, cfg)
        result["actions"].append("copy default ccstatusline config -> %s" % cfg)


def _cli_bindir(override) -> Path:
    """Where the on-PATH `hs-cli` launcher is dropped. Default ~/.local/bin (the
    XDG user-bin convention, already on PATH in most shells); an explicit
    override keeps it testable."""
    if override:
        return Path(override)
    return Path.home() / ".local" / "bin"


def _wire_cli(source_root, target_root, result, dry_run, bindir_override):
    """Opt-in: put an `hs-cli` launcher on PATH. POSIX → a no-clobber symlink in
    ~/.local/bin pointing at the shipped harness/bin/hs-cli wrapper (which
    resolves the repo from its own location and delegates to hs_cli.py). Windows
    has no reliable user symlink → advise adding harness/bin to PATH. Never
    clobbers an existing hs-cli; no package manager involved (just a launcher)."""
    wrapper = target_root / "harness" / "bin" / "hs-cli"
    if not wrapper.is_file():
        result["warnings"].append("hs-cli wrapper missing: %s" % wrapper)
        return
    if not dry_run:
        try:  # tar can drop the exec bit — restore it so the launcher runs
            wrapper.chmod(0o755)
        except OSError:
            pass
    if os.name == "nt":
        result["actions"].append(
            "hs-cli: on Windows add %s to PATH (hs-cli.cmd launcher)"
            % wrapper.parent)
        return
    bindir = _cli_bindir(bindir_override)
    link = bindir / "hs-cli"
    if link.exists() or link.is_symlink():
        result["actions"].append("hs-cli already at %s — left as-is" % link)
        return
    if dry_run:
        result["actions"].append("hs-cli symlink -> %s (dry-run)" % link)
        return
    try:
        bindir.mkdir(parents=True, exist_ok=True)
        link.symlink_to(wrapper)
        result["actions"].append("link hs-cli -> %s" % wrapper)
        on_path = str(bindir) in (os.environ.get("PATH") or "").split(os.pathsep)
        if not on_path:
            result["warnings"].append(
                "%s is not on PATH — add it to call `hs-cli` directly" % bindir)
    except OSError as e:  # noqa: BLE001 — a launcher we could not link is a warning
        result["warnings"].append("could not link hs-cli (%s)" % e)


def _chosen_components(components, components_arg) -> set:
    """Resolve `--components=all|csv` to the set of ENABLED component names.
    `all` (the default, or a missing/None arg) selects every declared component;
    a CSV selects only the named ones; an EMPTY string selects NONE (the "disable
    every optional component" choice — distinct from absent, which means all). An
    unknown name is a hard InstallError (a typo must not silently disable a
    component). Shared by the hook projector and the plugin wirer."""
    arg = "all" if components_arg is None else components_arg.strip()
    if arg == "all":
        return set(components)
    chosen = {c.strip() for c in arg.split(",") if c.strip()}
    unknown = chosen - set(components)
    if unknown:
        raise InstallError(
            "unknown component(s) %s — known: %s"
            % (", ".join(sorted(unknown)), ", ".join(sorted(components))))
    return chosen


def _apply_components(target_root, components_arg, result, dry_run):
    """Project the component selection into the TARGET (ship-all-but-off).
    The tree is already copied and every hook already wired; this only flips
    the `enabled` flag for DESELECTED components (off = runtime-disabled, never
    unwired or deleted) and records install-state. `--components=all` enables
    everything; a CSV (e.g. `rbac,decision-capture`) enables only those."""
    arg = "all" if components_arg is None else components_arg.strip()
    if dry_run:  # the target tree is not copied on a dry run — plan, don't read
        result["actions"].append(
            "components: project selection %r (dry-run)" % (arg or "(none)"))
        return
    scripts_dir = target_root / "harness" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    try:
        import component_config as cc
    except Exception as e:  # noqa: BLE001 — no projector → leave defaults on
        result["warnings"].append("component projector unavailable: %s" % e)
        return
    comp_file = target_root / "harness" / "data" / "components.yaml"
    try:
        components = cc.load_components(comp_file)
    except cc.ComponentConfigError as e:
        result["warnings"].append("components.yaml unreadable: %s" % e)
        return

    chosen = _chosen_components(components, arg)
    selection = {name: (name in chosen) for name in components}
    off = sorted(n for n, on in selection.items() if not on)

    try:
        # Hooks/policy/state only — enabledPlugins is wired separately by
        # _wire_plugins (it owns the full marketplace list + core plugin).
        cc.apply_selection(
            selection, components_path=comp_file,
            policy_path=target_root / "harness" / "data" / "component-policy.yaml",
            hooks_path=target_root / "harness" / "hooks" / "harness-hooks.yaml",
            state_path=target_root / "harness" / "state" / "install-state.json")
    except cc.ComponentConfigError as e:
        raise InstallError("component selection invalid: %s" % e)
    result["actions"].append(
        "components: %d enabled, disabled=%s" % (len(chosen), off or "none"))


def _marketplace_plugins(target_root) -> list:
    """Plugin names declared in the local marketplace — the source of truth for
    which plugins exist. [] when the marketplace file is absent or unreadable."""
    mp = (target_root / "harness" / "plugins" / ".claude-plugin"
          / "marketplace.json")
    if not mp.is_file():
        return []
    try:
        data = json.loads(mp.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a broken marketplace wires no plugins
        return []
    return [p.get("name") for p in data.get("plugins", []) if p.get("name")]


def _wire_plugins(target_root, components_arg, local, result, dry_run):
    """Wire EVERY plugin the marketplace declares into the SAME settings file
    the hooks go to (one file, never split): write extraKnownMarketplaces.hs-local
    + enabledPlugins. Ship-all-but-off — every plugin defaults ENABLED; a
    component that maps to a plugin (components.yaml `plugin:`) and is deselected
    turns that plugin enabledPlugins:false while its DIR still ships. Core plugin
    `hs` is always enabled. Idempotent merge; user-authored keys are preserved."""
    plugins = _marketplace_plugins(target_root)
    if not plugins:
        return  # no marketplace → nothing to wire

    states = {name: True for name in plugins}  # ship-all default: every plugin on
    scripts_dir = target_root / "harness" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    try:
        import component_config as cc
        comp_file = target_root / "harness" / "data" / "components.yaml"
        components = cc.load_components(comp_file)
        chosen = _chosen_components(components, components_arg)
        selection = {n: (n in chosen) for n in components}
        for plugin, enabled in cc.plugin_states(components, selection).items():
            if plugin in states:
                states[plugin] = enabled
    except InstallError:
        raise
    except Exception as e:  # noqa: BLE001 — no components map → leave all on
        result["warnings"].append("plugin component-map unavailable: %s" % e)
    if CORE_PLUGIN in states:
        states[CORE_PLUGIN] = True  # core is never disabled, whatever a component
        # says — but only if the marketplace actually declares it (don't inject a
        # phantom enable key for a core that isn't there).

    if dry_run:
        result["actions"].append(
            "plugins: wire %d (%s) (dry-run)"
            % (len(states), ", ".join(sorted(states))))
        return
    path = _settings_path(target_root, local)
    settings = _load_settings(path)
    mk = dict(settings.get("extraKnownMarketplaces") or {})
    mk[MARKETPLACE] = {"source": {"source": "directory", "path": _PLUGINS_REL}}
    settings["extraKnownMarketplaces"] = mk
    ep = dict(settings.get("enabledPlugins") or {})
    for plugin, enabled in states.items():
        ep["%s@%s" % (plugin, MARKETPLACE)] = bool(enabled)
    settings["enabledPlugins"] = ep
    _write_settings(path, settings, dry_run)
    off = sorted(p for p, on in states.items() if not on)
    result["actions"].append(
        "plugins: %d wired into %s, disabled=%s"
        % (len(states), path.name, off or "none"))


def _install_prepush(source_root, target_root, result, dry_run):
    git_dir = target_root / ".git"
    if not git_dir.is_dir():
        result["warnings"].append(
            ".git not found — pre-push transport gate skipped "
            "(run the installer inside a git work tree)")
        return
    src = source_root / "harness" / "install" / "git-pre-push-hook.sh"
    hooks_dir = git_dir / "hooks"
    dst = hooks_dir / "pre-push"
    if dst.is_file() and sha256_file(dst) != sha256_file(src):
        if not dry_run:
            shutil.copy2(dst, hooks_dir / "pre-push.bak")
        result["actions"].append(
            "back up existing pre-push -> pre-push.bak")
    if not dry_run:
        hooks_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        dst.chmod(0o755)
    result["actions"].append("install pre-push hook")


def _write_roster(target_root, source_root, reviewers, result, dry_run,
                  no_track=False):
    if source_root == target_root:
        if reviewers:
            result["warnings"].append(
                "source == target: roster left as-is (won't clobber the "
                "source roster — set reviewers in a real install target)")
        return
    if no_track:
        # --no-track gitignores harness/, so team.yaml is invisible to the
        # adopter's git. The roster's safety rests on being tamper-visible via a
        # git diff; writing it into an untracked file would fake that guarantee.
        if reviewers:
            result["warnings"].append(
                "roster NOT written: --no-track gitignores harness/, so a roster "
                "change cannot be tamper-visible in git. Track harness/ (drop "
                "--no-track) to use the approval gate with a real roster")
        return
    if not reviewers:
        return
    norm = normalize_reviewers(reviewers)
    path = target_root / "harness" / "data" / "team.yaml"
    if not path.is_file():
        result["warnings"].append(
            "team.yaml not found at target — roster skipped")
        return
    if not dry_run:
        path.write_text(render_roster(path.read_text(encoding="utf-8"), norm),
                        encoding="utf-8")
    result["actions"].append(
        "write roster (%d reviewer(s)) -> harness/data/team.yaml" % len(norm))


def _standards_maxloc() -> int:
    """Advisory line budget for a standards doc (tunable). Default mirrors the
    repo's docs footprint limit."""
    raw = os.environ.get("HARNESS_STANDARDS_MAXLOC", "").strip()
    try:
        return int(raw) if raw else 800
    except ValueError:
        return 800


_GITIGNORE_BEGIN = "# >>> harness (generated runtime — never commit) >>>"
_GITIGNORE_END = "# <<< harness <<<"
_GITIGNORE_PATTERNS = (
    "harness/state/",
    "harness/standards/.snapshots/",
    "harness/e2e/RUN-LOG.md",
)


def _write_gitignore(target_root, result, dry_run, no_track=False):
    """Ensure the target's .gitignore carries a managed harness block so the
    runtime state the harness writes never lands in the deployer's git. Additive
    and idempotent: a user .gitignore is preserved and the block is written once.
    With ``no_track``, ALSO ignore the whole harness/ tree — the harness runs but
    is never committed into the adopter's product git (re-track by dropping
    --no-track and removing the line)."""
    path = target_root / ".gitignore"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    new = existing
    if _GITIGNORE_BEGIN not in new:
        block = "\n".join([_GITIGNORE_BEGIN, *_GITIGNORE_PATTERNS, _GITIGNORE_END])
        sep = "" if not new or new.endswith("\n") else "\n"
        new = new + sep + block + "\n"
        result["actions"].append("add harness block to .gitignore")
    if no_track and "harness/" not in new.splitlines():
        sep = "" if not new or new.endswith("\n") else "\n"
        new = new + sep + "harness/\n"
        result["actions"].append(
            "gitignore harness/ (--no-track: harness present but not committed)")
    if new != existing and not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new, encoding="utf-8")


_CLAUDE_BEGIN = "<!-- >>> harness onboarding (generated; edits between markers are overwritten on reinstall) >>> -->"
_CLAUDE_END = "<!-- <<< harness <<< -->"


def _claude_md_block() -> str:
    """The self-loading onboarding block: what the harness is, how to drive it,
    where the shared rules live. Kept short — it is a pointer, not a manual."""
    return "\n".join([
        _CLAUDE_BEGIN,
        "",
        "## SDLC harness",
        "",
        "This repo runs a file-based **SDLC harness** for Claude Code, vendored "
        "self-contained under `harness/`.",
        "",
        "- **Skills** — drive the workflow with `/hs:<name>` (e.g. `/hs:plan`, "
        "`/hs:cook`, `/hs:test`, `/hs:ship`, `/hs:review-pr`). `/hs-meta:find-skills` "
        "lists the full catalog.",
        "- **Rules** — shared conventions load on demand from `harness/rules/` "
        "(routing in this file's project section, or ask a skill).",
        "- **Hooks** — gates/telemetry are wired in `.claude/settings.json`; "
        "config knobs live in `harness/data/*.yaml` and `harness/hooks/*.yaml`. "
        "Run `/hs:setup` to configure posture (voice, guard, reviewers).",
        "- **State** — runtime telemetry/state is written under `harness/state/` "
        "(gitignored; never commit it).",
        "",
        _CLAUDE_END,
    ])


def _write_claude_md(target_root, result, dry_run):
    """Inject the onboarding block into the target's CLAUDE.md. Unlike the
    .gitignore block (skip-if-present), this REPLACES between markers so a
    version bump refreshes a stale block; prose OUTSIDE the markers is always
    preserved, and a no-change rewrite is skipped (idempotent)."""
    path = target_root / "CLAUDE.md"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    block = _claude_md_block()
    b, e = existing.find(_CLAUDE_BEGIN), existing.find(_CLAUDE_END)
    if b != -1 and e != -1 and b < e:
        # well-formed marker pair → replace between them
        new = existing[:b] + block + existing[e + len(_CLAUDE_END):]
    else:
        sep = "" if not existing or existing.endswith("\n") else "\n"
        lead = "\n" if existing else ""
        new = existing + sep + lead + block + "\n"
    if new == existing:
        return  # already current — nothing to do (idempotent)
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new, encoding="utf-8")
    result["actions"].append("write harness onboarding block to CLAUDE.md")


def _check_standards(target_root, result):
    base = target_root / "harness" / "standards"
    maxloc = _standards_maxloc()
    for name in ("code-standards.md", "system-architecture.md"):
        p = base / name
        if not p.is_file() or len(p.read_text(encoding="utf-8").strip()) < 40:
            result["warnings"].append(
                "standards/%s missing or thin — author it (run "
                "harness/scripts/scaffold_standards.py --type %s for a TBD "
                "skeleton, or load your org's via symlink/copy into "
                "harness/standards/) before relying on standards-aware skills; "
                "the installer never fabricates them"
                % (name, name[:-3]))
            continue
        loc = p.read_text(encoding="utf-8").count("\n") + 1
        if loc > maxloc:
            result["warnings"].append(
                "standards/%s is %d lines (> %d) — many skills load it, so a "
                "long file costs tokens and is easy to skim past; consider "
                "trimming or splitting it (advisory, set HARNESS_STANDARDS_MAXLOC "
                "to tune)" % (name, loc, maxloc))


def _final_verify(target_root, strict, result):
    for rel, prob in verify_install.prepush_copy_warnings(target_root):
        result["warnings"].append("%s: %s" % (rel, prob))
    # Localization applies to integrity hash drift only; hook-registration
    # co-presence defects stay hard (a dangling wire is a bug, not config).
    hard, localized = verify_install.split_localized(
        verify_install.verify(target_root))
    hard += verify_install.hook_registration_problems(target_root)
    hard += verify_install.component_file_problems(target_root)
    hard += verify_install.plugin_presence_problems(target_root)
    for rel, prob in localized:
        result["warnings"].append(
            "%s: %s (deployer-localized — expected to differ from the "
            "shipped baseline)" % (rel, prob))
    result["problems"].extend(hard)
    if hard and strict:
        result["ok"] = False


def _uninstall_settings(target_root, local, result, dry_run):
    path = _settings_path(target_root, local)
    if not path.is_file():
        result["warnings"].append("no %s to clean" % path.name)
        return
    settings = _read_json(path)
    stripped = strip_harness_hooks(settings.get("hooks", {}))
    if stripped:
        settings["hooks"] = stripped
    else:
        settings.pop("hooks", None)
    _write_settings(path, settings, dry_run)
    result["actions"].append(
        "remove harness hook entries from %s" % path.name)


def _uninstall_prepush(target_root, result, dry_run):
    hooks_dir = target_root / ".git" / "hooks"
    dst = hooks_dir / "pre-push"
    bak = hooks_dir / "pre-push.bak"
    if not dst.exists():
        return
    if bak.exists():
        if not dry_run:
            shutil.copy2(bak, dst)
            bak.unlink()
        result["actions"].append("restore pre-push from pre-push.bak")
    else:
        if not dry_run:
            dst.unlink()
        result["actions"].append("remove harness pre-push hook")


# --- orchestrator --------------------------------------------------------


def _resolve_policy_components(source_root) -> str:
    """The default --components value when none was given: honor the shipped
    component-policy (default-only-hs). Returns "all" only when the policy has no
    deviations, else a CSV of the policy-enabled components; "all" on any error
    (fail-safe to the historical behavior rather than silently disabling)."""
    try:
        sys.path.insert(0, str(Path(source_root) / "harness" / "scripts"))
        import component_config as cc
        comps = cc.load_components(
            Path(source_root) / "harness" / "data" / "components.yaml")
        defaults = cc.resolved_selection(
            comps,
            cc.load_policy(Path(source_root) / "harness" / "data" / "component-policy.yaml"))
        enabled = sorted(c for c, on in defaults.items() if on)
        if len(enabled) == len(defaults):
            return "all"
        return ",".join(enabled)
    except Exception:  # noqa: BLE001 — no policy/map -> historical ship-all
        return "all"


def install(source_root, target_root, *, dry_run=False, local=False,
            uninstall=False, reviewers=None, strict=False,
            no_track=False, components=None,
            statusline=False, statusline_home=None,
            cli=False, cli_bindir=None) -> dict:
    """Run the full install (or uninstall) and return a result dict:
    {source_is_target, actions, skipped_events, warnings, problems, ok}.

    `components` selects optional components: a CSV of names, "all", "" (none), or
    None. None falls back to the shipped component-policy default (default-only-hs:
    the themed plugin groups ship OFF) rather than force-enabling everything."""
    source_root = Path(source_root).resolve()
    target_root = Path(target_root).resolve()
    if components is None:
        components = _resolve_policy_components(source_root)
    result = {
        "source_is_target": source_root == target_root,
        "actions": [], "skipped_events": [], "warnings": [],
        "problems": [], "ok": True,
    }

    if uninstall:
        _uninstall_settings(target_root, local, result, dry_run)
        _uninstall_prepush(target_root, result, dry_run)
        return result

    registration = load_registration(source_root)
    if result["source_is_target"]:
        result["actions"].append(
            "source == target: skip tree copy (dogfood no-op)")
    else:
        result["actions"].append(
            _copy_tree(source_root, target_root, dry_run))
    _wire_settings(target_root, registration, local, result, dry_run)
    if not result["source_is_target"]:
        # a dogfood install must not project onto the source's own hand-authored
        # harness-hooks.yaml (the live gate config) — selection is a deploy step.
        _apply_components(target_root, components, result, dry_run)
        # wire the plugin marketplace + enabledPlugins into the same settings
        # file the hooks went to (skipped on dogfood for the same reason).
        _wire_plugins(target_root, components, local, result, dry_run)
        if statusline:
            _wire_statusline(source_root, target_root, local, result, dry_run,
                             statusline_home)
        if cli:
            _wire_cli(source_root, target_root, result, dry_run, cli_bindir)
    _install_prepush(source_root, target_root, result, dry_run)
    _write_roster(target_root, source_root, reviewers, result, dry_run,
                  no_track=no_track)
    if not result["source_is_target"]:
        # a dogfood (source==target) install must not append to the source's
        # own .gitignore / CLAUDE.md — they are hand-authored here.
        _write_gitignore(target_root, result, dry_run, no_track=no_track)
        _write_claude_md(target_root, result, dry_run)
    _check_standards(target_root, result)
    if not dry_run:
        _final_verify(target_root, strict, result)
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default=".",
                    help="target repo root to install into (default: cwd)")
    ap.add_argument("--source", default=str(_HERE.parent.parent),
                    help="source harness tree (default: this installer's repo)")
    ap.add_argument("--reviewers", default=None,
                    help="comma-separated reviewer emails for the roster")
    ap.add_argument("--local", action="store_true",
                    help="wire into settings.local.json instead of settings.json")
    ap.add_argument("--dry-run", action="store_true",
                    help="plan the writes, change nothing")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if the final verify reports drift")
    ap.add_argument("--non-interactive", "--yes", dest="non_interactive",
                    action="store_true",
                    help="never prompt, even on a TTY (the CI/automation path); "
                         "uses --reviewers if given, otherwise an empty roster")
    ap.add_argument("--uninstall", action="store_true",
                    help="reverse the settings + pre-push edits "
                         "(harness/ is left in place; delete it to fully remove)")
    ap.add_argument("--no-track", dest="no_track", action="store_true",
                    help="install a running harness but gitignore harness/ so it "
                         "is never committed into the target's product git "
                         "(roster localization is skipped — the gate needs "
                         "harness/ tracked to be tamper-visible)")
    ap.add_argument("--components", default=None,
                    help="which optional components to ENABLE: 'all' (default) "
                         "or a CSV (e.g. rbac,decision-capture). All components "
                         "ship + wire regardless; deselected ones are only "
                         "runtime-disabled (enabled:false). Omitted on a TTY → "
                         "interactive prompt; omitted otherwise → 'all'.")
    ap.add_argument("--statusline", action="store_true",
                    help="opt in to the ccstatusline terminal status bar: wire a "
                         "statusLine block into settings.json and copy a default "
                         "ccstatusline config into ~/.config (both no-clobber). "
                         "Omitted on a TTY → interactive prompt; omitted "
                         "otherwise → off.")
    ap.add_argument("--cli", action="store_true",
                    help="opt in to the on-PATH `hs-cli` launcher: symlink "
                         "~/.local/bin/hs-cli at the shipped wrapper (POSIX; "
                         "Windows prints a PATH hint), no-clobber. Omitted on a "
                         "TTY → interactive prompt; omitted otherwise → off.")
    args = ap.parse_args(argv)

    source_root = Path(args.source).resolve()
    target_root = Path(args.target).resolve()

    reviewers = None
    if args.reviewers is not None:
        reviewers = args.reviewers.split(",")
    elif (not args.non_interactive and not args.uninstall and not args.dry_run
          and source_root != target_root and _stdin_is_tty()):
        print("Installing the harness into: %s" % target_root)
        print("  writes: harness/ tree, .claude/settings.json (hook wiring, "
              "merged), .git/hooks/pre-push (transport gate), "
              "harness/data/team.yaml (roster)")
        reviewers = _prompt_reviewers(_git_user_email())

    # Resolve the component selection. An explicit --components always wins.
    # On an interactive install we prompt (seeded from the shipped policy so the
    # themed groups read as opt-in). Otherwise we leave it None and install()
    # falls back to the component-policy default (default-only-hs) — never force-all.
    components_arg = args.components
    if (components_arg is None and not args.non_interactive and not args.uninstall
            and not args.dry_run and source_root != target_root and _stdin_is_tty()):
        comps_default, defaults = {}, {}
        try:
            sys.path.insert(0, str(source_root / "harness" / "scripts"))
            import component_config as cc
            comps_default = cc.load_components(
                source_root / "harness" / "data" / "components.yaml")
            defaults = cc.resolved_selection(
                comps_default,
                cc.load_policy(source_root / "harness" / "data" / "component-policy.yaml"))
        except Exception:  # noqa: BLE001 — no components map -> nothing to prompt
            comps_default, defaults = {}, {}
        if comps_default:
            components_arg = _prompt_components(sorted(comps_default), defaults)

    # ccstatusline is opt-in. An explicit --statusline always wins; on an
    # interactive install we ask once; otherwise it stays off.
    statusline = args.statusline
    if (not statusline and not args.non_interactive and not args.uninstall
            and not args.dry_run and source_root != target_root
            and _stdin_is_tty()):
        statusline = _prompt_statusline()

    # the on-PATH hs-cli launcher is opt-in, same cadence as statusline.
    cli = args.cli
    if (not cli and not args.non_interactive and not args.uninstall
            and not args.dry_run and source_root != target_root
            and _stdin_is_tty()):
        cli = _prompt_cli()

    try:
        result = install(source_root, target_root, dry_run=args.dry_run,
                         local=args.local, uninstall=args.uninstall,
                         reviewers=reviewers, strict=args.strict,
                         no_track=args.no_track, components=components_arg,
                         statusline=statusline, cli=cli)
    except InstallError as e:
        sys.stderr.write("ERROR %s\n" % e)
        return 1

    head = "PLAN (dry-run)" if args.dry_run else "INSTALL"
    if args.uninstall:
        head = "UNINSTALL"
    print("== %s == target: %s" % (head, target_root))
    for a in result["actions"]:
        print("  - %s" % a)
    for w in result["warnings"]:
        sys.stderr.write("WARN %s\n" % w)
    for rel, prob in result["problems"]:
        sys.stderr.write("DRIFT %s: %s\n" % (rel, prob))
    if result["problems"]:
        sys.stderr.write("verify: %d file(s) drifted\n" % len(result["problems"]))
    else:
        print("verify: clean" if not args.dry_run and not args.uninstall else "done")

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
