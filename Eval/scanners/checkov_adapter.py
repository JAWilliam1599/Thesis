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

# Map Checkov check IDs to semantic categories shared with iac_security_gate
# heuristics so cross-source deduplication can collapse overlapping findings.
# Unmapped check IDs use the check ID itself as the category.
_CHECKOV_CATEGORY_MAP: dict[str, str] = {
    "CKV_AWS_24": "sg_ssh_open",
    "CKV_AWS_25": "sg_rdp_open",
    "CKV_AWS_260": "sg_public_ingress",
    "CKV_AWS_88": "sg_public_ingress",
    "CKV_AWS_18": "s3_access_logging",
    "CKV_AWS_21": "s3_versioning",
    "CKV_AWS_19": "s3_encryption",
    "CKV_AWS_20": "s3_public_acl",
    "CKV_AWS_53": "s3_public_access_block",
    "CKV_AWS_54": "s3_public_access_block",
    "CKV_AWS_55": "s3_public_access_block",
    "CKV_AWS_56": "s3_public_access_block",
    "CKV_AWS_116": "lambda_dlq",
    "CKV_AWS_115": "lambda_concurrency",
    "CKV_AWS_117": "lambda_vpc",
    "CKV_AWS_16": "rds_encryption",
    "CKV_AWS_17": "rds_public",
    "CKV_AWS_211": "ebs_encryption",
    "CKV_AWS_212": "ebs_encryption",
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

        # Checkov emits resource as "AWS::Type.LogicalId"; normalise to bare
        # logical ID so it matches the heuristic resource_id for cross-source dedup.
        if "." in resource:
            resource = resource.split(".", 1)[1]

        message = f"[{check_id}] {check_name}" if check_id else check_name
        category = _CHECKOV_CATEGORY_MAP.get(check_id, check_id)

        findings.append(
            {
                "severity": _normalise_severity(severity_raw),
                "source": "checkov",
                "message": message,
                "resource_id": resource,
                "template": Path(file_path).name if file_path else "unknown",
                "category": category,
            }
        )

    return findings


def run_checkov(
    cdk_out_dir: Path,
    *,
    enabled: bool = True,
    template_files: list[Path] | None = None,
    framework: str = "cloudformation",
) -> tuple[list[dict[str, Any]], str]:
    """Run checkov against specific template files and return (findings, status).

    *template_files* is the list of template paths to scan (as returned by
    IaCSecurityGate.collect_templates()).  When provided, checkov is invoked
    once per file with ``--file`` so only the current generation is scanned,
    not any stale templates that may exist in cdk_out_dir from a prior run.
    Falls back to scanning the directory when *template_files* is not provided.

    *framework* selects the checkov runner ("cloudformation" for synthesized CDK
    templates, "ansible" for on-prem playbooks).

    Status values: "ok" | "skipped" | "not_installed" | "error"

    Gracefully returns an empty list with an appropriate status when checkov is
    not installed or fails in an unexpected way.
    """
    if not enabled:
        return [], _SKIPPED_STATUS

    targets = template_files or []
    if not targets:
        # No specific files supplied — fall back to directory scan
        return _run_checkov_on_dir(cdk_out_dir, framework=framework)

    all_findings: list[dict[str, Any]] = []
    encountered_not_installed = False
    encountered_error = False

    for template_path in targets:
        cmd = [
            _resolve_executable("checkov"),
            "--file",
            str(template_path),
            "--framework",
            framework,
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
            encountered_not_installed = True
            break
        except Exception:
            encountered_error = True
            continue

        raw_output = proc.stdout.strip()
        if not raw_output:
            continue
        try:
            parsed = json.loads(raw_output)
        except json.JSONDecodeError:
            encountered_error = True
            continue

        if isinstance(parsed, list):
            for result in parsed:
                if isinstance(result, dict):
                    all_findings.extend(_extract_findings_from_result(result))
        elif isinstance(parsed, dict):
            all_findings.extend(_extract_findings_from_result(parsed))

    if encountered_not_installed:
        return [], _NOT_INSTALLED_STATUS
    if encountered_error and not all_findings:
        return [], _ERROR_STATUS
    return all_findings, _OK_STATUS


def _run_checkov_on_dir(
    cdk_out_dir: Path,
    *,
    framework: str = "cloudformation",
) -> tuple[list[dict[str, Any]], str]:
    """Legacy directory-scan fallback (used when no template_files provided)."""
    cmd = [
        _resolve_executable("checkov"),
        "-d",
        str(cdk_out_dir),
        "--framework",
        framework,
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
