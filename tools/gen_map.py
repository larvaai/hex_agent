"""Regenerate MAP.md from each module's first docstring line. Run: python tools/gen_map.py. Epic: tooling."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DENY = {"tests", "var", "tools", ".git", "__pycache__", ".venv", ".ruff_cache", ".pytest_cache", ".egg-info"}


def first_doc(path: Path) -> str:
    try:
        doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")))
    except Exception as exc:  # pragma: no cover
        return f"(parse error: {exc})"
    return doc.splitlines()[0].strip() if doc else "(thiếu module docstring — thêm 1 dòng + epic)"


def packages() -> list[str]:
    return [
        p.name
        for p in sorted(ROOT.iterdir())
        if p.is_dir() and p.name not in DENY and not p.name.endswith(".egg-info") and any(p.glob("*.py"))
    ]


def main() -> int:
    lines = [
        "# MAP — chỉ mục module (TỰ SINH bởi `tools/gen_map.py`)",
        "",
        "Mỗi module + một dòng mục đích + epic. **Chạy lại `python tools/gen_map.py`** sau khi thêm/đổi file.",
        "",
    ]
    for pkg in packages():
        lines += [f"## {pkg}/", "", "| module | mục đích |", "|---|---|"]
        for f in sorted((ROOT / pkg).glob("*.py")):
            if f.name == "__init__.py":
                continue
            lines.append(f"| `{pkg}/{f.name}` | {first_doc(f)} |")
        lines.append("")
    root_py = sorted(ROOT.glob("*.py"))
    if root_py:
        lines += ["## (root)", "", "| file | mục đích |", "|---|---|"]
        for f in root_py:
            lines.append(f"| `{f.name}` | {first_doc(f)} |")
        lines.append("")
    (ROOT / "MAP.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", ROOT / "MAP.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
