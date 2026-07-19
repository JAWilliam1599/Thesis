"""SSM Hybrid Activation for on-prem nodes (Tailscale-connected private nodes).

Registers a private node as an AWS Systems Manager *managed instance* (mi-*) so
the same operational loop used for EC2 — Run Command, State Manager associations
(OS-level drift), Patch Manager, Inventory, and compliance events — also covers
the on-prem side of the hybrid system.  Compliance changes flow to EventBridge
and reuse the existing ops-loop Lambda; no separate agent stack is required.

Workflow:
    1. ensure_hybrid_role()  — create the IAM service role the agent assumes.
    2. create_activation()   — create an activation (ActivationId + Code).
    3. registration_command()— print the one-liner to run on the private node.

CLI:
    python -m monitoring.ssm_hybrid --create --name onprem-web --limit 1

All AWS calls are best-effort and surfaced via return values / printed output;
this module never provisions anything implicitly beyond what is requested.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

_DEFAULT_ROLE_NAME = "SysSecOpsHybridRole"
_MANAGED_POLICY = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
_ASSUME_ROLE_DOC = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": "ssm.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }
    ],
}


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


def ensure_hybrid_role(role_name: str = _DEFAULT_ROLE_NAME) -> str:
    """Create (or reuse) the IAM role the SSM agent assumes on the on-prem node.

    Returns the role name.  Idempotent — returns the existing role if present.
    """
    import json

    iam = _get_client("iam")
    try:
        iam.get_role(RoleName=role_name)
        return role_name
    except Exception:
        pass

    iam.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(_ASSUME_ROLE_DOC),
        Description="SysSecOps hybrid activation role for on-prem managed nodes.",
    )
    iam.attach_role_policy(RoleName=role_name, PolicyArn=_MANAGED_POLICY)
    return role_name


def create_activation(
    *,
    name: str,
    role_name: str = _DEFAULT_ROLE_NAME,
    registration_limit: int = 1,
    description: str = "SysSecOps on-prem hybrid node",
) -> dict[str, Any]:
    """Create an SSM hybrid activation and return its details.

    Returns: {activation_id, activation_code, region, role_name}
    """
    ensure_hybrid_role(role_name)
    ssm = _get_client("ssm")
    resp = ssm.create_activation(
        Description=description,
        DefaultInstanceName=name,
        IamRole=role_name,
        RegistrationLimit=registration_limit,
    )
    return {
        "activation_id": resp["ActivationId"],
        "activation_code": resp["ActivationCode"],
        "region": _get_region(),
        "role_name": role_name,
    }


def registration_command(activation: dict[str, Any]) -> str:
    """Return the shell command to register the on-prem node with SSM.

    Run this on the private node (Ubuntu/RPi) once the SSM agent is installed
    and the node is reachable over Tailscale.
    """
    return (
        "sudo amazon-ssm-agent -register -y "
        f"-code \"{activation['activation_code']}\" "
        f"-id \"{activation['activation_id']}\" "
        f"-region \"{activation['region']}\""
    )


def install_and_register_snippet(activation: dict[str, Any]) -> str:
    """Return a full install+register snippet for a Debian/Ubuntu private node."""
    return "\n".join(
        [
            "# Run on the on-prem node (Ubuntu/Debian), reachable via Tailscale:",
            "mkdir -p /tmp/ssm && cd /tmp/ssm",
            "curl -s https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/debian_amd64/amazon-ssm-agent.deb -o amazon-ssm-agent.deb",
            "sudo dpkg -i amazon-ssm-agent.deb",
            "sudo service amazon-ssm-agent stop",
            registration_command(activation),
            "sudo service amazon-ssm-agent start",
        ]
    )


def _main() -> int:
    parser = argparse.ArgumentParser(description="Create an SSM hybrid activation for an on-prem node.")
    parser.add_argument("--create", action="store_true", help="Create a new activation.")
    parser.add_argument("--name", default="onprem-node", help="Default instance name for the managed node.")
    parser.add_argument("--role-name", default=_DEFAULT_ROLE_NAME, help="IAM role name for the SSM agent.")
    parser.add_argument("--limit", type=int, default=1, help="Registration limit (number of nodes).")
    args = parser.parse_args()

    if not args.create:
        parser.print_help()
        return 0

    try:
        activation = create_activation(name=args.name, role_name=args.role_name, registration_limit=args.limit)
    except Exception as exc:
        print(f"ERROR: could not create activation — {exc}")
        return 1

    print("Hybrid activation created:")
    print(f"  ActivationId:   {activation['activation_id']}")
    print(f"  ActivationCode: {activation['activation_code']}")
    print(f"  Region:         {activation['region']}")
    print(f"  IAM Role:       {activation['role_name']}")
    print("\nRegister the on-prem node with:\n")
    print(install_and_register_snippet(activation))
    return 0


if __name__ == "__main__":
    from env_bootstrap import load_env

    load_env()
    raise SystemExit(_main())
