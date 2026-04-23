from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from collections import defaultdict
from pathlib import Path
from typing import Iterable


SEVERITY_VALUE_MAP = {
    "critical": 10,
    "high": 8,
    "medium": 5,
    "low": 2,
    "info": 1,
    "warning": 3,
}

RISK_LEVELS = (
    (80, "Critical", "Block deployment"),
    (60, "High", "Require manual approval"),
    (40, "Medium", "Allow with warning"),
    (0, "Low", "Log for monitoring"),
)

PUBLIC_FACING_PATTERNS = (
    r"@app\.route",
    r"@bp\.route",
    r"flask\.",
    r"fastapi",
    r"uvicorn",
    r"http\.server",
    r"socketserver",
    r"listen\(",
    r"app\.run\(",
    r"request\.",
)

SANDBOX_PATTERNS = (
    r"pytest",
    r"unittest",
    r"test_",
    r"mock",
    r"sandbox",
)

INTERNAL_PATTERNS = (
    r"boto3",
    r"botocore",
    r"aws",
    r"lambda",
    r"s3",
    r"ec2",
)

HIGH_EXPL_PATTERNS = (
    "remote code execution",
    "rce",
    "command injection",
    "shell injection",
    "sql injection",
    "path traversal",
    "deserialization",
    "hardcoded secret",
    "hardcoded password",
    "credential",
    "token",
    "eval",
    "exec",
    "os.system",
    "subprocess",
    "popen",
)

MEDIUM_EXPL_PATTERNS = (
    "injection",
    "vulnerability",
    "unsafe",
    "weak",
    "missing auth",
    "csrf",
    "xss",
    "secret",
)

LOW_EXPL_PATTERNS = (
    "warning",
    "informational",
    "style",
    "complexity",
)


@dataclass(frozen=True)
class ScoredFinding:
    source: str
    severity: str
    message: str
    severity_value: int
    severity_score: float
    exploitability_score: float
    exposure_score: float
    confidence_score: float
    risk_score: float
    risk_level: str
    recommended_action: str
    normalized_key: str


class RiskScorer:
    """Compute a multi-factor risk score for code findings."""

    def __init__(self, deployment_context: str | None = None):
        self.deployment_context = (deployment_context or "internal").strip().lower()

    def score(self, *, code: str, findings: Iterable[dict]) -> dict:
        findings_list = [dict(finding) for finding in findings]
        normalized_groups = self._build_normalized_groups(findings_list)
        scored_findings = []

        for finding in findings_list:
            scored_findings.append(self._score_finding(code=code, finding=finding, normalized_groups=normalized_groups))

        overall_risk_score = max((item.risk_score for item in scored_findings), default=0.0)
        risk_level, recommended_action = self._classify(overall_risk_score)
        risk_summary = self._summarize(scored_findings)

        return {
            "risk_score": round(overall_risk_score, 2),
            "risk_level": risk_level,
            "recommended_action": recommended_action,
            "risk_summary": risk_summary,
            "risk_findings": [asdict(item) for item in scored_findings],
        }

    def _score_finding(self, *, code: str, finding: dict, normalized_groups: dict[str, set[str]]) -> ScoredFinding:
        source = str(finding.get("source", "unknown")).strip().lower() or "unknown"
        severity = self._normalize_severity(str(finding.get("severity", "low")))
        message = str(finding.get("message", "")).strip()
        normalized_key = self._normalize_message(message)

        severity_value = self._severity_value(severity)
        severity_score = severity_value / 10.0
        exploitability_score = self._exploitability_score(source=source, severity=severity, message=message, code=code)
        exposure_score = self._exposure_score(code)
        confidence_score = self._confidence_score(source=source, severity=severity, normalized_key=normalized_key, normalized_groups=normalized_groups)

        risk_score = (
            100.0
            * (
                0.35 * severity_score
                + 0.25 * exploitability_score
                + 0.25 * exposure_score
                + 0.15 * confidence_score
            )
        )

        risk_level, recommended_action = self._classify(risk_score)
        return ScoredFinding(
            source=source,
            severity=severity,
            message=message,
            severity_value=severity_value,
            severity_score=round(severity_score, 4),
            exploitability_score=round(exploitability_score, 4),
            exposure_score=round(exposure_score, 4),
            confidence_score=round(confidence_score, 4),
            risk_score=round(risk_score, 2),
            risk_level=risk_level,
            recommended_action=recommended_action,
            normalized_key=normalized_key,
        )

    def _severity_value(self, severity: str) -> int:
        return SEVERITY_VALUE_MAP.get(severity, 2)

    def _normalize_severity(self, severity: str) -> str:
        severity_lower = severity.strip().lower()
        if severity_lower in SEVERITY_VALUE_MAP:
            return severity_lower
        return "low"

    def _normalize_message(self, message: str) -> str:
        normalized = message.lower()
        normalized = re.sub(r"\b0x[0-9a-f]+\b", "<hex>", normalized)
        normalized = re.sub(r"\b\d+\b", "<num>", normalized)
        normalized = re.sub(r"[^a-z0-9<>&._/ -]+", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized[:240]

    def _build_normalized_groups(self, findings: list[dict]) -> dict[str, set[str]]:
        groups: dict[str, set[str]] = defaultdict(set)
        for finding in findings:
            source = str(finding.get("source", "unknown")).strip().lower() or "unknown"
            message = str(finding.get("message", ""))
            groups[self._normalize_message(message)].add(source)
        return groups

    def _exploitability_score(self, *, source: str, severity: str, message: str, code: str) -> float:
        combined_text = f"{message}\n{code}".lower()

        if any(pattern in combined_text for pattern in HIGH_EXPL_PATTERNS):
            return 1.0
        if any(pattern in combined_text for pattern in MEDIUM_EXPL_PATTERNS):
            return 0.8
        if any(pattern in combined_text for pattern in LOW_EXPL_PATTERNS):
            return 0.2

        if source == "bandit":
            return {"critical": 1.0, "high": 0.9, "medium": 0.7, "low": 0.4, "info": 0.3, "warning": 0.4}.get(severity, 0.5)
        if source == "semgrep":
            return {"critical": 1.0, "high": 0.95, "medium": 0.75, "low": 0.45, "info": 0.3, "warning": 0.65}.get(severity, 0.5)
        if source == "quickval":
            return 0.4
        return 0.5

    def _exposure_score(self, code: str) -> float:
        context = self.deployment_context
        if context == "public":
            return 1.0
        if context == "internal":
            inferred = self._infer_exposure_from_code(code)
            return max(0.6, inferred)
        if context == "onprem":
            inferred = self._infer_exposure_from_code(code)
            return min(inferred, 0.3)
        if context == "sandbox":
            inferred = self._infer_exposure_from_code(code)
            return min(inferred, 0.1)
        return self._infer_exposure_from_code(code)

    def _infer_exposure_from_code(self, code: str) -> float:
        code_lower = code.lower()
        if any(re.search(pattern, code_lower) for pattern in PUBLIC_FACING_PATTERNS):
            return 1.0
        if any(re.search(pattern, code_lower) for pattern in INTERNAL_PATTERNS):
            return 0.6
        if any(re.search(pattern, code_lower) for pattern in SANDBOX_PATTERNS):
            return 0.1
        if "if __name__ == \"__main__\":" in code_lower:
            return 0.6
        return 0.6

    def _confidence_score(
        self,
        *,
        source: str,
        severity: str,
        normalized_key: str,
        normalized_groups: dict[str, set[str]],
    ) -> float:
        supporting_sources = normalized_groups.get(normalized_key, {source})
        if len(supporting_sources) >= 2:
            return 1.0
        if source in {"bandit", "semgrep"} and severity in {"critical", "high"}:
            return 0.8
        if source == "quickval":
            return 0.3
        if severity in {"critical", "high"}:
            return 0.8
        if severity in {"medium"}:
            return 0.5
        return 0.4

    def _classify(self, risk_score: float) -> tuple[str, str]:
        for threshold, level, action in RISK_LEVELS:
            if risk_score >= threshold:
                return level, action
        return "Low", "Log for monitoring"

    def _summarize(self, findings: Iterable[ScoredFinding]) -> dict:
        summary = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "sources": {},
        }
        source_counts: dict[str, int] = defaultdict(int)
        for finding in findings:
            summary[finding.risk_level.lower()] += 1
            source_counts[finding.source] += 1
        summary["sources"] = dict(source_counts)
        return summary
