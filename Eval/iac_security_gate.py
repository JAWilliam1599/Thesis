from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SEVERITY_POINTS = {
    "critical": 30,
    "high": 10,
    "medium": 5,
    "low": 1,
}

THRESHOLDS = {
    "pass_max": 20,
    "review_max": 60,
}


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


def _new_finding(severity: str, source: str, message: str, resource_id: str) -> dict[str, Any]:
    return {
        "severity": severity,
        "source": source,
        "message": message,
        "resource_id": resource_id,
    }


class IaCSecurityGate:
    """IaC gate that inspects synthesized CloudFormation templates and scores risk."""

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
                                    )
                                )
                            else:
                                findings.append(
                                    _new_finding(
                                        "high",
                                        "iac_security_gate",
                                        "Security group allows public ingress from 0.0.0.0/0.",
                                        resource_id,
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
                        )
                    )

        return findings

    def evaluate(
        self,
        cdk_out_dir: Path,
        *,
        cost_delta_usd: float = 0.0,
        aws_config_violations: int = 0,
    ) -> dict[str, Any]:
        templates = self.collect_templates(cdk_out_dir)
        findings: list[dict[str, Any]] = []

        for template_path in templates:
            parsed = json.loads(template_path.read_text(encoding="utf-8"))
            file_findings = self.analyze_template(parsed)
            for finding in file_findings:
                finding["template"] = template_path.name
            findings.extend(file_findings)

        severity_score = sum(_severity_points(item.get("severity", "low")) for item in findings)

        cost_score = 0
        if cost_delta_usd > 50:
            cost_score = 40
        elif cost_delta_usd > 10:
            cost_score = 15

        config_score = max(0, int(aws_config_violations)) * 5
        total_score = int(severity_score + cost_score + config_score)

        decision = _decision(total_score)

        return {
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
            },
            "inputs": {
                "cost_delta_usd": cost_delta_usd,
                "aws_config_violations": aws_config_violations,
                "templates": [path.name for path in templates],
            },
            "findings": findings,
        }
