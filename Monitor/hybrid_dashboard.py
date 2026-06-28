"""Hybrid CloudWatch dashboard: AWS <-> on-prem visibility in one pane.

Creates a CloudWatch dashboard (via ``put_dashboard``) that surfaces:
    - Risk score per target (CDK stacks + ansible-<node>) from SysSecOps/Gate.
    - Gate decision trend per target.
    - EC2 network flow (packets in/out) as a proxy for AWS<->on-prem traffic.
    - A text panel summarising the hybrid mesh and where to find node health.

This is the AWS-native dashboard option (thesis "Model B" custom panel lives in
the UI later).  It is CLI-driven so it can be created/updated without deploying
a CDK stack.

CLI:
    python -m Monitor.hybrid_dashboard --create \
        --targets HybridDemoStack ansible-site
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

_NAMESPACE = "SysSecOps/Gate"
_DEFAULT_DASHBOARD = "SysSecOps-Hybrid"


def _get_region() -> str:
    return (
        os.environ.get("AWS_DEFAULT_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("CDK_DEFAULT_REGION")
        or "us-east-1"
    )


def _get_client(service: str):
    from pipeline.aws_credentials import get_session

    session = get_session()
    if session is not None:
        return session.client(service)
    import boto3

    return boto3.client(service, region_name=_get_region())


def build_dashboard_body(targets: list[str], region: str) -> dict:
    """Return the CloudWatch dashboard JSON body for the given gate targets."""
    score_metrics = [[_NAMESPACE, "GateScore", "StackName", t] for t in targets]
    decision_metrics = [[_NAMESPACE, "GateDecision", "StackName", t] for t in targets]

    widgets = [
        {
            "type": "text",
            "x": 0, "y": 0, "width": 24, "height": 2,
            "properties": {
                "markdown": (
                    "# SysSecOps Hybrid Dashboard\n"
                    "Risk score & decision per target (CDK + on-prem Ansible). "
                    "On-prem node health: **SSM Fleet Manager**. "
                    "Mesh connectivity: **Tailscale admin console**."
                )
            },
        },
        {
            "type": "metric",
            "x": 0, "y": 2, "width": 12, "height": 6,
            "properties": {
                "title": "Risk score per target",
                "view": "timeSeries",
                "region": region,
                "metrics": score_metrics or [[_NAMESPACE, "GateScore"]],
                "yAxis": {"left": {"min": 0}},
                "annotations": {"horizontal": [
                    {"label": "auto-pass", "value": 20},
                    {"label": "auto-reject", "value": 80},
                ]},
            },
        },
        {
            "type": "metric",
            "x": 12, "y": 2, "width": 12, "height": 6,
            "properties": {
                "title": "Gate decision (0=pass 1=review 2=reject)",
                "view": "timeSeries",
                "region": region,
                "metrics": decision_metrics or [[_NAMESPACE, "GateDecision"]],
                "yAxis": {"left": {"min": 0, "max": 2}},
            },
        },
        {
            "type": "metric",
            "x": 0, "y": 8, "width": 24, "height": 6,
            "properties": {
                "title": "AWS network flow (EC2 packets in/out)",
                "view": "timeSeries",
                "region": region,
                "metrics": [
                    ["AWS/EC2", "NetworkPacketsIn"],
                    ["AWS/EC2", "NetworkPacketsOut"],
                ],
            },
        },
    ]
    return {"widgets": widgets}


def create_dashboard(targets: list[str], name: str = _DEFAULT_DASHBOARD) -> dict:
    """Create or update the hybrid dashboard. Returns the AWS response."""
    region = _get_region()
    body = build_dashboard_body(targets, region)
    cw = _get_client("cloudwatch")
    return cw.put_dashboard(DashboardName=name, DashboardBody=json.dumps(body))


def _main() -> int:
    parser = argparse.ArgumentParser(description="Create the SysSecOps hybrid CloudWatch dashboard.")
    parser.add_argument("--create", action="store_true", help="Create/update the dashboard.")
    parser.add_argument("--name", default=_DEFAULT_DASHBOARD, help="Dashboard name.")
    parser.add_argument("--targets", nargs="*", default=[], help="Gate target names (CDK stacks + ansible-<node>).")
    args = parser.parse_args()

    if not args.create:
        parser.print_help()
        return 0

    try:
        create_dashboard(args.targets, name=args.name)
    except Exception as exc:
        print(f"ERROR: could not create dashboard — {exc}")
        return 1
    print(f"Dashboard '{args.name}' created/updated in {_get_region()} with targets: {args.targets or '(none)'}")
    return 0


if __name__ == "__main__":
    from env_bootstrap import load_env

    load_env()
    raise SystemExit(_main())
