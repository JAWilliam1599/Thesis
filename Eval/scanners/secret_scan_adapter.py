"""Lightweight secret / sensitive-value scanner for IaC source files.

Complements ansible-lint and checkov on the on-prem path by catching hardcoded
credentials in playbooks and variable files (AWS keys, private keys, plaintext
passwords / tokens).  Pure-Python regex scan — no external tool or Docker
dependency — so it is always available.

Findings are emitted in the shared schema used by IaCSecurityGate.

Status values (consistent with the other scanner adapters):
    "ok" | "skipped" | "error"
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_SKIPPED_STATUS = "skipped"
_OK_STATUS = "ok"
_ERROR_STATUS = "error"

# Values that are clearly not hardcoded secrets — Jinja vars, Ansible vault
# references, and lookups.  Lines whose value matches these are ignored.
_SAFE_VALUE = re.compile(r"\{\{.*\}\}|!vault|lookup\s*\(|\$\{", re.IGNORECASE)

# (compiled regex, severity, category, human message) tuples.
_PATTERNS: list[tuple[re.Pattern[str], str, str, str]] = [
    (
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "critical",
        "secret_aws_access_key",
        "Hardcoded AWS access key ID detected.",
    ),
    (
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
        "critical",
        "secret_private_key",
        "Hardcoded private key material detected.",
    ),
    (
        re.compile(
            r"(?i)\b(?:aws_)?secret_access_key\b\s*[:=]\s*['\"]?[A-Za-z0-9/+]{40}\b"
        ),
        "critical",
        "secret_aws_secret_key",
        "Hardcoded AWS secret access key detected.",
    ),
    (
        re.compile(
            r"(?i)\b(?:password|passwd|pwd)\b\s*[:=]\s*['\"]?[^\s'\"#{}]{6,}"
        ),
        "high",
        "secret_password",
        "Hardcoded password detected.",
    ),
    (
        re.compile(
            r"(?i)\b(?:api[_-]?key|auth[_-]?token|access[_-]?token|secret[_-]?token)\b"
            r"\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"
        ),
        "high",
        "secret_token",
        "Hardcoded API key or token detected.",
    ),
]


def _scan_text(text: str, template_name: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _SAFE_VALUE.search(line):
            continue

        for pattern, severity, category, message in _PATTERNS:
            if pattern.search(line):
                dedup_key = (category, lineno)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                findings.append(
                    {
                        "severity": severity,
                        "source": "secret-scan",
                        "message": message,
                        "resource_id": f"{template_name}:{lineno}",
                        "template": template_name,
                        "category": category,
                    }
                )

    return findings


def run_secret_scan(
    files: list[Path],
    *,
    enabled: bool = True,
) -> tuple[list[dict[str, Any]], str]:
    """Scan *files* for hardcoded secrets and return (findings, status).

    Reads each file as UTF-8 (errors ignored) and applies the secret patterns.
    Unreadable files are skipped silently; an empty file list is an "ok" no-op.
    """
    if not enabled:
        return [], _SKIPPED_STATUS

    findings: list[dict[str, Any]] = []
    for file_path in files:
        try:
            text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        findings.extend(_scan_text(text, Path(file_path).name))

    return findings, _OK_STATUS
