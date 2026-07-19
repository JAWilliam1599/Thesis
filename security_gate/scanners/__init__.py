"""Scanner adapters for the IaC security gate.

Each adapter normalises a tool's output into the shared finding schema and
returns ``(findings, status)`` so the gate can score CloudFormation (CDK) and
Ansible (on-prem) inputs through the same risk engine.
"""
from security_gate.scanners.ansible_lint_adapter import run_ansible_lint
from security_gate.scanners.aws_config_adapter import fetch_violations
from security_gate.scanners.cfn_lint_adapter import run_cfn_lint
from security_gate.scanners.checkov_adapter import run_checkov
from security_gate.scanners.infracost_adapter import run_infracost
from security_gate.scanners.secret_scan_adapter import run_secret_scan

__all__ = [
    "run_ansible_lint",
    "fetch_violations",
    "run_cfn_lint",
    "run_checkov",
    "run_infracost",
    "run_secret_scan",
]
