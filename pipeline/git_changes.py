"""Git changed-file discovery for scoping security scans.

For large hybrid projects the IaC security gate should scan only the files that
changed instead of the whole tree.  This module computes the set of changed
files under a given directory relative to a base git ref (committed diff,
unstaged working-tree changes, and untracked files), filtered by extension.

Design contract:
    changed_files(path, base_ref=...) -> list[Path] | None

    Returns a list of absolute Paths to changed files under *path*.
    Returns None when change detection is not possible (path is not inside a git
    repository, git is unavailable, or the base ref cannot be resolved).  A None
    result is the caller's signal to fall back to scanning every file — never to
    skip scanning entirely.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def _git(repo: Path, *args: str, timeout: int = 30) -> subprocess.CompletedProcess | None:
    """Run a git command inside *repo*; return the completed process or None."""
    git = shutil.which("git")
    if not git:
        return None
    try:
        return subprocess.run(
            [git, "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception:
        return None


def _repo_root(path: Path) -> Path | None:
    proc = _git(path, "rev-parse", "--show-toplevel")
    if proc is None or proc.returncode != 0:
        return None
    root = proc.stdout.strip()
    return Path(root) if root else None


def _ref_exists(repo: Path, base_ref: str) -> bool:
    proc = _git(repo, "rev-parse", "--verify", "--quiet", base_ref)
    return proc is not None and proc.returncode == 0


def changed_files(
    path: str | Path,
    *,
    base_ref: str = "HEAD",
    exts: tuple[str, ...] | None = None,
    include_untracked: bool = True,
) -> list[Path] | None:
    """Return changed files under *path*, or None when detection is impossible.

    *base_ref*:
        Git ref to diff against (e.g. "HEAD", "HEAD~1", "origin/main").
        Committed differences between *base_ref* and the working tree are
        included, along with unstaged changes and (optionally) untracked files.
    *exts*:
        Lowercase extensions to keep (e.g. (".yml", ".yaml")).  None keeps all.
    *include_untracked*:
        When True, untracked files (new playbooks not yet committed) are included.
    """
    target = Path(path).resolve()
    if not target.exists():
        return None

    repo = _repo_root(target)
    if repo is None:
        return None
    repo = repo.resolve()

    rel_targets: set[str] = set()

    # 1. Committed diff base_ref..working-tree (only when the ref resolves).
    if _ref_exists(repo, base_ref):
        proc = _git(repo, "diff", "--name-only", base_ref, "--")
        if proc is not None and proc.returncode == 0:
            rel_targets.update(_nonempty_lines(proc.stdout))

    # 2. Unstaged + staged changes relative to HEAD (covers dirty working tree).
    proc = _git(repo, "diff", "--name-only", "HEAD", "--")
    if proc is not None and proc.returncode == 0:
        rel_targets.update(_nonempty_lines(proc.stdout))

    # 3. Untracked files (new, never committed).
    if include_untracked:
        proc = _git(repo, "ls-files", "--others", "--exclude-standard")
        if proc is not None and proc.returncode == 0:
            rel_targets.update(_nonempty_lines(proc.stdout))

    norm_exts = tuple(e.lower() for e in exts) if exts else None

    results: list[Path] = []
    for rel in sorted(rel_targets):
        abs_path = (repo / rel).resolve()
        # Keep only files under the requested directory that still exist.
        if not _is_within(abs_path, target):
            continue
        if not abs_path.is_file():
            continue
        if norm_exts is not None and abs_path.suffix.lower() not in norm_exts:
            continue
        results.append(abs_path)

    return results


def _nonempty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False
