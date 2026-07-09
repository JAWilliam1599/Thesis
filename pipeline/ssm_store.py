"""AWS SSM Parameter Store integration for gate result persistence.

Stores and retrieves the latest gate risk score and decision per stack under:
    /syssecops/gate/{stack_name}/latest_score
    /syssecops/gate/{stack_name}/latest_decision
    /syssecops/gate/{stack_name}/latest_run_id
    /syssecops/gate/{stack_name}/latest_report_path

Configuration via environment variables:
    SSM_ENABLED        — set to "false" to disable all SSM operations (default: enabled)
    AWS_DEFAULT_REGION — region for SSM client (falls back to us-east-1)
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_SSM_PREFIX = "/syssecops/gate"


def _is_enabled() -> bool:
    return os.environ.get("SSM_ENABLED", "true").strip().lower() not in ("false", "0", "no")


def _get_client():
    from pipeline.aws_credentials import get_session

    session = get_session()
    if session is not None:
        return session.client("ssm")
    # Fallback: direct boto3 (reads env vars / ~/.aws/credentials)
    import boto3

    region = (
        os.environ.get("AWS_DEFAULT_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("CDK_DEFAULT_REGION")
        or "us-east-1"
    )
    return boto3.client("ssm", region_name=region)


def write_gate_result(
    stack_name: str,
    run_id: str,
    score: int | float,
    decision: str,
    report_path: str | None,
) -> None:
    """Persist the latest gate result for a stack in SSM Parameter Store.

    Never raises — logs a warning on any failure so the pipeline is never blocked.
    No-ops when SSM_ENABLED=false.
    """
    if not _is_enabled():
        logger.debug("SSM disabled; skipping write_gate_result for stack=%r", stack_name)
        return

    prefix = f"{_SSM_PREFIX}/{stack_name}"
    params = {
        "latest_score": str(score),
        "latest_decision": decision,
        "latest_run_id": run_id,
        "latest_report_path": report_path if report_path else "none",
    }

    try:
        client = _get_client()
        for suffix, value in params.items():
            client.put_parameter(
                Name=f"{prefix}/{suffix}",
                Value=value,
                Type="String",
                Overwrite=True,
            )
        logger.info(
            "SSM: wrote gate result stack=%r run_id=%r decision=%r score=%s",
            stack_name,
            run_id,
            decision,
            score,
        )
    except Exception as exc:
        logger.warning("SSM: write_gate_result failed for stack=%r — %s", stack_name, exc)


def read_gate_result(stack_name: str) -> dict[str, str] | None:
    """Return the latest gate result for a stack from SSM, or None on error / not found.

    Returns a dict with keys: latest_score, latest_decision, latest_run_id, latest_report_path.
    """
    if not _is_enabled():
        logger.debug("SSM disabled; skipping read_gate_result for stack=%r", stack_name)
        return None

    prefix = f"{_SSM_PREFIX}/{stack_name}/"
    try:
        client = _get_client()
        response = client.get_parameters_by_path(Path=prefix)
        parameters = response.get("Parameters", [])
        if not parameters:
            return None

        result: dict[str, str] = {}
        for param in parameters:
            # Extract the suffix after the prefix
            suffix = param["Name"].replace(prefix, "")
            result[suffix] = param["Value"]

        return result or None
    except Exception as exc:
        logger.warning("SSM: read_gate_result failed for stack=%r — %s", stack_name, exc)
        return None


def delete_gate_result(stack_name: str) -> bool:
    """Delete all /syssecops/gate/<stack>/* parameters for a destroyed stack.

    Returns True when the parameters were removed (or none existed).
    Never raises — logs a warning and returns False on failure.
    No-ops (returns True) when SSM_ENABLED=false.
    """
    if not _is_enabled():
        logger.debug("SSM disabled; skipping delete_gate_result for stack=%r", stack_name)
        return True

    prefix = f"{_SSM_PREFIX}/{stack_name}/"
    try:
        client = _get_client()
        paginator = client.get_paginator("get_parameters_by_path")
        names: list[str] = []
        for page in paginator.paginate(Path=prefix, Recursive=True):
            names.extend(p["Name"] for p in page.get("Parameters", []))
        for i in range(0, len(names), 10):  # delete_parameters max batch = 10
            client.delete_parameters(Names=names[i:i + 10])
        logger.info("SSM: deleted %d parameter(s) for stack=%r", len(names), stack_name)
        return True
    except Exception as exc:
        logger.warning("SSM: delete_gate_result failed for stack=%r — %s", stack_name, exc)
        return False


def list_monitored_stacks() -> list[str]:
    """Return all stack names tracked under /syssecops/gate/ in SSM.

    Returns an empty list on error or when SSM_ENABLED=false.
    """
    if not _is_enabled():
        logger.debug("SSM disabled; skipping list_monitored_stacks")
        return []

    try:
        client = _get_client()
        paginator = client.get_paginator("get_parameters_by_path")
        stack_names: set[str] = set()

        for page in paginator.paginate(Path=f"{_SSM_PREFIX}/", Recursive=True):
            for param in page.get("Parameters", []):
                # Path format: /syssecops/gate/{stack_name}/latest_*
                parts = param["Name"].split("/")
                # parts: ['', 'syssecops', 'gate', '{stack_name}', 'latest_*']
                if len(parts) >= 5:
                    stack_names.add(parts[3])

        return sorted(stack_names)
    except Exception as exc:
        logger.warning("SSM: list_monitored_stacks failed — %s", exc)
        return []
