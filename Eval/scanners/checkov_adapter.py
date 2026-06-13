"""Checkov adapter for IaC security gate.

Runs checkov against a CDK output directory and normalises findings into the
shared finding schema used by IaCSecurityGate.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _resolve_executable(name: str) -> str:
    """Return the absolute path to *name*, preferring the active venv's bin dir."""
    venv_bin = Path(sys.executable).parent
    candidate = venv_bin / name
    if candidate.is_file():
        return str(candidate)
    found = shutil.which(name)
    return found if found else name

# Map checkov severity strings to internal severity levels.
_SEVERITY_MAP: dict[str, str] = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
    "INFO": "low",
    "UNKNOWN": "medium",
}

_SKIPPED_STATUS = "skipped"
_OK_STATUS = "ok"
_NOT_INSTALLED_STATUS = "not_installed"
_ERROR_STATUS = "error"


def _normalise_severity(raw: str) -> str:
    return _SEVERITY_MAP.get(str(raw).strip().upper(), "medium")


def _extract_findings_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse a single checkov result block (one framework/runner)."""
    findings: list[dict[str, Any]] = []

    failed_checks = result.get("results", {}).get("failed_checks", [])
    if not isinstance(failed_checks, list):
        return findings

    for check in failed_checks:
        if not isinstance(check, dict):
            continue

        check_id: str = str(check.get("check_id", ""))
        check_name: str = str(check.get("check_name", ""))
        severity_raw: str = str(check.get("severity", "UNKNOWN") or "UNKNOWN")
        resource: str = str(check.get("resource", "unknown"))
        file_path: str = str(check.get("repo_file_path") or check.get("file_path") or "")

        message = f"[{check_id}] {check_name}" if check_id else check_name

        findings.append(
            {
                "severity": _normalise_severity(severity_raw),
                "source": "checkov",
                "message": message,
                "resource_id": resource,
                "template": Path(file_path).name if file_path else "unknown",
            }
        )

    return findings


def run_checkov(
    cdk_out_dir: Path,
    *,
    enabled: bool = True,
) -> tuple[list[dict[str, Any]], str]:
    """Run checkov against *cdk_out_dir* and return (findings, status).

    Status values: "ok" | "skipped" | "not_installed" | "error"

    Gracefully returns an empty list with an appropriate status when checkov is
    not installed or fails in an unexpected way.
    """
    if not enabled:
        return [], _SKIPPED_STATUS

    cmd = [
        _resolve_executable("checkov"),
        "-d",
        str(cdk_out_dir),
        "--framework",
        "cloudformation",
        "-o",
        "json",
        "--compact",
        "--quiet",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        return [], _NOT_INSTALLED_STATUS
    except Exception:
        return [], _ERROR_STATUS

    raw_output = proc.stdout.strip()
    if not raw_output:
        # No output is acceptable — means no findings or empty dir.
        return [], _OK_STATUS

    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError:
        return [], _ERROR_STATUS

    findings: list[dict[str, Any]] = []

    # checkov may return a single result dict or a list of result dicts (one per runner).
    if isinstance(parsed, list):
        for result in parsed:
            if isinstance(result, dict):
                findings.extend(_extract_findings_from_result(result))
    elif isinstance(parsed, dict):
        findings.extend(_extract_findings_from_result(parsed))

    return findings, _OK_STATUS
