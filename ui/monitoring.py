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

# Infrastructure / bootstrap stacks that are not user-deployed workloads and so
# are hidden from the Monitor tab's stack selector:
#   CDKToolkit                 — the CDK bootstrap stack
#   SysSecOpsCloudTrailStack   — shared account-wide CloudTrail for the pipeline
#   SysSecOpsLoopStack         — the ops/monitoring control-loop stack
# ("ApplicationInsights-*" helper stacks are filtered separately by prefix.)
_HIDDEN_STACKS = {
    "cdktoolkit",
    "syssecopscloudtrailstack",
    "syssecopsopsloopstack",
}


def list_cfn_stacks() -> tuple[list[str], str]:
    """Names of active CloudFormation stacks in the configured region.

    Auxiliary stacks that are not user-deployed workloads are hidden:
    ``ApplicationInsights-*`` (CloudWatch Application Insights helpers) and the
    infrastructure/bootstrap stacks in :data:`_HIDDEN_STACKS` (CDKToolkit,
    SysSecOpsCloudTrailStack, SysSecOpsLoopStack).
    """
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
                name = summary["StackName"]
                if name.startswith("ApplicationInsights-"):
                    continue  # AWS-managed monitoring helper stack
                if name.lower() in _HIDDEN_STACKS:
                    continue  # bootstrap / shared infrastructure stack
                names.append(name)
        return sorted(set(names)), ""
    except Exception as exc:  # noqa: BLE001
        return [], _short(exc)


def list_monitoring_apps() -> tuple[list[dict[str, Any]], str]:
    """CloudWatch Application Insights apps mapped to the stack they monitor.

    The pipeline registers each deployed stack under resource group
    ``syssecops-<stack>``, so the monitored stack is recoverable from the
    group name.

    Application Insights apps are independent AWS resources: deleting a stack
    outside the app's cascade delete leaves them orphaned. To avoid showing
    stale entries, apps are cross-referenced against the live stack list — only
    apps whose monitored stack still exists (and isn't a hidden infra stack)
    are returned.
    """
    client, error = _client("application-insights")
    if client is None:
        return [], error

    live_stacks, _ = list_cfn_stacks()
    live_lower = {s.lower() for s in live_stacks}
    try:
        rows: list[dict[str, Any]] = []
        next_token: str | None = None
        while True:
            kwargs = {"NextToken": next_token} if next_token else {}
            page = client.list_applications(**kwargs)
            for app in page.get("ApplicationInfoList", []):
                group = app.get("ResourceGroupName", "")
                monitored = group[len("syssecops-"):] if group.startswith("syssecops-") else "—"
                # Hide orphaned apps whose stack was deleted, hidden infra
                # stacks, and any app not tied to a live syssecops-<stack>.
                if monitored == "—" or monitored.lower() not in live_lower:
                    continue
                rows.append({
                    "resource_group": group,
                    "monitored_stack": monitored,
                    "lifecycle": app.get("LifeCycle", "—"),
                    "auto_config": app.get("AutoConfigEnabled", False),
                })
            next_token = page.get("NextToken")
            if not next_token:
                break
        rows.sort(key=lambda r: r["monitored_stack"])
        return rows, ""
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
    period: int = 3600,
) -> tuple[list[dict[str, Any]], str]:
    """Datapoints for one metric, oldest first: [{time, value}]."""
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
            Period=period,
            Statistics=[stat],
        )
        points = sorted(response.get("Datapoints", []), key=lambda p: p["Timestamp"])
        return (
            [{"time": p["Timestamp"], "value": p.get(stat, 0.0)} for p in points],
            "",
        )
    except Exception as exc:  # noqa: BLE001
        return [], _short(exc)


# Gate dashboard metrics (mirrors the SysSecOpsGate CloudWatch dashboard).
# Statistic + period match the deployed dashboard (Monitor/ops_loop_stack.py) so
# in-app values line up with the CloudWatch console.
GATE_DASHBOARD_METRICS: list[tuple[str, str, str]] = [
    ("GateScore", "Maximum", "score"),
    ("GateDecision", "Maximum", "0=pass 1=review 2=reject"),
    ("CriticalFindings", "Sum", "count"),
    ("HighFindings", "Sum", "count"),
    ("MLRiskScore", "Maximum", "points"),
]

# EC2 network-flow metrics (mirrors the SysSecOps-Hybrid dashboard panels).
NETWORK_FLOW_METRICS: list[tuple[str, str, str]] = [
    ("NetworkPacketsIn", "Sum", "packets"),
    ("NetworkPacketsOut", "Sum", "packets"),
]


def get_gate_metric_series(
    stack_name: str,
    metric_name: str,
    stat: str = "Average",
    hours: int = 168,
) -> tuple[list[dict[str, Any]], str]:
    """Datapoints of a SysSecOps/Gate metric for one stack (StackName dim).

    Uses a 5-minute period to match the deployed SysSecOpsGate dashboard.
    """
    return get_metric_series(
        config.CLOUDWATCH_NAMESPACE,
        metric_name,
        "StackName",
        stack_name,
        stat=stat,
        hours=hours,
        period=300,
    )


# --- Console deep links -------------------------------------------------------
def cloudwatch_dashboard_url(name: str) -> str:
    region = _region()
    return (
        f"https://{region}.console.aws.amazon.com/cloudwatch/home"
        f"?region={region}#dashboards/dashboard/{name}"
    )


def dashboard_exists(name: str) -> bool:
    """True if a CloudWatch dashboard with this exact name exists."""
    client, error = _client("cloudwatch")
    if client is None:
        return False
    try:
        paginator = client.get_paginator("list_dashboards")
        for page in paginator.paginate():
            for entry in page.get("DashboardEntries", []):
                if entry.get("DashboardName") == name:
                    return True
        return False
    except Exception:  # noqa: BLE001
        return False


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


# --- Stack deletion (cascade) ---------------------------------------------------
def destroy_stack(stack_name: str) -> tuple[dict[str, Any], str]:
    """Delete a stack AND every related monitoring artifact.

    Order matters: monitoring artifacts (alarms, metric filters, Application
    Insights app + its auto-created helper stack, resource group, gate log
    group, SSM parameters) are removed first, then CloudFormation stack
    deletion is initiated (asynchronous — the stack transitions to
    DELETE_IN_PROGRESS).

    Returns ``(summary, error)``; ``error`` is non-empty only when the
    CloudFormation deletion itself could not be started.
    """
    from Monitor.stack_monitor import teardown_stack_monitoring

    summary = teardown_stack_monitoring(stack_name)

    client, error = _client("cloudformation")
    if client is None:
        summary["stack_delete_started"] = False
        return summary, error
    try:
        client.delete_stack(StackName=stack_name)
        summary["stack_delete_started"] = True
        return summary, ""
    except Exception as exc:  # noqa: BLE001
        summary["stack_delete_started"] = False
        return summary, _short(exc)


def get_stack_status(stack_name: str) -> tuple[str, str]:
    """Current CloudFormation status of a stack ('' when it no longer exists)."""
    client, error = _client("cloudformation")
    if client is None:
        return "", error
    try:
        response = client.describe_stacks(StackName=stack_name)
        stacks = response.get("Stacks", [])
        return (stacks[0]["StackStatus"] if stacks else ""), ""
    except Exception as exc:  # noqa: BLE001
        if "does not exist" in str(exc):
            return "", ""
        return "", _short(exc)


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
