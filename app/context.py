"""Brute-force repo context builder: dump the entire repo into one string."""

import os
import subprocess
from pathlib import Path

# Extensions we consider "code" — everything else is skipped
CODE_EXTENSIONS = {
    ".py", ".yaml", ".yml", ".md", ".json", ".sh", ".bash",
    ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
    ".toml", ".cfg", ".ini", ".txt", ".html", ".css", ".sql",
    ".rb", ".c", ".cpp", ".h", ".hpp", ".swift", ".kt",
    ".dockerfile", ".tf", ".hcl", ".proto",
}

# Directories to always skip
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".tox", ".mypy_cache"}


def get_git_diff(repo_path: str = ".") -> str:
    """Get the current unstaged + staged diff."""
    # Staged changes
    staged = subprocess.run(
        ["git", "diff", "--cached"],
        cwd=repo_path, capture_output=True, text=True,
    ).stdout

    # Unstaged changes
    unstaged = subprocess.run(
        ["git", "diff"],
        cwd=repo_path, capture_output=True, text=True,
    ).stdout

    parts = []
    if staged:
        parts.append(staged)
    if unstaged:
        parts.append(unstaged)
    return "\n".join(parts)


def get_whole_repo_context(repo_path: str = ".") -> str:
    """Pack the entire repo into one big string. No optimization, pure brute force.

    Skips .git, __pycache__, node_modules, and binary files.
    """
    context_parts = []

    for root, dirs, files in os.walk(repo_path):
        # Prune skipped directories in-place
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for filename in sorted(files):
            ext = Path(filename).suffix.lower()
            # Also include extensionless files like Dockerfile, Makefile
            if ext not in CODE_EXTENSIONS and ext != "":
                continue

            file_path = Path(root) / filename
            rel_path = file_path.relative_to(repo_path)

            try:
                content = file_path.read_text(encoding="utf-8")
                context_parts.append(f"--- File: {rel_path} ---\n{content}")
            except (UnicodeDecodeError, PermissionError):
                pass  # binary or unreadable — skip silently

    return "\n\n".join(context_parts)
