"""ansible-lint adapter for the IaC security gate.

Runs ansible-lint against a set of playbook / role files and normalises its
findings into the shared finding schema used by IaCSecurityGate so they can be
scored by the same risk engine as CloudFormation findings.

Status values (consistent with the other scanner adapters):
    "ok" | "skipped" | "not_installed" | "error"
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_SKIPPED_STATUS = "skipped"
_OK_STATUS = "ok"
_NOT_INSTALLED_STATUS = "not_installed"
_ERROR_STATUS = "error"

# ansible-lint codeclimate severities → internal severity levels.
_SEVERITY_MAP: dict[str, str] = {
    "blocker": "critical",
    "critical": "critical",
    "major": "high",
    "minor": "medium",
    "info": "low",
}


def _resolve_executable(name: str) -> str:
    """Return the absolute path to *name*, preferring the active venv's bin dir."""
    venv_bin = Path(sys.executable).parent
    candidate = venv_bin / name
    if candidate.is_file():
        return str(candidate)
    found = shutil.which(name)
    return found if found else name


def _normalise_severity(raw: str) -> str:
    return _SEVERITY_MAP.get(str(raw).strip().lower(), "medium")


def _parse_codeclimate(raw: str) -> list[dict[str, Any]]:
    """Parse ansible-lint ``-f json`` (codeclimate) output into findings."""
    findings: list[dict[str, Any]] = []
    text = raw.strip()
    if not text:
        return findings

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return findings

    if not isinstance(parsed, list):
        return findings

    for item in parsed:
        if not isinstance(item, dict):
            continue

        check_name = str(item.get("check_name", "")).strip()
        description = str(item.get("description", "")).strip()
        severity_raw = str(item.get("severity", "minor") or "minor")

        location = item.get("location") or {}
        path = str(location.get("path", "")) if isinstance(location, dict) else ""
        line = ""
        if isinstance(location, dict):
            lines = location.get("lines") or location.get("positions") or {}
            if isinstance(lines, dict):
                begin = lines.get("begin")
                if isinstance(begin, dict):
                    line = str(begin.get("line", ""))
                elif begin is not None:
                    line = str(begin)

        template_name = Path(path).name if path else "unknown"
        resource_id = f"{template_name}:{line}" if line else (template_name or "unknown")
        message = f"[{check_name}] {description}" if check_name else description

        findings.append(
            {
                "severity": _normalise_severity(severity_raw),
                "source": "ansible-lint",
                "message": message or "ansible-lint rule violation",
                "resource_id": resource_id,
                "template": template_name,
                # Use the rule id as the dedup category so the same rule on the
                # same file/line is never double-counted across re-runs.
                "category": check_name or "ansible_lint",
            }
        )

    return findings


def run_ansible_lint(
    files: list[Path],
    *,
    enabled: bool = True,
    project_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Run ansible-lint against *files* and return (findings, status).

    *files* is the explicit list of playbook / role YAML files to lint (typically
    scoped to git-changed files by the caller).  When empty, the scan is a no-op
    that returns an "ok" status with no findings.

    *project_dir* sets the working directory so ansible-lint resolves project
    config (``.ansible-lint``, ``ansible.cfg``) and role paths correctly.
    """
    if not enabled:
        return [], _SKIPPED_STATUS

    if not files:
        return [], _OK_STATUS

    cmd = [
        _resolve_executable("ansible-lint"),
        "-f",
        "json",
        "--nocolor",
        *[str(f) for f in files],
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=240,
            cwd=str(project_dir) if project_dir else None,
        )
    except FileNotFoundError:
        return [], _NOT_INSTALLED_STATUS
    except Exception:
        return [], _ERROR_STATUS

    findings = _parse_codeclimate(proc.stdout)

    # ansible-lint returns 2 when violations are found (expected) and 0 when
    # clean.  A non-zero exit with no parseable findings and no stdout signals an
    # internal error (bad config, syntax crash) rather than lint violations.
    if not findings and proc.returncode not in (0, 2) and not proc.stdout.strip():
        return [], _ERROR_STATUS

    return findings, _OK_STATUS
