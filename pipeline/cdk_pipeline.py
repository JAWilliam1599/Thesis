from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
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


def clear_cdk_out(project_dir: Path) -> None:
    """Delete all synthesized CloudFormation template files from cdk.out.

    Removes only *.template.json files (and manifest.json / tree.json) so that
    stale templates from a previous app.py generation are never picked up by the
    gate or any scanner on the next synth.  The directory itself is preserved so
    CDK does not need to recreate it.

    Safe to call before every `cdk synth` — CDK always regenerates the full
    output regardless.
    """
    import shutil

    cdk_out = project_dir / "cdk.out"
    if not cdk_out.is_dir():
        return
    for item in cdk_out.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except Exception:
            pass  # best-effort; synth will overwrite anyway


def run_iac_gate(
    project_dir: Path,
    *,
    cost_delta_usd: float | None = None,
    aws_config_violations: int | None = None,
    use_checkov: bool = True,
    use_cfn_lint: bool = True,
    use_infracost: bool = True,
    use_aws_config: bool = True,
    run_id: str | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    if run_id is None:
        run_id = f"cdk_{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    gate = IaCSecurityGate()
    cdk_out_dir = project_dir / "cdk.out"
    return gate.evaluate(
        cdk_out_dir,
        cost_delta_usd=cost_delta_usd,
        aws_config_violations=aws_config_violations,
        use_checkov=use_checkov,
        use_cfn_lint=use_cfn_lint,
        use_infracost=use_infracost,
        use_aws_config=use_aws_config,
        run_id=run_id,
        region=region,
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


_DEFAULT_GATE_REPORTS_DIR = Path(__file__).resolve().parents[1] / "logs" / "gate_reports"
_DEFAULT_APPROVALS_DIR = Path(__file__).resolve().parents[1] / "logs" / "approvals"
_DEFAULT_REJECTIONS_DIR = Path(__file__).resolve().parents[1] / "logs" / "rejections"


def extract_stack_name(gate_report: dict[str, Any]) -> str:
    """Derive a stack name from a gate report.

    Uses the first template filename in gate_report["inputs"]["templates"],
    stripping the ".template.json" suffix.  Falls back to the run_id if no
    templates are present.
    """
    templates: list[str] = (gate_report.get("inputs") or {}).get("templates") or []
    if templates:
        name = templates[0]
        for suffix in (".template.json", ".json"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        # Strip any leading directory components returned in some CDK versions
        return Path(name).name
    return gate_report.get("run_id") or "unknown"


def load_gate_report(run_id: str, log_dir: Path | None = None) -> dict[str, Any]:
    """Load a persisted gate report by run_id.

    Raises FileNotFoundError if the report file does not exist.
    """
    report_dir = Path(log_dir) if log_dir else _DEFAULT_GATE_REPORTS_DIR
    report_path = report_dir / f"gate_{run_id}.json"
    if not report_path.exists():
        raise FileNotFoundError(
            f"Gate report not found for run_id '{run_id}': {report_path}\n"
            "Run the full pipeline first to generate a report."
        )
    return json.loads(report_path.read_text(encoding="utf-8"))


def _get_caller_identity() -> dict[str, str | None]:
    """Return AWS caller ARN and account via the AWS CLI subprocess.

    Uses the CLI rather than boto3 directly so that it honours the same
    credential chain as the rest of the CDK tooling (profiles, SSO, etc.)
    Falls back to null values if the CLI call fails or is unavailable.
    """
    try:
        result = subprocess.run(
            ["aws", "sts", "get-caller-identity", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            import json as _json
            identity = _json.loads(result.stdout)
            return {
                "arn": identity.get("Arn"),
                "account": identity.get("Account"),
            }
    except Exception:
        pass
    return {"arn": None, "account": None}


def write_approval(
    run_id: str,
    gate_report: dict[str, Any],
    approver: str = "cli",
    log_dir: Path | None = None,
) -> str:
    """Persist an approval record for a review-band gate report.

    Returns the path of the written approval JSON file.
    """
    approvals_dir = Path(log_dir) if log_dir else _DEFAULT_APPROVALS_DIR
    approvals_dir.mkdir(parents=True, exist_ok=True)
    approval_path = approvals_dir / f"approval_{run_id}.json"
    identity = _get_caller_identity()
    record = {
        "run_id": run_id,
        "approved_at": datetime.now(tz=timezone.utc).isoformat(),
        "approver": approver,
        "approver_arn": identity["arn"],
        "approver_account": identity["account"],
        "gate_decision": gate_report.get("decision"),
        "gate_score": gate_report.get("score"),
        "gate_report_path": gate_report.get("report_path"),
    }
    approval_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return str(approval_path)


def write_rejection_record(
    run_id: str,
    gate_report: dict[str, Any],
    log_dir: Path | None = None,
) -> str:
    """Persist a rejection record for an auto-rejected or blocked gate report.

    Returns the path of the written rejection JSON file.
    """
    rejections_dir = Path(log_dir) if log_dir else _DEFAULT_REJECTIONS_DIR
    rejections_dir.mkdir(parents=True, exist_ok=True)
    rejection_path = rejections_dir / f"rejection_{run_id}.json"
    identity = _get_caller_identity()
    top_findings = (gate_report.get("findings") or [])[:5]
    record = {
        "run_id": run_id,
        "rejected_at": datetime.now(tz=timezone.utc).isoformat(),
        "gate_decision": gate_report.get("decision"),
        "gate_score": gate_report.get("score"),
        "gate_report_path": gate_report.get("report_path"),
        "top_findings": top_findings,
        "rejector_arn": identity["arn"],
        "rejector_account": identity["account"],
    }
    rejection_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return str(rejection_path)