"""Reproducibility metadata for evaluation runs.

Every recorded run carries the commit, interpreter and external-tool versions it
was produced with, so a campaign result can be tied to an exact code state.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]

# Some tools (ansible-lint) colourise --version output even when piped.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

# (binary, args) pairs probed for a version string.
_TOOL_PROBES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cdk", ("--version",)),
    ("ansible-playbook", ("--version",)),
    ("ansible-lint", ("--version",)),
    ("checkov", ("--version",)),
    ("cfn-lint", ("--version",)),
    ("infracost", ("--version",)),
    ("bandit", ("--version",)),
    ("semgrep", ("--version",)),
)

_cached: dict[bool, dict[str, Any]] = {}


def _run(cmd: list[str], timeout: int = 20) -> str | None:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    out = (proc.stdout or proc.stderr).strip()
    if not out:
        return None
    return _ANSI.sub("", out.splitlines()[0]).strip()


def _git_state() -> dict[str, Any]:
    git = shutil.which("git")
    if not git:
        return {"commit": None, "dirty": None, "branch": None}
    commit = _run([git, "-C", str(ROOT_DIR), "rev-parse", "HEAD"])
    branch = _run([git, "-C", str(ROOT_DIR), "rev-parse", "--abbrev-ref", "HEAD"])
    status = _run([git, "-C", str(ROOT_DIR), "status", "--porcelain"])
    return {"commit": commit, "branch": branch, "dirty": bool(status)}


def _which(name: str) -> str | None:
    """Locate *name*, preferring the active venv's bin dir.

    Mirrors ``pipeline.ansible_pipeline._resolve_executable`` so the recorded
    versions are the ones the pipeline actually invokes, not whatever the
    ambient PATH happens to expose.
    """
    candidate = Path(sys.executable).parent / name
    if candidate.is_file():
        return str(candidate)
    return shutil.which(name)


def _tool_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name, args in _TOOL_PROBES:
        binary = _which(name)
        versions[name] = _run([binary, *args]) if binary else None
    return versions


def collect_provenance(include_tools: bool = True) -> dict[str, Any]:
    """Return commit/host/tool metadata, cached for the process lifetime."""
    cached = _cached.get(include_tools)
    if cached is not None:
        return cached
    data: dict[str, Any] = {
        "git": _git_state(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "hostname": platform.node(),
        "cwd": str(Path.cwd()),
        "aws_region": os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION"),
    }
    data["tools"] = _tool_versions() if include_tools else {}
    _cached[include_tools] = data
    return data
