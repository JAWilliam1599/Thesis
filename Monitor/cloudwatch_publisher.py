"""CloudWatch custom metrics and structured log publisher for gate evaluations.

Publishes per-gate-run metrics and the full gate report as a structured log
event so CloudWatch dashboards and alarms can surface gate health in real time.

Metrics published (namespace: SysSecOps/Gate):
    GateScore         — numeric risk score
    GateDecision      — 0=pass, 1=review, 2=reject
    CriticalFindings  — count of critical-severity findings
    HighFindings      — count of high-severity findings
    MLRiskScore       — logistic-regression component (0-20; omitted when N/A)

Dimensions: StackName + RunId

Log group / stream:
    /syssecops/gate/{stack_name}  (log group)
    {run_id}                      (log stream)

Configuration via environment variables:
    AWS_DEFAULT_REGION — region for CloudWatch client (falls back to us-east-1)
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_NAMESPACE = "SysSecOps/Gate"
_DECISION_MAP = {"pass": 0, "review": 1, "reject": 2}


def _get_region() -> str:
    return (
        os.environ.get("AWS_DEFAULT_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("CDK_DEFAULT_REGION")
        or "us-east-1"
    )


def _get_client(service: str):
    """Return a boto3 service client using the shared aws_credentials session."""
    from pipeline.aws_credentials import get_session

    session = get_session()
    if session is not None:
        return session.client(service)
    import boto3
    return boto3.client(service, region_name=_get_region())


def publish_gate_metrics(
    stack_name: str,
    run_id: str,
    score: int | float,
    decision: str,
    findings: list[dict[str, Any]] | None,
    ml_score: int | float | None = None,
) -> None:
    """Publish gate evaluation metrics to CloudWatch.

    ``ml_score`` — optional ML risk component; the MLRiskScore metric is only
    emitted when a value is provided (the model does not apply to Ansible).

    Never raises — logs a warning on any failure so the pipeline is never blocked.
    """
    findings = findings or []
    critical_count = sum(1 for f in findings if str(f.get("severity", "")).lower() == "critical")
    high_count = sum(1 for f in findings if str(f.get("severity", "")).lower() == "high")
    decision_value = _DECISION_MAP.get(str(decision).lower(), 2)

    dimensions = [
        {"Name": "StackName", "Value": stack_name},
        {"Name": "RunId", "Value": run_id},
    ]
    stack_dimensions = [
        {"Name": "StackName", "Value": stack_name},
    ]

    # Publish at three dimension granularities:
    #   1. StackName + RunId  — per-run drilldown
    #   2. StackName only     — per-stack trend
    #   3. No dimensions      — aggregate; required by the dashboard and alarms
    #      (CloudWatch treats each dimension set as a distinct metric series, so
    #      the dashboard/alarms that specify no dimensions would otherwise never
    #      receive any data points.)
    def _make_points(dims: list[dict]) -> list[dict]:
        points = [
            {"MetricName": "GateScore",        "Dimensions": dims, "Value": float(score),          "Unit": "None"},
            {"MetricName": "GateDecision",     "Dimensions": dims, "Value": float(decision_value), "Unit": "None"},
            {"MetricName": "CriticalFindings", "Dimensions": dims, "Value": float(critical_count), "Unit": "Count"},
            {"MetricName": "HighFindings",     "Dimensions": dims, "Value": float(high_count),     "Unit": "Count"},
        ]
        if ml_score is not None:
            points.append(
                {"MetricName": "MLRiskScore", "Dimensions": dims, "Value": float(ml_score), "Unit": "None"}
            )
        return points

    metric_data = (
        _make_points(dimensions)
        + _make_points(stack_dimensions)
        + _make_points([])
    )

    try:
        client = _get_client("cloudwatch")
        client.put_metric_data(Namespace=_NAMESPACE, MetricData=metric_data)
        logger.info(
            "CloudWatch: published metrics stack=%r run_id=%r decision=%r score=%s",
            stack_name,
            run_id,
            decision,
            score,
        )
    except Exception as exc:
        logger.warning("CloudWatch: publish_gate_metrics failed — %s", exc)


def put_log_event(
    stack_name: str,
    run_id: str,
    gate_report: dict[str, Any],
) -> None:
    """Write the full gate report as a structured log event to CloudWatch Logs.

    Log group:  /syssecops/gate/{stack_name}
    Log stream: {run_id}

    Creates the log group and stream if they do not already exist.
    Never raises — logs a warning on any failure.
    """
    log_group = f"/syssecops/gate/{stack_name}"
    log_stream = run_id
    timestamp_ms = int(time.time() * 1000)
    message = json.dumps(gate_report, default=str)

    try:
        from botocore.exceptions import ClientError

        client = _get_client("logs")

        # Ensure log group exists
        try:
            client.create_log_group(logGroupName=log_group)
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ResourceAlreadyExistsException":
                raise

        # Ensure log stream exists
        try:
            client.create_log_stream(logGroupName=log_group, logStreamName=log_stream)
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ResourceAlreadyExistsException":
                raise

        client.put_log_events(
            logGroupName=log_group,
            logStreamName=log_stream,
            logEvents=[{"timestamp": timestamp_ms, "message": message}],
        )
        logger.info(
            "CloudWatch Logs: wrote gate report stack=%r run_id=%r group=%r",
            stack_name,
            run_id,
            log_group,
        )
    except Exception as exc:
        logger.warning("CloudWatch Logs: put_log_event failed — %s", exc)
