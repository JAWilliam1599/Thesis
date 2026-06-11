from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.cdk_pipeline import can_deploy, run_cdk_command, run_iac_gate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CDK pipeline with IaC risk gate.")
    parser.add_argument("--project-dir", default="GeneratedCDK", help="CDK project directory.")
    parser.add_argument("--cost-delta-usd", type=float, default=0.0, help="Optional Infracost delta in USD.")
    parser.add_argument("--aws-config-violations", type=int, default=0, help="Optional AWS Config violations count.")
    parser.add_argument("--manual-approve", action="store_true", help="Approve review decision (21-60) for deploy.")
    parser.add_argument("--deploy", action="store_true", help="Run deploy if gate allows.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = Path(args.project_dir).resolve()

    if not project_dir.exists():
        print(f"ERROR: project directory not found: {project_dir}")
        return 2

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    synth = run_cdk_command(project_dir, "synth", env=env)
    print(json.dumps({"stage": "synth", **synth}, indent=2))
    if synth["return_code"] != 0:
        return 10

    gate_report = run_iac_gate(
        project_dir,
        cost_delta_usd=args.cost_delta_usd,
        aws_config_violations=args.aws_config_violations,
    )
    print(json.dumps({"stage": "gate", "gate": gate_report}, indent=2))

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
