from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Eval.scanners.ansible_lint_adapter import run_ansible_lint
from Eval.scanners.aws_config_adapter import fetch_violations
from Eval.scanners.checkov_adapter import run_checkov
from Eval.scanners.cfn_lint_adapter import run_cfn_lint
from Eval.scanners.infracost_adapter import run_infracost
from Eval.scanners.ml_risk_adapter import run_ml_risk
from Eval.scanners.secret_scan_adapter import run_secret_scan

SEVERITY_POINTS = {
    "critical": 20,
    "high": 10,
    "medium": 5,
    "low": 1,
}

THRESHOLDS = {
    "pass_max": 20,
    "review_max": 80,
}


def _logs_root() -> Path:
    """Repo logs root, overridable per project via SYSSECOPS_LOG_DIR."""
    override = os.environ.get("SYSSECOPS_LOG_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / "logs"


def _severity_points(severity: str) -> int:
    return SEVERITY_POINTS.get(str(severity).strip().lower(), 1)


def _decision(score: int) -> str:
    if score <= THRESHOLDS["pass_max"]:
        return "pass"
    if score <= THRESHOLDS["review_max"]:
        return "review"
    return "reject"


def _decision_message(decision: str) -> str:
    if decision == "pass":
        return "Auto-pass. Deployment may proceed."
    if decision == "review":
        return "Manual review required before deployment."
    return "Auto-reject. Regenerate IaC or remediate findings."


def _resource_type(resource: dict[str, Any]) -> str:
    return str(resource.get("Type", ""))


def _resource_props(resource: dict[str, Any]) -> dict[str, Any]:
    props = resource.get("Properties")
    if isinstance(props, dict):
        return props
    return {}


# Used during cross-source deduplication to resolve which severity wins.
_SEVERITY_ORDER: dict[str, int] = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _new_finding(
    severity: str,
    source: str,
    message: str,
    resource_id: str,
    category: str = "",
) -> dict[str, Any]:
    return {
        "severity": severity,
        "source": source,
        "message": message,
        "resource_id": resource_id,
        "category": category,
    }


def _dedupe_findings(all_findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse semantically equivalent findings reported by multiple scanners.

    Key: (resource_id, template, category) — category groups equivalent checks
    from different tools (e.g. heuristic SSH + CKV_AWS_24, or an ansible-lint
    rule + a secret-scan hit on the same line).  Resolution keeps the highest
    severity and merges source labels when tied.  Findings without a category
    fall back to their message string so unrelated findings are never merged.
    """
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for f in all_findings:
        key = (
            str(f.get("resource_id", "")),
            str(f.get("template", "")),
            str(f.get("category") or f.get("message", "")),
        )
        existing = groups.get(key)
        if existing is None:
            groups[key] = dict(f)
        else:
            f_rank = _SEVERITY_ORDER.get(str(f.get("severity", "low")).lower(), 1)
            ex_rank = _SEVERITY_ORDER.get(str(existing.get("severity", "low")).lower(), 1)
            if f_rank > ex_rank:
                merged_source = f"{f['source']}+{existing['source']}"
                groups[key] = dict(f)
                groups[key]["source"] = merged_source
            elif f_rank == ex_rank:
                existing["source"] = f"{existing['source']}+{f['source']}"
            # else: incoming severity is lower — discard, keep existing.
    return list(groups.values())


def _score_findings(
    deduped: list[dict[str, Any]],
    *,
    cost_delta_usd: float,
    config_violations: int,
    ml_score: int = 0,
) -> dict[str, Any]:
    """Compute the risk score and decision from deduplicated findings.

    Shared by the CloudFormation (CDK) and Ansible (on-prem) gate paths so both
    use the identical severity weights, cost banding, and decision thresholds.
    ``ml_score`` is the pre-computed logistic-regression component
    (``round(P(insecure) * 20)``); it is 0 on the Ansible path where the model
    does not apply.
    """
    severity_score = sum(_severity_points(item.get("severity", "low")) for item in deduped)

    cost_score = 0
    if cost_delta_usd > 50:
        cost_score = 10
    elif cost_delta_usd > 10:
        cost_score = 5

    config_score = max(0, config_violations) * 5
    ml_component = max(0, int(ml_score))
    total_score = int(severity_score + cost_score + config_score + ml_component)

    return {
        "severity": severity_score,
        "cost": cost_score,
        "aws_config": config_score,
        "ml_risk": ml_component,
        "total": total_score,
        "decision": _decision(total_score),
    }


class IaCSecurityGate:
    """IaC gate that inspects synthesized CloudFormation templates and scores risk."""

    # --- Report persistence ---

    def save_report(self, report: dict[str, Any], run_id: str, log_dir: Path | None = None) -> str:
        """Persist *report* as JSON under *log_dir*/gate_<run_id>.json.

        Creates *log_dir* (and parents) if it does not exist.
        Returns the absolute path of the written file.
        """
        if log_dir is None:
            log_dir = _logs_root() / "gate_reports"
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        report_path = log_dir / f"gate_{run_id}.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return str(report_path)

    def collect_templates(self, cdk_out_dir: Path) -> list[Path]:
        if not cdk_out_dir.exists() or not cdk_out_dir.is_dir():
            return []

        templates: list[Path] = []
        for path in sorted(cdk_out_dir.glob("*.json")):
            if path.name in {"manifest.json", "tree.json"}:
                continue
            try:
                parsed = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and isinstance(parsed.get("Resources"), dict):
                templates.append(path)
        return templates

    def analyze_template(self, template: dict[str, Any]) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        resources = template.get("Resources")
        if not isinstance(resources, dict):
            return findings

        for resource_id, resource in resources.items():
            if not isinstance(resource, dict):
                continue

            rtype = _resource_type(resource)
            props = _resource_props(resource)

            if rtype == "AWS::EC2::SecurityGroup":
                ingress = props.get("SecurityGroupIngress")
                if isinstance(ingress, list):
                    for rule in ingress:
                        if not isinstance(rule, dict):
                            continue
                        cidr = rule.get("CidrIp")
                        from_port = rule.get("FromPort")
                        to_port = rule.get("ToPort")
                        if cidr == "0.0.0.0/0":
                            if from_port == 22 or to_port == 22:
                                findings.append(
                                    _new_finding(
                                        "critical",
                                        "iac_security_gate",
                                        "Security group allows SSH from anywhere (0.0.0.0/0).",
                                        resource_id,
                                        "sg_ssh_open",
                                    )
                                )
                            else:
                                findings.append(
                                    _new_finding(
                                        "high",
                                        "iac_security_gate",
                                        "Security group allows public ingress from 0.0.0.0/0.",
                                        resource_id,
                                        "sg_public_ingress",
                                    )
                                )

            if rtype == "AWS::S3::Bucket":
                access_block = props.get("PublicAccessBlockConfiguration")
                if not isinstance(access_block, dict):
                    findings.append(
                        _new_finding(
                            "high",
                            "iac_security_gate",
                            "S3 bucket is missing PublicAccessBlockConfiguration.",
                            resource_id,
                            "s3_public_access_block",
                        )
                    )
                else:
                    for key in (
                        "BlockPublicAcls",
                        "IgnorePublicAcls",
                        "BlockPublicPolicy",
                        "RestrictPublicBuckets",
                    ):
                        if access_block.get(key) is not True:
                            findings.append(
                                _new_finding(
                                    "high",
                                    "iac_security_gate",
                                    f"S3 bucket public access guard {key} is not set to true.",
                                    resource_id,
                                    "s3_public_access_block",
                                )
                            )
                access_control = props.get("AccessControl")
                if access_control in {"PublicRead", "PublicReadWrite"}:
                    findings.append(
                        _new_finding(
                            "critical",
                            "iac_security_gate",
                            "S3 bucket ACL is public.",
                            resource_id,
                            "s3_public_acl",
                        )
                    )

            if rtype == "AWS::IAM::Policy":
                policy_doc = props.get("PolicyDocument")
                statements = policy_doc.get("Statement") if isinstance(policy_doc, dict) else None
                if isinstance(statements, list):
                    for statement in statements:
                        if not isinstance(statement, dict):
                            continue
                        action = statement.get("Action")
                        resource = statement.get("Resource")
                        is_wild_action = action == "*" or (isinstance(action, list) and "*" in action)
                        is_wild_resource = resource == "*" or (isinstance(resource, list) and "*" in resource)
                        if is_wild_action and is_wild_resource:
                            findings.append(
                                _new_finding(
                                    "critical",
                                    "iac_security_gate",
                                    "IAM policy allows Action=* and Resource=*.",
                                    resource_id,
                                    "iam_wildcard",
                                )
                            )

            if rtype == "AWS::RDS::DBInstance":
                if props.get("StorageEncrypted") is not True:
                    findings.append(
                        _new_finding(
                            "high",
                            "iac_security_gate",
                            "RDS instance storage encryption is disabled.",
                            resource_id,
                            "rds_encryption",
                        )
                    )

            if rtype == "AWS::EC2::Volume":
                if props.get("Encrypted") is not True:
                    findings.append(
                        _new_finding(
                            "medium",
                            "iac_security_gate",
                            "EBS volume encryption is disabled.",
                            resource_id,
                            "ebs_encryption",
                        )
                    )

        # Deduplicate within heuristic findings: one finding per
        # (resource_id, category) so a security group with N open ingress
        # rules does not emit N identical findings.
        seen_heuristic: set[tuple[str, str]] = set()
        unique_findings: list[dict[str, Any]] = []
        for f in findings:
            hkey = (str(f.get("resource_id", "")), str(f.get("category", "")))
            if hkey not in seen_heuristic:
                seen_heuristic.add(hkey)
                unique_findings.append(f)
        return unique_findings

    def evaluate(
        self,
        cdk_out_dir: Path,
        *,
        cost_delta_usd: float | None = None,
        aws_config_violations: int | None = None,
        use_checkov: bool = True,
        use_cfn_lint: bool = True,
        use_infracost: bool = True,
        use_aws_config: bool = True,
        use_ml_risk: bool = True,
        source_dir: Path | None = None,
        run_id: str | None = None,
        region: str | None = None,
        stack_name: str | None = None,
        profile_name: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate synthesized CDK templates and return a gate report dict.

        cost_delta_usd / aws_config_violations:
            Pass an explicit value to override automation.  Pass None (default)
            to let the gate auto-run Infracost / AWS Config and use the result.
        source_dir:
            Directory containing the CDK app's Python source (e.g. the project
            dir).  When provided and ``use_ml_risk`` is True, the trained
            logistic-regression model scores the source (bandit + semgrep
            features) and adds ``round(P(insecure) * 20)`` points.
        run_id:
            When provided, the gate report is persisted to
            logs/gate_reports/gate_<run_id>.json and report_path is included
            in the returned dict.
        """
        templates = self.collect_templates(cdk_out_dir)
        findings: list[dict[str, Any]] = []

        for template_path in templates:
            parsed = json.loads(template_path.read_text(encoding="utf-8"))
            file_findings = self.analyze_template(parsed)
            for finding in file_findings:
                finding["template"] = template_path.name
            findings.extend(file_findings)

        # --- External scanners ---
        checkov_findings, checkov_status = run_checkov(cdk_out_dir, enabled=use_checkov, template_files=templates)
        cfn_lint_findings, cfn_lint_status = run_cfn_lint(templates, enabled=use_cfn_lint)

        # Merge all findings then deduplicate across sources.
        all_findings = findings + checkov_findings + cfn_lint_findings
        deduped = _dedupe_findings(all_findings)

        # --- Scanner warnings for checkov / cfn-lint ---
        scanner_warnings: list[str] = []
        if checkov_status == "not_installed":
            scanner_warnings.append("checkov not installed — scan skipped.")
        elif checkov_status == "error":
            scanner_warnings.append("checkov encountered an error — scan skipped.")
        elif checkov_status == "skipped":
            scanner_warnings.append("checkov disabled by caller.")

        if cfn_lint_status == "not_installed":
            scanner_warnings.append("cfn-lint not installed — scan skipped.")
        elif cfn_lint_status == "error":
            scanner_warnings.append("cfn-lint encountered an error — scan skipped.")
        elif cfn_lint_status == "skipped":
            scanner_warnings.append("cfn-lint disabled by caller.")

        # --- Cost analysis (Infracost) ---
        cost_analysis = run_infracost(cdk_out_dir, enabled=use_infracost)
        if cost_delta_usd is not None:
            # Explicit override from caller — use it directly.
            effective_cost_delta = float(cost_delta_usd)
        else:
            effective_cost_delta = cost_analysis["cost_delta_usd"]
            status = cost_analysis["status"]
            if status == "not_installed":
                scanner_warnings.append("infracost not installed — cost analysis skipped.")
            elif status == "not_supported":
                scanner_warnings.append(f"infracost could not price these templates — cost analysis skipped: {cost_analysis.get('message', '')}")
            elif status == "error":
                scanner_warnings.append(f"infracost error — cost analysis skipped: {cost_analysis.get('message', '')}")
            elif status == "skipped":
                scanner_warnings.append("infracost disabled by caller.")

        # --- AWS Config violations ---
        config_analysis = fetch_violations(region=region, stack_name=stack_name, enabled=use_aws_config, profile_name=profile_name)
        if aws_config_violations is not None:
            # Explicit override from caller — use it directly.
            effective_config_violations = int(aws_config_violations)
        else:
            effective_config_violations = config_analysis["violation_count"]
            status = config_analysis["status"]
            if status == "not_installed":
                scanner_warnings.append("boto3 not installed — AWS Config check skipped.")
            elif status == "no_credentials":
                scanner_warnings.append("AWS credentials not found — Config check skipped.")
            elif status == "not_configured":
                scanner_warnings.append("AWS Config not enabled in account/region — check skipped.")
            elif status == "error":
                scanner_warnings.append(f"AWS Config error — check skipped: {config_analysis.get('message', '')}")
            elif status == "skipped":
                scanner_warnings.append("AWS Config check disabled by caller.")

        # --- ML risk (logistic regression on the CDK Python source) ---
        if source_dir is not None:
            ml_analysis = run_ml_risk(Path(source_dir), enabled=use_ml_risk)
        else:
            ml_analysis = {
                "status": "skipped",
                "probability": 0.0,
                "ml_score": 0,
                "files": [],
                "message": "No source directory provided — ML risk scoring skipped.",
            }
        if ml_analysis["status"] not in ("ok", "skipped"):
            scanner_warnings.append(
                f"ML risk model not applied: {ml_analysis.get('message', '')}"
            )
        elif ml_analysis["status"] == "skipped" and source_dir is not None and not use_ml_risk:
            scanner_warnings.append("ML risk model disabled by caller.")
        effective_ml_score = int(ml_analysis.get("ml_score", 0))

        # --- Scoring ---
        score_parts = _score_findings(
            deduped,
            cost_delta_usd=effective_cost_delta,
            config_violations=effective_config_violations,
            ml_score=effective_ml_score,
        )
        severity_score = score_parts["severity"]
        cost_score = score_parts["cost"]
        config_score = score_parts["aws_config"]
        total_score = score_parts["total"]

        decision = score_parts["decision"]

        timestamp = datetime.now(tz=timezone.utc).isoformat()

        result: dict[str, Any] = {
            "run_id": run_id,
            "timestamp": timestamp,
            "score": total_score,
            "decision": decision,
            "message": _decision_message(decision),
            "thresholds": {
                "pass_max": THRESHOLDS["pass_max"],
                "review_max": THRESHOLDS["review_max"],
            },
            "components": {
                "severity": severity_score,
                "cost": cost_score,
                "aws_config": config_score,
                "ml_risk": score_parts["ml_risk"],
            },
            "inputs": {
                "cost_delta_usd": effective_cost_delta,
                "cost_delta_override": cost_delta_usd is not None,
                "aws_config_violations": effective_config_violations,
                "aws_config_override": aws_config_violations is not None,
                "ml_probability": ml_analysis.get("probability", 0.0),
                "templates": [path.name for path in templates],
            },
            "scanner_status": {
                "checkov": checkov_status,
                "cfn_lint": cfn_lint_status,
                "infracost": cost_analysis["status"],
                "aws_config": config_analysis["status"],
                "ml_risk": ml_analysis["status"],
            },
            "scanner_warnings": scanner_warnings,
            "findings": deduped,
            "cost_analysis": cost_analysis,
            "config_analysis": config_analysis,
            "ml_analysis": ml_analysis,
            "report_path": None,
        }

        if run_id:
            result["report_path"] = self.save_report(result, run_id)

        return result

    # --- Ansible / on-prem path ---

    def collect_ansible_files(
        self,
        ansible_dir: Path,
        changed_files: list[Path] | None = None,
    ) -> list[Path]:
        """Return the YAML playbook/var files to scan on the Ansible path.

        When *changed_files* is provided (git-scoped), it is filtered to the
        YAML files under *ansible_dir*.  When None, every ``*.yml`` / ``*.yaml``
        file under *ansible_dir* is returned (full scan).
        """
        exts = {".yml", ".yaml"}
        if changed_files is not None:
            files: list[Path] = []
            for f in changed_files:
                p = Path(f)
                if p.suffix.lower() in exts and p.is_file():
                    files.append(p)
            return sorted(set(files))

        if not ansible_dir.exists() or not ansible_dir.is_dir():
            return []
        found = [p for p in ansible_dir.rglob("*") if p.suffix.lower() in exts and p.is_file()]
        return sorted(set(found))

    def evaluate_ansible(
        self,
        ansible_dir: Path,
        *,
        changed_files: list[Path] | None = None,
        aws_config_violations: int | None = None,
        use_ansible_lint: bool = True,
        use_checkov: bool = True,
        use_secret_scan: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate Ansible playbooks and return a gate report dict.

        Mirrors :meth:`evaluate` but sources findings from ansible-lint, checkov
        (``--framework ansible``) and the secret scanner instead of synthesized
        CloudFormation templates.  The same risk engine (severity weights, cost
        banding, thresholds) and report schema are reused so CDK and Ansible
        results are directly comparable.

        *changed_files*:
            When provided, only these files are scanned (git-scoped); otherwise
            every YAML file under *ansible_dir* is scanned.
        *aws_config_violations*:
            Optional override for AWS Config violations (e.g. for SSM-managed
            private nodes).  Defaults to 0 \u2014 Infracost and AWS Config auto-runs
            do not apply to playbooks.
        """
        ansible_dir = Path(ansible_dir)
        target_files = self.collect_ansible_files(ansible_dir, changed_files)

        ansible_findings, ansible_status = run_ansible_lint(
            target_files, enabled=use_ansible_lint, project_dir=ansible_dir
        )
        checkov_findings, checkov_status = run_checkov(
            ansible_dir,
            enabled=use_checkov,
            template_files=target_files,
            framework="ansible",
        )
        secret_findings, secret_status = run_secret_scan(target_files, enabled=use_secret_scan)

        deduped = _dedupe_findings(ansible_findings + checkov_findings + secret_findings)

        scanner_warnings: list[str] = []
        for label, status in (
            ("ansible-lint", ansible_status),
            ("checkov", checkov_status),
            ("secret-scan", secret_status),
        ):
            if status == "not_installed":
                scanner_warnings.append(f"{label} not installed — scan skipped.")
            elif status == "error":
                scanner_warnings.append(f"{label} encountered an error — scan skipped.")
            elif status == "skipped":
                scanner_warnings.append(f"{label} disabled by caller.")

        if not target_files:
            scanner_warnings.append("No Ansible YAML files matched — nothing to scan.")

        effective_config_violations = int(aws_config_violations) if aws_config_violations is not None else 0

        # Infracost / AWS Config auto-runs do not apply to playbooks; cost is 0.
        score_parts = _score_findings(
            deduped,
            cost_delta_usd=0.0,
            config_violations=effective_config_violations,
        )

        timestamp = datetime.now(tz=timezone.utc).isoformat()
        decision = score_parts["decision"]

        result: dict[str, Any] = {
            "run_id": run_id,
            "timestamp": timestamp,
            "score": score_parts["total"],
            "decision": decision,
            "message": _decision_message(decision),
            "thresholds": {
                "pass_max": THRESHOLDS["pass_max"],
                "review_max": THRESHOLDS["review_max"],
            },
            "components": {
                "severity": score_parts["severity"],
                "cost": score_parts["cost"],
                "aws_config": score_parts["aws_config"],
                "ml_risk": 0,
            },
            "inputs": {
                "cost_delta_usd": 0.0,
                "cost_delta_override": False,
                "aws_config_violations": effective_config_violations,
                "aws_config_override": aws_config_violations is not None,
                "templates": [p.name for p in target_files],
                "target": "ansible",
            },
            "scanner_status": {
                "ansible_lint": ansible_status,
                "checkov": checkov_status,
                "secret_scan": secret_status,
            },
            "scanner_warnings": scanner_warnings,
            "findings": deduped,
            "cost_analysis": {"status": "not_supported", "message": "Cost analysis does not apply to Ansible playbooks."},
            "config_analysis": {"status": "override" if aws_config_violations is not None else "skipped", "violation_count": effective_config_violations},
            "ml_analysis": {
                "status": "not_applicable",
                "probability": 0.0,
                "ml_score": 0,
                "files": [],
                "message": "ML risk model is trained on Python sources; it does not apply to Ansible playbooks.",
            },
            "report_path": None,
        }

        if run_id:
            result["report_path"] = self.save_report(result, run_id)

        return result
