"""cfn-lint adapter for IaC security gate.

Runs cfn-lint against a list of CloudFormation template files and normalises
findings into the shared finding schema used by IaCSecurityGate.
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

# cfn-lint severity → internal severity
_SEVERITY_MAP: dict[str, str] = {
    "error": "high",
    "warning": "medium",
    "informational": "low",
    "info": "low",
    "unknown": "medium",
}

_SKIPPED_STATUS = "skipped"
_OK_STATUS = "ok"
_NOT_INSTALLED_STATUS = "not_installed"
_ERROR_STATUS = "error"


def _normalise_severity(raw: str) -> str:
    return _SEVERITY_MAP.get(str(raw).strip().lower(), "medium")


def _resource_id_from_location(location: Any) -> str:
    """Extract the CloudFormation resource logical ID from a cfn-lint Location."""
    if not isinstance(location, dict):
        return "unknown"
    path = location.get("Path")
    if not isinstance(path, list) or len(path) < 2:
        return "unknown"
    if path[0] == "Resources":
        return str(path[1])
    return "unknown"


def _parse_cfn_lint_output(
    raw: str,
    template_name: str,
) -> list[dict[str, Any]]:
    """Parse cfn-lint JSON output for a single template."""
    findings: list[dict[str, Any]] = []

    if not raw.strip():
        return findings

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return findings

    if not isinstance(parsed, list):
        return findings

    for item in parsed:
        if not isinstance(item, dict):
            continue

        rule: dict[str, Any] = item.get("Rule") or {}
        rule_id: str = str(rule.get("Id", ""))
        level: str = str(item.get("Level", "unknown"))
        message: str = str(item.get("Message", ""))
        location: Any = item.get("Location")

        full_message = f"[{rule_id}] {message}" if rule_id else message
        resource_id = _resource_id_from_location(location)

        findings.append(
            {
                "severity": _normalise_severity(level),
                "source": "cfn-lint",
                "message": full_message,
                "resource_id": resource_id,
                "template": template_name,
            }
        )

    return findings


def run_cfn_lint(
    template_files: list[Path],
    *,
    enabled: bool = True,
) -> tuple[list[dict[str, Any]], str]:
    """Run cfn-lint against each template file and return (findings, status).

    Status values: "ok" | "skipped" | "not_installed" | "error"

    cfn-lint exits with a non-zero code when it finds issues — this is expected.
    stdout is parsed regardless of exit code.  A FileNotFoundError means the
    tool is not installed.
    """
    if not enabled:
        return [], _SKIPPED_STATUS

    if not template_files:
        return [], _OK_STATUS

    all_findings: list[dict[str, Any]] = []
    encountered_not_installed = False
    encountered_error = False

    for template_path in template_files:
        cmd = [_resolve_executable("cfn-lint"), str(template_path), "--format", "json"]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except FileNotFoundError:
            encountered_not_installed = True
            break
        except Exception:
            encountered_error = True
            continue

        findings = _parse_cfn_lint_output(proc.stdout, template_path.name)
        all_findings.extend(findings)

    if encountered_not_installed:
        return [], _NOT_INSTALLED_STATUS
    if encountered_error and not all_findings:
        return [], _ERROR_STATUS

    return all_findings, _OK_STATUS
