from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.cdk_pipeline import can_deploy, run_bootstrap, run_cdk_command, run_iac_gate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CDK pipeline with IaC risk gate.")
    parser.add_argument("--project-dir", default="GeneratedCDK", help="CDK project directory.")
    parser.add_argument("--run-id", default=None, help="Override auto-generated run ID (used for gate report filename).")
    parser.add_argument("--cost-delta-usd", type=float, default=None, help="Override Infracost cost delta in USD (default: auto-detect via infracost).")
    parser.add_argument("--aws-config-violations", type=int, default=None, help="Override AWS Config violations count (default: auto-fetch via boto3).")
    parser.add_argument("--no-infracost", action="store_true", help="Skip infracost cost analysis.")
    parser.add_argument("--no-aws-config", action="store_true", help="Skip AWS Config violations fetch.")
    parser.add_argument("--manual-approve", action="store_true", help="Approve review decision (21-60) for deploy.")
    parser.add_argument("--deploy", action="store_true", help="Run deploy if gate allows.")
    parser.add_argument("--bootstrap", action="store_true", help="Run cdk bootstrap before synth (required for first deploy).")
    parser.add_argument("--no-checkov", action="store_true", help="Skip checkov scan (useful for fast-path testing).")
    parser.add_argument("--no-cfn-lint", action="store_true", help="Skip cfn-lint scan (useful for fast-path testing).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = Path(args.project_dir).resolve()

    if not project_dir.exists():
        print(f"ERROR: project directory not found: {project_dir}")
        return 2

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    if args.bootstrap:
        bootstrap = run_bootstrap(project_dir, env=env)
        print(json.dumps({"stage": "bootstrap", **bootstrap}, indent=2))
        if bootstrap["return_code"] != 0:
            return 9

    synth = run_cdk_command(project_dir, "synth", env=env)
    print(json.dumps({"stage": "synth", **synth}, indent=2))
    if synth["return_code"] != 0:
        return 10

    gate_report = run_iac_gate(
        project_dir,
        cost_delta_usd=args.cost_delta_usd,
        aws_config_violations=args.aws_config_violations,
        use_checkov=not args.no_checkov,
        use_cfn_lint=not args.no_cfn_lint,
        use_infracost=not args.no_infracost,
        use_aws_config=not args.no_aws_config,
        run_id=args.run_id,
    )
    print(json.dumps({"stage": "gate", "gate": gate_report}, indent=2))
    report_path = gate_report.get("report_path")
    if report_path:
        print(json.dumps({"stage": "gate_report", "path": report_path}, indent=2))

    diff = run_cdk_command(project_dir, "diff", env=env)
    print(json.dumps({"stage": "diff", **diff}, indent=2))
    if diff["return_code"] != 0:
        return 11

    allowed, reason = can_deploy(gate_report, manual_review_approved=args.manual_approve)
    print(json.dumps({"stage": "decision", "allowed": allowed, "reason": reason}, indent=2))

    if not allowed:
        if str(gate_report.get("decision", "")).lower() == "review":
            return 21
        return 22

    if not args.deploy:
        return 0

    deploy = run_cdk_command(project_dir, "deploy", env=env)
    print(json.dumps({"stage": "deploy", **deploy}, indent=2))
    return 0 if deploy["return_code"] == 0 else 12


if __name__ == "__main__":
    raise SystemExit(main())
