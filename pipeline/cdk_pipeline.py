from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from ExecComponent.exec_code import exec_code
from Eval.iac_security_gate import IaCSecurityGate


def resolve_cdk_env() -> dict[str, str]:
    env = os.environ.copy()
    region = env.get("CDK_DEFAULT_REGION") or env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or "us-east-1"
    env["CDK_DEFAULT_REGION"] = region
    env["AWS_REGION"] = region
    env["AWS_DEFAULT_REGION"] = region

    if not env.get("CDK_DEFAULT_ACCOUNT"):
        try:
            venv_python = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python"
            if not venv_python.exists():
                return env

            result = subprocess.run(
                [str(venv_python), "-c", "import boto3; print(boto3.client('sts').get_caller_identity()['Account'])"],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            account = result.stdout.strip()
            env["CDK_DEFAULT_ACCOUNT"] = account
        except Exception:
            pass

    return env


def build_cdk_command(command_name: str) -> list[str]:
    command = ["cdk", command_name]
    if command_name == "deploy":
        command.extend(["--all", "--require-approval", "never"])
    return command


def run_bootstrap(project_dir: Path, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Run `cdk bootstrap` against the resolved AWS account/region.

    Returns the same result contract as run_cdk_command so callers and the GUI
    can treat it uniformly: {command, command_name, return_code, output}.
    """
    effective_env = resolve_cdk_env()
    if env:
        effective_env.update(env)

    account = effective_env.get("CDK_DEFAULT_ACCOUNT", "")
    region = effective_env.get("CDK_DEFAULT_REGION", "us-east-1")

    command = ["cdk", "bootstrap"]
    if account and region:
        command.append(f"aws://{account}/{region}")

    result = exec_code.run_command(command, cwd=str(project_dir), env=effective_env)
    return {
        "command": command,
        "command_name": "bootstrap",
        "return_code": int(result.get("return_code", 1)),
        "output": result.get("output", ""),
    }


def run_cdk_command(project_dir: Path, command_name: str, env: dict[str, str] | None = None) -> dict[str, Any]:
    command = build_cdk_command(command_name)
    effective_env = resolve_cdk_env()
    if env:
        effective_env.update(env)
    result = exec_code.run_command(command, cwd=str(project_dir), env=effective_env)
    return {
        "command": command,
        "command_name": command_name,
        "return_code": int(result.get("return_code", 1)),
        "output": result.get("output", ""),
    }


def run_iac_gate(
    project_dir: Path,
    *,
    cost_delta_usd: float = 0.0,
    aws_config_violations: int = 0,
    use_checkov: bool = True,
    use_cfn_lint: bool = True,
) -> dict[str, Any]:
    gate = IaCSecurityGate()
    cdk_out_dir = project_dir / "cdk.out"
    return gate.evaluate(
        cdk_out_dir,
        cost_delta_usd=cost_delta_usd,
        aws_config_violations=aws_config_violations,
        use_checkov=use_checkov,
        use_cfn_lint=use_cfn_lint,
    )


def can_deploy(
    gate_report: dict[str, Any] | None,
    *,
    manual_review_approved: bool,
) -> tuple[bool, str]:
    if not gate_report:
        return False, "Run cdk synth first to generate a gate report."

    decision = str(gate_report.get("decision", "reject")).lower()
    if decision == "pass":
        return True, "Risk gate passed."
    if decision == "review":
        if manual_review_approved:
            return True, "Manual review approved."
        return False, "Risk gate requires manual review approval."
    return False, "Risk gate rejected this deployment (score > 60)."
