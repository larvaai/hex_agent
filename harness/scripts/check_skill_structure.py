"""check_skill_structure.py — structural + content lint for hs:* skills.

Enforces the thin-core discipline the harness documents for skills: a SKILL.md stays
small so the always-loaded core is cheap, and detail is pushed one level deep into
references/ that themselves stay bounded. Three existing validators cover other
concerns (catalog.tier_problems for compliance-tier; the dot-claude tree for
frontmatter/cross-refs) — this one owns the size + description-shape gap none of them
check, plus the WRITE-time content integrity the skill_quality_gate hook enforces.

Findings by severity:
  - HARD: oversized SKILL.md / reference (thin-core), a dangling local reference the
    body points at (broken-reference-link), and a machine birth-marker leaking into
    prose (birth-marker-leak).
  - ADVISORY: description shape, an orphan reference no body links (orphan-reference),
    and tight email / US-SSN PII shapes (pii-possible).

Contract (mirrors check_report_language):
  - Advisory by default: exits 0, emits a per-skill verdict on stdout, never mutates.
  - With --strict any HARD finding exits non-zero. CI runs --strict only on skills
    CHANGED vs main, so existing skills are grandfathered until they are next touched.
  - write_gate_reason() is the compliance-core for the PostToolUse skill_quality_gate
    hook: it blocks ONLY on the HARD content rules (dangling reference / birth-marker),
    leaving size to CI and shape/PII advisory.

Input is a skill directory (one with a SKILL.md) or a root that holds skill dirs;
a root is swept. A path with no SKILL.md is inert (skipped, exit 0).
"""
import argparse
import json
import re
import sys
from pathlib import Path

# Thin-core thresholds. The SKILL.md ceiling matches the documented standard; the
# reference ceiling bounds one-level-deep detail. Both live here as the single knob.
MAX_SKILL_LINES = 150
MAX_REF_LINES = 300

# Description-shape advisory bounds.
DESC_MIN = 30
DESC_MAX = 512
_TRIGGER_RE = re.compile(r"\bUse (?:when|for|to)\b", re.I)

_DESC_RE = re.compile(r"(?m)^description:\s*(.+?)\s*$")

# A bare local reference the body points at: references/scripts/assets + a filename.
# The negative-lookbehind skips an absolute-path mention (harness/.../references/x.md
# is preceded by `/`), so only a repo-local relative ref is resolved against the skill
# dir — exactly what a reader would click. The file part is case-blind (A-Za-z): a
# capitalized name or uppercase extension (references/Detail.md, references/x.MD) is the
# same dead link to a reader, so it must not slip past on case alone.
_LOCAL_REF_RE = re.compile(r"(?<![/\w])(references|scripts|assets)/([A-Za-z0-9_-]+\.[A-Za-z]+)")

# Birth-marker leak — deliberately tightened to ONLY machine-generated provenance SHAPES. It is
# deliberately NOT `success rate` or a bare `\d+ episode`: those match legitimate
# documentation prose (a belief-store SKILL.md reads "reinforced from 3 episodes"),
# which would make the very phases that document the belief store self-trip this gate.
# "generated from N episodes/runs/samples" requires the literal "generated from", so
# "reinforced from 3 episodes" does not match.
_BIRTH_MARKER_RE = re.compile(
    r"auto-drafted|generated_on|generated_by|generated from \d+ (?:episodes?|runs?|samples?)",
    re.IGNORECASE)

# Tight PII shapes (advisory): an email and a US SSN. Phone is deliberately
# dropped — its loose shape false-matched timestamp slugs / SVG viewBox / ISO dates.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# The WRITE-time gate (skill_quality_gate hook) blocks ONLY these HARD content rules.
# Size stays a CI lint (a mid-edit oversize is not a write-time integrity failure) and
# shape/PII stay advisory.
_WRITE_GATE_RULES = ("broken-reference-link", "birth-marker-leak")

# Frontmatter contract (skill-schema.json). Loaded once; absence/parse-failure degrades
# to "no schema check" (fail-open) so a missing schema never blocks a write.
_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "skill-schema.json"
_JSON_TO_PY = {"string": str, "boolean": bool, "array": list,
               "object": dict, "number": (int, float), "integer": int}


def _load_skill_schema() -> dict:
    try:
        return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


_SKILL_SCHEMA = _load_skill_schema()


def _frontmatter(skill_md: Path) -> "dict | None":
    """The SKILL.md frontmatter as a dict, or None when absent/unparseable (fail-open)."""
    try:
        import yaml
    except Exception:
        return None
    text = skill_md.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return None
    try:
        data = yaml.safe_load(m.group(1))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _type_ok(value, schema_type) -> bool:
    """True if value matches a JSON-Schema type (string, or list-of-types union)."""
    types = schema_type if isinstance(schema_type, list) else [schema_type]
    for t in types:
        py = _JSON_TO_PY.get(t)
        if py is None:
            return True  # unknown type keyword -> do not penalize
        # bool is a subclass of int: keep them distinct so a boolean field is not
        # silently accepted as a number and vice-versa.
        if py is bool and isinstance(value, bool):
            return True
        if py is not bool and isinstance(value, py) and not isinstance(value, bool):
            return True
        if py is bool:
            continue
    return False


def _schema_findings(skill_md: Path) -> list:
    """Advisory findings from the frontmatter contract: required-present + known-field
    types. A MISSING OPTIONAL field is never a finding — that is rollout coverage, not a
    structural error — so the existing tree stays clean until the rollout fills it."""
    if not _SKILL_SCHEMA:
        return []
    fm = _frontmatter(skill_md)
    if fm is None:
        return []
    out = []
    for req in _SKILL_SCHEMA.get("required", []):
        val = fm.get(req)
        if val is None or (isinstance(val, str) and not val.strip()):
            out.append({"rule": "frontmatter-missing-required", "severity": "advisory",
                        "detail": "frontmatter is missing required field %r" % req})
    props = _SKILL_SCHEMA.get("properties", {})
    for key, spec in props.items():
        if key in fm and fm[key] is not None and "type" in spec:
            if not _type_ok(fm[key], spec["type"]):
                out.append({"rule": "frontmatter-bad-type", "severity": "advisory",
                            "detail": "frontmatter field %r should be %s" % (key, spec["type"])})
    return out


def _count_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="replace").splitlines())


def _body(skill_md: Path) -> str:
    """The SKILL.md body (everything after the leading frontmatter block), or the
    whole file when there is no frontmatter. Body-only is deliberate: a birth-marker
    or PII shape is a PROSE concern, so a `generated_on:` field inside frontmatter
    metadata is not a leak. Fail-soft: an unreadable file yields ""."""
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            after = text.find("\n", end + 1)
            return text[after + 1:] if after != -1 else ""
    return text


def _description(skill_md: Path) -> str:
    """The frontmatter description line, or "" when absent.

    The harness skills keep description on a single line; a multi-line YAML scalar is
    out of scope (none use it). Fail-soft: an unreadable file yields "".
    """
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    # Only look inside the leading frontmatter block.
    if text.startswith("---"):
        end = text.find("\n---", 3)
        head = text[:end] if end != -1 else text
    else:
        head = text
    m = _DESC_RE.search(head)
    return m.group(1).strip() if m else ""


def check_skill(skill_dir: str) -> dict:
    """Return a verdict dict for one skill directory.

    verdict: FAIL when any HARD finding is present, PASS_WITH_RISK when only advisory
    findings exist, PASS when clean. A directory without a SKILL.md is skipped.
    """
    d = Path(skill_dir)
    skill_md = d / "SKILL.md"
    if not skill_md.is_file():
        return {"tool": "check_skill_structure", "skill": d.name,
                "verdict": "PASS", "skipped": "no SKILL.md", "findings": []}

    findings = []

    # Size gate governs GUIDANCE: count the BODY (after frontmatter), not metadata.
    # Otherwise the schema frontmatter rollout would shrink every skill's body budget.
    n = len(_body(skill_md).splitlines())
    if n > MAX_SKILL_LINES:
        findings.append({"rule": "skill-md-too-long", "severity": "hard",
                         "detail": "SKILL.md body is %d lines (max %d) — split detail into references/"
                                   % (n, MAX_SKILL_LINES)})

    refs = d / "references"
    if refs.is_dir():
        for ref in sorted(refs.glob("*.md")):
            rn = _count_lines(ref)
            if rn > MAX_REF_LINES:
                findings.append({"rule": "reference-too-long", "severity": "hard",
                                 "detail": "references/%s is %d lines (max %d)"
                                           % (ref.name, rn, MAX_REF_LINES)})

    body = _body(skill_md)

    # dangling local reference (HARD): a references/scripts/assets path the body links
    # must resolve inside the skill dir. linked names are collected here so the orphan
    # pass below can tell an unlinked on-disk reference from a missing one.
    linked_refs = set()
    for m in _LOCAL_REF_RE.finditer(body):
        if m.group(1) == "references":
            linked_refs.add(m.group(2))
        if not (d / m.group(1) / m.group(2)).is_file():
            findings.append({"rule": "broken-reference-link", "severity": "hard",
                             "detail": "body links %s/%s which does not exist in the skill dir"
                                       % (m.group(1), m.group(2))})

    # birth-marker leak (HARD): a machine-generated provenance shape in prose.
    bm = _BIRTH_MARKER_RE.search(body)
    if bm:
        findings.append({"rule": "birth-marker-leak", "severity": "hard",
                         "detail": "body carries a generated-provenance marker %r — strip it"
                                   % bm.group(0)})

    # orphan reference (ADVISORY): a references/*.md file no body link points to.
    if refs.is_dir():
        on_disk = {p.name for p in refs.glob("*.md") if p.is_file()}
        for orphan in sorted(on_disk - linked_refs):
            findings.append({"rule": "orphan-reference", "severity": "advisory",
                             "detail": "references/%s is on disk but no body link points to it"
                                       % orphan})

    # PII (ADVISORY): tight email / US-SSN shapes in the body.
    if _EMAIL_RE.search(body):
        findings.append({"rule": "pii-possible", "severity": "advisory",
                         "detail": "body contains an email-shaped string"})
    if _SSN_RE.search(body):
        findings.append({"rule": "pii-possible", "severity": "advisory",
                         "detail": "body contains a US-SSN-shaped string"})

    desc = _description(skill_md)
    if not (DESC_MIN <= len(desc) <= DESC_MAX):
        findings.append({"rule": "description-length", "severity": "advisory",
                         "detail": "description is %d chars (want %d-%d)"
                                   % (len(desc), DESC_MIN, DESC_MAX)})
    if desc and not _TRIGGER_RE.search(desc):
        findings.append({"rule": "description-missing-trigger", "severity": "advisory",
                         "detail": 'description has no "Use when/for/to ..." trigger clause'})

    # frontmatter contract (skill-schema.json): required-present + known-field types.
    findings.extend(_schema_findings(skill_md))

    hard = any(f["severity"] == "hard" for f in findings)
    verdict = "FAIL" if hard else ("PASS_WITH_RISK" if findings else "PASS")
    return {"tool": "check_skill_structure", "skill": d.name,
            "verdict": verdict, "findings": findings}


def write_gate_reason(file_path) -> "str | None":
    """Compliance-core decision for the skill_quality_gate PostToolUse hook.

    None ⇒ allow; a string ⇒ block reason. Only a SKILL.md is gated, and only the HARD
    content rules (dangling reference / birth-marker leak) block at WRITE time — size
    stays a CI lint and shape/PII stay advisory (fail-open). check_skill is fail-soft,
    so an unreadable target produces no finding and passes.
    """
    p = Path(file_path)
    if p.name != "SKILL.md":
        return None
    result = check_skill(str(p.parent))
    hard = [f for f in result.get("findings", []) if f.get("rule") in _WRITE_GATE_RULES]
    if not hard:
        return None
    detail = "; ".join("%s — %s" % (f["rule"], f["detail"]) for f in hard)
    return "SKILL.md content gate at %s: %s" % (p, detail)


def _iter_skill_dirs(root: Path):
    """A root that directly holds a SKILL.md is one skill; otherwise its immediate
    children that hold a SKILL.md are the skills."""
    if (root / "SKILL.md").is_file():
        return [root]
    return sorted(c for c in root.iterdir() if c.is_dir() and (c / "SKILL.md").is_file())


def check_path(path: str) -> dict:
    root = Path(path)
    if not root.exists():
        return {"tool": "check_skill_structure", "verdict": "PASS",
                "skipped": "no such path: %s" % path, "skills": []}
    dirs = _iter_skill_dirs(root)
    if not dirs:
        return {"tool": "check_skill_structure", "verdict": "PASS",
                "skipped": "no SKILL.md under %s" % path, "skills": []}
    skills = [check_skill(str(d)) for d in dirs]
    hard = sum(len([f for f in s["findings"] if f["severity"] == "hard"]) for s in skills)
    advisory = sum(len([f for f in s["findings"] if f["severity"] == "advisory"]) for s in skills)
    return {
        "tool": "check_skill_structure",
        "verdict": "FAIL" if hard else ("PASS_WITH_RISK" if advisory else "PASS"),
        "hard": hard,
        "advisory": advisory,
        "skills": skills,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Advisory structural lint for hs:* skills.")
    ap.add_argument("path", help="a skill directory, or a root holding skill dirs")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero when a HARD finding is present (CI runs this on changed skills)")
    args = ap.parse_args(argv)
    result = check_path(args.path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if (args.strict and result.get("hard")) else 0


if __name__ == "__main__":
    sys.exit(main())
