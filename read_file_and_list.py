from pathlib import Path
from datetime import datetime

# =========================
# CONFIG
# =========================

ROOT_DIR = Path(".").resolve()
OUTPUT_FILE = ROOT_DIR / "project_context.txt"

MAX_FILE_SIZE_MB = 2

EXCLUDE_DIRS = {
    "OpenHands",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    ".idea",
    ".vscode",
}

EXCLUDE_FILES = {
    "project_context.txt",
    "dump_project_context.py",
    ".env",
    ".env.local",
    ".env.production",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
    ".pdf", ".zip", ".rar", ".7z",
    ".exe", ".dll", ".so", ".bin",
    ".mp4", ".mp3", ".wav",
    ".pkl", ".pt", ".onnx",
}

TEXT_EXTENSIONS = {
    ".py", ".txt", ".md", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg",
    ".html", ".css", ".js", ".ts",
    ".bat", ".sh", ".ps1",
    ".log",
    ".gitignore",
}


# =========================
# HELPER FUNCTIONS
# =========================

def should_exclude_path(path: Path) -> bool:
    parts = set(path.parts)

    if parts & EXCLUDE_DIRS:
        return True

    if path.name in EXCLUDE_FILES:
        return True

    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True

    return False


def is_probably_text_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True

    if path.name in TEXT_EXTENSIONS:
        return True

    return False


def safe_read_text(path: Path) -> str:
    max_size = MAX_FILE_SIZE_MB * 1024 * 1024

    try:
        if path.stat().st_size > max_size:
            return f"[SKIPPED: file too large > {MAX_FILE_SIZE_MB}MB]"

        if not is_probably_text_file(path):
            return "[SKIPPED: not recognized as text file]"

        return path.read_text(encoding="utf-8", errors="replace")

    except Exception as e:
        return f"[ERROR READING FILE: {e}]"


def build_tree(root: Path) -> str:
    lines = []

    def walk(current: Path, prefix: str = ""):
        items = sorted(
            [p for p in current.iterdir() if not should_exclude_path(p)],
            key=lambda p: (p.is_file(), p.name.lower())
        )

        for index, item in enumerate(items):
            connector = "└── " if index == len(items) - 1 else "├── "
            lines.append(prefix + connector + item.name)

            if item.is_dir():
                extension = "    " if index == len(items) - 1 else "│   "
                walk(item, prefix + extension)

    lines.append(root.name + "/")
    walk(root)

    return "\n".join(lines)


def collect_files(root: Path):
    files = []

    for path in root.rglob("*"):
        if path.is_file() and not should_exclude_path(path):
            files.append(path)

    return sorted(files, key=lambda p: str(p.relative_to(root)).lower())


# =========================
# MAIN
# =========================

def main():
    tree_text = build_tree(ROOT_DIR)
    files = collect_files(ROOT_DIR)

    with OUTPUT_FILE.open("w", encoding="utf-8") as out:
        out.write("# PROJECT CONTEXT DUMP\n\n")
        out.write(f"Generated at: {datetime.now().isoformat(timespec='seconds')}\n")
        out.write(f"Root directory: {ROOT_DIR}\n\n")

        out.write("=" * 80 + "\n")
        out.write("PROJECT FILE TREE\n")
        out.write("=" * 80 + "\n\n")
        out.write(tree_text)
        out.write("\n\n")

        out.write("=" * 80 + "\n")
        out.write("FILES WITH CONTENT\n")
        out.write("=" * 80 + "\n\n")

        for file_path in files:
            relative_path = file_path.relative_to(ROOT_DIR)
            content = safe_read_text(file_path)

            out.write("\n")
            out.write("=" * 80 + "\n")
            out.write(f"FILE: {relative_path}\n")
            out.write("=" * 80 + "\n\n")
            out.write(content)
            out.write("\n\n")

    print(f"Done. Project context saved to:")
    print(OUTPUT_FILE)


if __name__ == "__main__":
    main()