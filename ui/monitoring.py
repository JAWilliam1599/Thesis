"""AWS-backed monitoring reads for the Monitor tab.

All functions degrade gracefully: when credentials are missing or a call
fails, they return an empty result plus a short status string rather than
raising, so the GUI stays responsive without AWS access.
"""
from __future__ import annotations

import os
from typing import Any

from ui import config, credentials


def _region() -> str:
    creds = credentials.load_credentials()
    return creds.get("region") or config.DEFAULT_REGION


def _client(service: str):
    """Build a boto3 client using stored credentials, or return (None, error)."""
    creds = credentials.load_credentials()
    if not (creds.get("access_key") and creds.get("secret_key")):
        return None, "AWS credentials not configured."
    try:
        import boto3
    except ImportError:
        return None, "boto3 is not installed."
    try:
        session = boto3.Session(
            aws_access_key_id=creds["access_key"],
            aws_secret_access_key=creds["secret_key"],
            aws_session_token=creds.get("session_token") or None,
            region_name=creds.get("region") or config.DEFAULT_REGION,
        )
        return session.client(service), ""
    except Exception as exc:  # noqa: BLE001
        return None, _short(exc)


# --- SSM gate status --------------------------------------------------------
def list_stack_statuses() -> tuple[list[dict[str, Any]], str]:
    """Return latest gate status per monitored stack from SSM Parameter Store."""
    client, error = _client("ssm")
    if client is None:
        return [], error

    prefix = config.SSM_GATE_PREFIX + "/"
    try:
        paginator = client.get_paginator("get_parameters_by_path")
        # stack -> {suffix: value}
        stacks: dict[str, dict[str, str]] = {}
        for page in paginator.paginate(Path=prefix, Recursive=True):
            for param in page.get("Parameters", []):
                parts = param["Name"].split("/")
                # /syssecops/gate/{stack}/latest_*
                if len(parts) >= 5:
                    stack = parts[3]
                    suffix = parts[4]
                    stacks.setdefault(stack, {})[suffix] = param["Value"]
        rows = [
            {
                "stack": stack,
                "score": vals.get("latest_score", "—"),
                "decision": vals.get("latest_decision", "—"),
                "run_id": vals.get("latest_run_id", "—"),
            }
            for stack, vals in sorted(stacks.items())
        ]
        return rows, ""
    except Exception as exc:  # noqa: BLE001
        return [], _short(exc)


# --- CloudWatch alarms ------------------------------------------------------
def list_alarms() -> tuple[list[dict[str, Any]], str]:
    """Return SysSecOps CloudWatch alarms with their current state."""
    client, error = _client("cloudwatch")
    if client is None:
        return [], error

    try:
        paginator = client.get_paginator("describe_alarms")
        rows: list[dict[str, Any]] = []
        for page in paginator.paginate(AlarmNamePrefix=config.ALARM_NAME_PREFIX):
            for alarm in page.get("MetricAlarms", []):
                updated = alarm.get("StateUpdatedTimestamp")
                rows.append({
                    "name": alarm.get("AlarmName", ""),
                    "state": alarm.get("StateValue", "INSUFFICIENT_DATA"),
                    "metric": alarm.get("MetricName", ""),
                    "updated": updated.strftime("%Y-%m-%d %H:%M:%S") if updated else "—",
                })
        state_rank = {"ALARM": 0, "INSUFFICIENT_DATA": 1, "OK": 2}
        rows.sort(key=lambda r: state_rank.get(r["state"], 3))
        return rows, ""
    except Exception as exc:  # noqa: BLE001
        return [], _short(exc)


# --- CloudWatch gate metrics ------------------------------------------------
def get_gate_metric_average(metric_name: str, hours: int = 168) -> tuple[float | None, str]:
    """Return the average of a SysSecOps/Gate metric over the last N hours."""
    client, error = _client("cloudwatch")
    if client is None:
        return None, error

    from datetime import datetime, timedelta, timezone

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    try:
        response = client.get_metric_statistics(
            Namespace=config.CLOUDWATCH_NAMESPACE,
            MetricName=metric_name,
            StartTime=start,
            EndTime=end,
            Period=3600,
            Statistics=["Average"],
        )
        points = response.get("Datapoints", [])
        if not points:
            return None, "No datapoints."
        avg = sum(p["Average"] for p in points) / len(points)
        return round(avg, 2), ""
    except Exception as exc:  # noqa: BLE001
        return None, _short(exc)


def _short(exc: Exception) -> str:
    msg = str(exc)
    return msg if len(msg) <= 200 else msg[:197] + "..."
