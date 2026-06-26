#!/usr/bin/env python3
"""apply_frontmatter.py — additive SKILL.md frontmatter rollout (idempotent).

Fills the schema's gap fields (category, license, keywords, when_to_use) on skills
that lack them, WITHOUT overwriting anything already authored and WITHOUT touching
allowed-tools (restricting tools is a breakage risk handled deliberately, not in bulk)
or fabricating argument-hint (unreliable to derive). Derived values come from the
skill's own name + description — no invented content.

Insertion is textual (new lines after the `description:` line), so an existing
`metadata:` block and the exact formatting survive untouched. Running twice is a no-op.

Usage:
    python3 harness/scripts/apply_frontmatter.py [--root .] [--dry-run]
"""

import argparse
import re
import sys
from pathlib import Path

# Native group (decomposition-map value) -> category label. Spine "hs" reads as "core".
GROUP_TO_CATEGORY = {
    "hs": "core", "flow": "flow", "think": "think", "research": "research",
    "create": "create", "mem": "mem", "meta": "meta",
}
# ck-port plugin dir -> category label (for the few ck-port skills missing one).
PLUGIN_TO_CATEGORY = {
    "hs-ai": "ai-ml", "hs-devops": "devops", "hs-stack": "stack",
    "hs-uiux": "ui-ux", "hs-integrations": "integrations",
    "hs-extra": "extra", "hs-viz": "visualization",
}

_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "for", "from", "has",
    "have", "if", "in", "into", "is", "it", "its", "of", "on", "or", "so", "the",
    "to", "up", "use", "via", "vs", "was", "we", "when", "with", "you", "your",
    "this", "that", "via", "per", "each", "any", "all", "not", "but", "out",
})

_DESC_LINE_RE = re.compile(r"(?m)^description:\s*.+$")
_NAME_LINE_RE = re.compile(r"(?m)^name:\s*.+$")
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def derive_keywords(name, description, limit=6):
    """Salient lowercase keywords from the skill's own name + description."""
    base = name.split(":")[-1] if ":" in name else name
    words = re.findall(r"[A-Za-z][A-Za-z0-9+-]{1,}", "%s %s" % (base, description))
    out = []
    for w in words:
        lw = w.lower()
        if lw in _STOPWORDS or len(lw) < 3:
            continue
        if lw not in out:
            out.append(lw)
        if len(out) >= limit:
            break
    return out


def derive_when_to_use(description):
    """Prefer an explicit 'Use ...' trigger clause; else the first sentence."""
    m = re.search(r"Use\s+[^.]*\.", description)
    if m:
        return m.group(0).strip()
    first = description.strip().split(".")[0].strip()
    return (first + ".") if first else description.strip()


def compute_missing(fm, *, is_native, group, plugin):
    """The fields to ADD — only those absent from `fm`. Never allowed-tools."""
    add = {}
    if "category" not in fm:
        add["category"] = (GROUP_TO_CATEGORY.get(group, group) if is_native
                           else PLUGIN_TO_CATEGORY.get(plugin, (plugin or "").replace("hs-", "")))
    if "license" not in fm:
        add["license"] = "AGPL-3.0" if is_native else "MIT"
    name = fm.get("name", "")
    desc = fm.get("description", "") or ""
    if "keywords" not in fm:
        add["keywords"] = derive_keywords(name, desc)
    if "when_to_use" not in fm:
        add["when_to_use"] = derive_when_to_use(desc)
    return add


def _fmt_lines(add):
    """Render the add-dict as frontmatter lines, in a stable order."""
    order = ["category", "license", "keywords", "when_to_use"]
    lines = []
    for key in order:
        if key not in add:
            continue
        val = add[key]
        if isinstance(val, list):
            lines.append("%s: [%s]" % (key, ", ".join(val)))
        elif key in ("when_to_use",):
            esc = val.replace('"', '\\"')
            lines.append('%s: "%s"' % (key, esc))
        else:
            lines.append("%s: %s" % (key, val))
    return lines


def insert_after_description(text, add):
    """Insert the add-lines as TOP-LEVEL keys after the full description value.

    The description may be a folded/literal scalar (`>-`, `|`) spanning several
    indented continuation lines — inserting right after the `description:` line would
    split that scalar and corrupt the YAML. So advance past every continuation line
    (indented or blank) and insert just before the NEXT top-level key, keeping the new
    keys above any nested block (e.g. metadata:)."""
    lines = _fmt_lines(add)
    if not lines:
        return text
    m = _FM_RE.match(text)
    if not m:
        return text
    fm_lines = m.group(1).split("\n")

    anchor_i = None
    for i, ln in enumerate(fm_lines):
        if re.match(r"^description:", ln):
            anchor_i = i
            break
    if anchor_i is None:
        for i, ln in enumerate(fm_lines):
            if re.match(r"^name:", ln):
                anchor_i = i
                break
    if anchor_i is None:
        return text

    insert_i = anchor_i + 1
    while insert_i < len(fm_lines):
        ln = fm_lines[insert_i]
        if ln == "" or ln.startswith((" ", "\t")):
            insert_i += 1
        else:
            break

    new_fm = "\n".join(fm_lines[:insert_i] + lines + fm_lines[insert_i:])
    return text[:m.start(1)] + new_fm + text[m.end(1):]


def _parse_fm(text):
    m = _FM_RE.match(text)
    if not m:
        return None
    try:
        import yaml
        data = yaml.safe_load(m.group(1))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def apply_to_file(path, *, is_native, group, plugin, dry_run=False):
    """Add missing fields to one SKILL.md. Returns the dict of fields added ({} = no-op)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    fm = _parse_fm(text)
    if fm is None:
        return {}
    add = compute_missing(fm, is_native=is_native, group=group, plugin=plugin)
    if not add:
        return {}
    if not dry_run:
        path.write_text(insert_after_description(text, add), encoding="utf-8")
    return add


def _load_native_map(root):
    """basename -> group, from decomposition-map.yaml (the native/core skills)."""
    cfg = Path(root) / "harness" / "data" / "decomposition-map.yaml"
    try:
        import yaml
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        return dict(data.get("skills") or {})
    except Exception:
        return {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    native = _load_native_map(root)
    changed = 0
    for skill_md in sorted((root / "harness" / "plugins").rglob("SKILL.md")):
        parts = skill_md.relative_to(root / "harness" / "plugins").parts
        plugin = parts[0]
        basename = skill_md.parent.name
        is_native = basename in native
        group = native.get(basename)
        add = apply_to_file(skill_md, is_native=is_native, group=group,
                            plugin=plugin, dry_run=args.dry_run)
        if add:
            changed += 1
            print("%s += %s" % (skill_md.relative_to(root), sorted(add)))
    print("apply_frontmatter: %d skill(s) %s"
          % (changed, "would change" if args.dry_run else "changed"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
