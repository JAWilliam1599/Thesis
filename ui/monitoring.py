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


# --- CloudFormation stacks & resources ---------------------------------------
_ACTIVE_STACK_STATUSES = [
    "CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE",
    "ROLLBACK_COMPLETE", "IMPORT_COMPLETE",
]


def list_cfn_stacks() -> tuple[list[str], str]:
    """Names of active CloudFormation stacks in the configured region."""
    client, error = _client("cloudformation")
    if client is None:
        return [], error
    try:
        paginator = client.get_paginator("list_stacks")
        names: list[str] = []
        for page in paginator.paginate(StackStatusFilter=_ACTIVE_STACK_STATUSES):
            for summary in page.get("StackSummaries", []):
                if summary.get("ParentId"):
                    continue  # skip nested stacks
                names.append(summary["StackName"])
        return sorted(set(names)), ""
    except Exception as exc:  # noqa: BLE001
        return [], _short(exc)


def list_stack_resources(stack_name: str) -> tuple[list[dict[str, Any]], str]:
    """Resources of one CloudFormation stack (logical id, type, physical id, status)."""
    client, error = _client("cloudformation")
    if client is None:
        return [], error
    try:
        paginator = client.get_paginator("list_stack_resources")
        rows: list[dict[str, Any]] = []
        for page in paginator.paginate(StackName=stack_name):
            for res in page.get("StackResourceSummaries", []):
                rows.append({
                    "logical_id": res.get("LogicalResourceId", ""),
                    "type": res.get("ResourceType", ""),
                    "physical_id": res.get("PhysicalResourceId", ""),
                    "status": res.get("ResourceStatus", ""),
                })
        return rows, ""
    except Exception as exc:  # noqa: BLE001
        return [], _short(exc)


# --- Per-resource CloudWatch metrics -----------------------------------------
# Resource type -> (metrics namespace, dimension name, [(metric, stat, unit label)])
RESOURCE_METRICS: dict[str, tuple[str, str, list[tuple[str, str, str]]]] = {
    "AWS::EC2::Instance": ("AWS/EC2", "InstanceId", [
        ("CPUUtilization", "Average", "%"),
        ("NetworkPacketsIn", "Sum", "packets"),
        ("StatusCheckFailed", "Maximum", "failed"),
    ]),
    "AWS::Lambda::Function": ("AWS/Lambda", "FunctionName", [
        ("Invocations", "Sum", "count"),
        ("Errors", "Sum", "count"),
        ("Duration", "Average", "ms"),
    ]),
    "AWS::RDS::DBInstance": ("AWS/RDS", "DBInstanceIdentifier", [
        ("CPUUtilization", "Average", "%"),
        ("DatabaseConnections", "Average", "count"),
        ("FreeStorageSpace", "Average", "bytes"),
    ]),
    "AWS::ECS::Service": ("AWS/ECS", "ServiceName", [
        ("CPUUtilization", "Average", "%"),
        ("MemoryUtilization", "Average", "%"),
    ]),
}


def get_metric_series(
    namespace: str,
    metric_name: str,
    dimension_name: str,
    dimension_value: str,
    stat: str = "Average",
    hours: int = 24,
) -> tuple[list[dict[str, Any]], str]:
    """Hourly datapoints for one metric, oldest first: [{time, value}]."""
    client, error = _client("cloudwatch")
    if client is None:
        return [], error

    from datetime import datetime, timedelta, timezone

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    try:
        response = client.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=[{"Name": dimension_name, "Value": dimension_value}],
            StartTime=start,
            EndTime=end,
            Period=3600,
            Statistics=[stat],
        )
        points = sorted(response.get("Datapoints", []), key=lambda p: p["Timestamp"])
        return (
            [{"time": p["Timestamp"], "value": p.get(stat, 0.0)} for p in points],
            "",
        )
    except Exception as exc:  # noqa: BLE001
        return [], _short(exc)


# --- Console deep links -------------------------------------------------------
def cloudwatch_dashboard_url(name: str) -> str:
    region = _region()
    return (
        f"https://{region}.console.aws.amazon.com/cloudwatch/home"
        f"?region={region}#dashboards:name={name}"
    )


def cloudwatch_automatic_dashboards_url() -> str:
    region = _region()
    return (
        f"https://{region}.console.aws.amazon.com/cloudwatch/home"
        f"?region={region}#home:dashboards"
    )


def cloudformation_stack_url(stack_name: str) -> str:
    region = _region()
    return (
        f"https://{region}.console.aws.amazon.com/cloudformation/home"
        f"?region={region}#/stacks?filteringText={stack_name}"
    )


# --- On-prem / hybrid mesh status ---------------------------------------------
def get_hybrid_status() -> tuple[dict[str, Any], str]:
    """SSM managed nodes + compliance + Tailscale devices (graceful on failure).

    Exports the stored Tailscale settings into the process env first so the
    shared pipeline collector can use them.
    """
    creds = credentials.load_credentials()
    if creds.get("tailscale_key"):
        os.environ.setdefault("TAILSCALE_API_KEY", creds["tailscale_key"])
    if creds.get("tailscale_tailnet"):
        os.environ.setdefault("TAILSCALE_TAILNET", creds["tailscale_tailnet"])
    try:
        from pipeline.hybrid_status import collect_hybrid_status

        return collect_hybrid_status(), ""
    except Exception as exc:  # noqa: BLE001
        return {}, _short(exc)
