"""Repo context builder: git-aware file extraction with noise filtering."""

import subprocess
from pathlib import Path

# Files that are noise for code review even if git-tracked
IGNORED_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Pipfile.lock", "Cargo.lock", ".DS_Store",
}

# Extensions with no code review value
IGNORED_EXTENSIONS = {
    # binaries
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".exe", ".bin", ".whl", ".egg",
    # media
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".ttf", ".woff", ".woff2", ".mp3", ".mp4", ".wav",
    # archives & data
    ".pdf", ".zip", ".tar", ".gz", ".rar", ".7z",
    ".sqlite", ".sqlite3", ".db", ".jar",
}

# Skip files larger than this (prevents token explosion)
MAX_FILE_SIZE = 200 * 1024  # 200KB


def get_git_diff(repo_path: str = ".") -> str:
    """Get the current unstaged + staged diff."""
    try:
        staged = subprocess.run(
            ["git", "diff", "--cached"],
            cwd=repo_path, capture_output=True, text=True,
        )
        unstaged = subprocess.run(
            ["git", "diff"],
            cwd=repo_path, capture_output=True, text=True,
        )
    except FileNotFoundError:
        return ""

    parts = []
    if staged.stdout:
        parts.append(staged.stdout)
    if unstaged.stdout:
        parts.append(unstaged.stdout)
    return "\n".join(parts)


def get_whole_repo_context(repo_path: str = ".") -> str:
    """Extract repo context using git ls-files with noise filtering.

    Three layers of defense:
    1. git ls-files: only tracked files (inherits .gitignore)
    2. Extension + filename filter: skip binaries, media, lock files
    3. Size limit: skip files > 200KB
    """
    repo_dir = Path(repo_path).resolve()

    # Use git to get tracked files (respects .gitignore)
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=str(repo_dir),
            capture_output=True, text=True, check=True,
        )
        tracked_files = result.stdout.splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""

    context_parts = []

    for rel_path in sorted(tracked_files):
        file_path = repo_dir / rel_path

        # Filter: extension
        if file_path.suffix.lower() in IGNORED_EXTENSIONS:
            continue

        # Filter: noise files
        if file_path.name in IGNORED_FILES:
            continue

        if not file_path.is_file():
            continue

        # Filter: size
        try:
            size = file_path.stat().st_size
            if size > MAX_FILE_SIZE:
                context_parts.append(f"--- {rel_path} [SKIPPED: >{MAX_FILE_SIZE // 1024}KB] ---")
                continue

            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if not content.strip():
                continue

            context_parts.append(f"--- {rel_path} ---\n{content}")
        except (OSError, PermissionError):
            pass

    return "\n\n".join(context_parts)
