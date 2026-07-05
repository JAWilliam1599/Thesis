"""Infracost adapter for IaC cost analysis in the CDK security gate.

Runs `infracost scan <cdk_out_dir> --json` against the synthesized CloudFormation
output directory (auto-detection; supports CloudFormation natively).

Status values returned:
    ok            – infracost ran and returned a parseable cost estimate
    skipped       – disabled by caller
    not_installed – infracost binary not found
    not_supported – infracost ran but produced no cost data (auth error, unsupported
                    resources, or no priceable resources in templates)
    error         – unexpected subprocess or JSON parse error
"""
from __future__ import annotations

import json
import os
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


_OK_STATUS = "ok"
_NOT_INSTALLED_STATUS = "not_installed"
_SKIPPED_STATUS = "skipped"
_NOT_SUPPORTED_STATUS = "not_supported"
_ERROR_STATUS = "error"


def _parse_cost(value: Any) -> float:
    """Parse a cost value that may be a string, float, or None."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def run_infracost(
    cdk_out_dir: Path,
    *,
    enabled: bool = True,
) -> dict[str, Any]:
    """Run `infracost scan <cdk_out_dir> --json` and return cost estimate.

    The current infracost CLI (v0.10+) uses `infracost scan` instead of the
    removed `breakdown` command.  It auto-detects CloudFormation from the
    directory and prices all supported resources in one pass.

    Returns a dict with keys:
        status            – "ok" | "skipped" | "not_installed" | "not_supported"
                            | "error"
        cost_delta_usd    – estimated total monthly cost in USD (float)
        total_monthly_usd – same value (alias for display)
        template_count    – number of projects priced by infracost
        message           – human-readable status detail
    """
    if not enabled:
        return {
            "status": _SKIPPED_STATUS,
            "cost_delta_usd": 0.0,
            "total_monthly_usd": 0.0,
            "template_count": 0,
            "message": "Infracost disabled by caller.",
        }

    cdk_out_dir = Path(cdk_out_dir)
    if not cdk_out_dir.exists():
        return {
            "status": _NOT_SUPPORTED_STATUS,
            "cost_delta_usd": 0.0,
            "total_monthly_usd": 0.0,
            "template_count": 0,
            "message": f"cdk.out directory not found: {cdk_out_dir}",
        }

    infracost_exe = _resolve_executable("infracost")
    cmd = [infracost_exe, "scan", str(cdk_out_dir), "--json"]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError:
        return {
            "status": _NOT_INSTALLED_STATUS,
            "cost_delta_usd": 0.0,
            "total_monthly_usd": 0.0,
            "template_count": 0,
            "message": "infracost is not installed or not on PATH.",
        }
    except Exception as exc:
        return {
            "status": _ERROR_STATUS,
            "cost_delta_usd": 0.0,
            "total_monthly_usd": 0.0,
            "template_count": 0,
            "message": f"Unexpected error running infracost: {exc}",
        }

    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()

    if not stdout:
        # infracost ran but produced no JSON — auth failure, unsupported dir, etc.
        detail = stderr.splitlines()[0] if stderr else "no output produced"
        hint = ""
        if not os.environ.get("INFRACOST_API_KEY"):
            hint = (
                " Hint: no INFRACOST_API_KEY is set — add it to the repo .env "
                "or via the UI Login tab (free key from dashboard.infracost.io)."
            )
        return {
            "status": _NOT_SUPPORTED_STATUS,
            "cost_delta_usd": 0.0,
            "total_monthly_usd": 0.0,
            "template_count": 0,
            "message": f"infracost produced no output: {detail}{hint}",
        }

    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "status": _ERROR_STATUS,
            "cost_delta_usd": 0.0,
            "total_monthly_usd": 0.0,
            "template_count": 0,
            "message": "infracost output was not valid JSON.",
        }

    # `infracost scan --json` actual output schema:
    # {
    #   "summary": { "total_monthly_cost": "49.634", "costed_resources": 5, ... },
    #   "projects": [ { "summary": { "total_monthly_cost": "12.00", ... }, ... } ]
    # }
    summary: dict[str, Any] = parsed.get("summary") or {}
    total_monthly = _parse_cost(summary.get("total_monthly_cost"))
    projects: list[dict[str, Any]] = parsed.get("projects", [])

    # Fallback: sum per-project summaries if top-level summary is absent.
    if total_monthly == 0.0 and projects:
        for project in projects:
            proj_summary = project.get("summary") or {}
            total_monthly += _parse_cost(proj_summary.get("total_monthly_cost"))

    template_count = len(projects)
    costed_resources = int(summary.get("costed_resources", 0))

    if total_monthly == 0.0:
        if costed_resources == 0:
            # All resources are free-tier or unsupported by infracost.
            return {
                "status": _NOT_SUPPORTED_STATUS,
                "cost_delta_usd": 0.0,
                "total_monthly_usd": 0.0,
                "template_count": template_count,
                "message": "infracost found no priceable resources in cdk.out.",
            }
        # costed_resources > 0 with a $0 baseline is legitimate: the priced
        # resources (e.g. S3, Lambda, DynamoDB on-demand) are usage-based and
        # carry no fixed monthly cost. Report success with a $0 delta.
        return {
            "status": _OK_STATUS,
            "cost_delta_usd": 0.0,
            "total_monthly_usd": 0.0,
            "template_count": template_count,
            "message": (
                f"Estimated $0.00/month across {template_count} project(s) "
                f"({costed_resources} usage-based resource(s) with no fixed monthly cost)."
            ),
        }

    msg = f"Estimated ${total_monthly:.2f}/month across {template_count} project(s) ({costed_resources} costed resource(s))."
    return {
        "status": _OK_STATUS,
        "cost_delta_usd": round(total_monthly, 4),
        "total_monthly_usd": round(total_monthly, 4),
        "template_count": template_count,
        "message": msg,
    }
