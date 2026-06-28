"""Scanner adapters for the IaC security gate.

Each adapter normalises a tool's output into the shared finding schema and
returns ``(findings, status)`` so the gate can score CloudFormation (CDK) and
Ansible (on-prem) inputs through the same risk engine.
"""
from Eval.scanners.ansible_lint_adapter import run_ansible_lint
from Eval.scanners.aws_config_adapter import fetch_violations
from Eval.scanners.cfn_lint_adapter import run_cfn_lint
from Eval.scanners.checkov_adapter import run_checkov
from Eval.scanners.infracost_adapter import run_infracost
from Eval.scanners.secret_scan_adapter import run_secret_scan

__all__ = [
    "run_ansible_lint",
    "fetch_violations",
    "run_cfn_lint",
    "run_checkov",
    "run_infracost",
    "run_secret_scan",
]
