"""Lambda handler for the SysSecOps ops-loop.

Handles two EventBridge event patterns:

1. AWS Config compliance change (source: aws.config)
   - Detects drift on a previously-passing stack
   - Publishes a drift_detected SNS notification
   - Optionally re-triggers the CDK pipeline (RETRIGGER_MODE=auto_retrigger)

2. CloudFormation stack status change (source: aws.cloudformation)
   - Detects rollback / failure states
   - Publishes a stack_rollback SNS notification

This file is intentionally standalone — it uses only boto3 and the standard
library so it can be packaged as a Lambda deployment asset without carrying
the rest of the project as a dependency.

Environment variables:
    SNS_TOPIC_ARN      — required; SNS notifications are skipped if unset
    AWS_DEFAULT_REGION — region for all boto3 clients
    RETRIGGER_MODE     — "notify_only" (default) | "auto_retrigger"
    PIPELINE_LAMBDA_ARN — Lambda ARN to invoke in auto_retrigger mode
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
_RETRIGGER_MODE = os.environ.get("RETRIGGER_MODE", "notify_only")
_PIPELINE_LAMBDA_ARN = os.environ.get("PIPELINE_LAMBDA_ARN", "")
_SSM_PREFIX = "/syssecops/gate"

# CloudFormation statuses that indicate a rollback or failure
_ROLLBACK_STATUSES = frozenset({
    "ROLLBACK_COMPLETE",
    "UPDATE_ROLLBACK_COMPLETE",
    "DELETE_FAILED",
    "CREATE_FAILED",
    "UPDATE_FAILED",
})


def _get_region() -> str:
    return (
        os.environ.get("AWS_DEFAULT_REGION")
        or os.environ.get("AWS_REGION")
        or "us-east-1"
    )


def _publish_sns(event_type: str, payload: dict[str, Any]) -> None:
    """Publish an SNS message. Never raises."""
    if not _SNS_TOPIC_ARN:
        logger.warning("SNS_TOPIC_ARN not set; skipping notification event_type=%r", event_type)
        return

    try:
        import boto3

        client = boto3.client("sns", region_name=_get_region())
        message = json.dumps(payload, indent=2)
        client.publish(
            TopicArn=_SNS_TOPIC_ARN,
            Subject=f"SysSecOps: {event_type}",
            Message=message,
            MessageAttributes={
                "event_type": {
                    "DataType": "String",
                    "StringValue": event_type,
                }
            },
        )
        logger.info("SNS: published event_type=%r", event_type)
    except Exception as exc:
        logger.warning("SNS: publish failed event_type=%r — %s", event_type, exc)


def _read_ssm_gate_result(stack_name: str) -> dict[str, str] | None:
    """Read latest gate result from SSM. Returns None on error or not found."""
    try:
        import boto3

        client = boto3.client("ssm", region_name=_get_region())
        prefix = f"{_SSM_PREFIX}/{stack_name}/"
        response = client.get_parameters_by_path(Path=prefix)
        params = response.get("Parameters", [])
        if not params:
            return None

        result: dict[str, str] = {}
        for param in params:
            suffix = param["Name"].replace(prefix, "")
            result[suffix] = param["Value"]
        return result or None
    except Exception as exc:
        logger.warning("SSM: read_gate_result failed stack=%r — %s", stack_name, exc)
        return None


def _auto_retrigger(stack_name: str, run_id: str) -> None:
    """Re-invoke the pipeline Lambda in auto_retrigger mode. Never raises."""
    if not _PIPELINE_LAMBDA_ARN:
        logger.warning("PIPELINE_LAMBDA_ARN not set; cannot auto_retrigger for stack=%r", stack_name)
        return

    try:
        import boto3

        client = boto3.client("lambda", region_name=_get_region())
        payload = json.dumps({
            "action": "retrigger",
            "stack_name": stack_name,
            "triggered_by_run_id": run_id,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        })
        client.invoke(
            FunctionName=_PIPELINE_LAMBDA_ARN,
            InvocationType="Event",  # async
            Payload=payload.encode(),
        )
        logger.info("Lambda: auto_retrigger invoked for stack=%r", stack_name)
    except Exception as exc:
        logger.warning("Lambda: auto_retrigger failed for stack=%r — %s", stack_name, exc)


def _handle_config_event(event: dict[str, Any]) -> None:
    """Handle an AWS Config Rules Compliance Change event."""
    detail = event.get("detail", {})
    resource_id = detail.get("resourceId") or detail.get("resourceType", "unknown")
    compliance_type = detail.get("newEvaluationResult", {}).get("complianceType", "")
    config_rule_name = detail.get("configRuleName", "unknown")

    # Attempt to extract a stack name — Config events may carry the stack name
    # in the resourceId when the resource is a CloudFormation stack, or we fall
    # back to the resourceId directly.
    stack_name = resource_id

    logger.info(
        "Config event: stack=%r rule=%r compliance=%r",
        stack_name,
        config_rule_name,
        compliance_type,
    )

    if compliance_type != "NON_COMPLIANT":
        logger.info("Compliance type is %r; no action required.", compliance_type)
        return

    # Check last gate decision from SSM
    gate_result = _read_ssm_gate_result(stack_name)
    last_decision = (gate_result or {}).get("latest_decision", "unknown")
    last_run_id = (gate_result or {}).get("latest_run_id", "unknown")
    last_score = (gate_result or {}).get("latest_score", "unknown")

    logger.info(
        "Drift detected: stack=%r was last decision=%r (run_id=%r); Config rule %r now NON_COMPLIANT",
        stack_name,
        last_decision,
        last_run_id,
        config_rule_name,
    )

    payload: dict[str, Any] = {
        "event_type": "drift_detected",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "stack_name": stack_name,
        "config_rule_name": config_rule_name,
        "last_gate_decision": last_decision,
        "last_gate_score": last_score,
        "last_run_id": last_run_id,
        "compliance_type": compliance_type,
    }
    _publish_sns("drift_detected", payload)

    if _RETRIGGER_MODE == "auto_retrigger":
        _auto_retrigger(stack_name, last_run_id)


def _handle_cloudformation_event(event: dict[str, Any]) -> None:
    """Handle a CloudFormation Stack Status Change event."""
    detail = event.get("detail", {})
    stack_id = detail.get("stack-id", "")
    status_details = detail.get("status-details", {})
    stack_status = status_details.get("stack-status", "")

    # Extract stack name from ARN: arn:aws:cloudformation:...:stack/{name}/{id}
    stack_name = stack_id
    if ":stack/" in stack_id:
        try:
            stack_name = stack_id.split(":stack/")[1].split("/")[0]
        except IndexError:
            pass
    elif "/stack/" in stack_id:
        try:
            stack_name = stack_id.split("/stack/")[1].split("/")[0]
        except IndexError:
            pass

    if stack_status not in _ROLLBACK_STATUSES:
        logger.info("CFN status %r for stack=%r; no action required.", stack_status, stack_name)
        return

    logger.info("CFN rollback detected: stack=%r status=%r", stack_name, stack_status)

    gate_result = _read_ssm_gate_result(stack_name)
    last_run_id = (gate_result or {}).get("latest_run_id", "unknown")
    last_decision = (gate_result or {}).get("latest_decision", "unknown")

    payload: dict[str, Any] = {
        "event_type": "stack_rollback",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "stack_name": stack_name,
        "stack_status": stack_status,
        "last_gate_decision": last_decision,
        "last_run_id": last_run_id,
    }
    _publish_sns("stack_rollback", payload)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point. Routes to the appropriate handler by event source."""
    source = event.get("source", "")
    detail_type = event.get("detail-type", "")

    logger.info("Received event source=%r detail-type=%r", source, detail_type)

    try:
        if source == "aws.config" and detail_type == "Config Rules Compliance Change":
            _handle_config_event(event)
        elif source == "aws.cloudformation" and detail_type == "CloudFormation Stack Status Change":
            _handle_cloudformation_event(event)
        else:
            logger.warning("Unrecognised event source=%r detail-type=%r; ignoring.", source, detail_type)
    except Exception as exc:
        # Never let the handler crash — log and return gracefully
        logger.error("Unhandled error in Lambda handler: %s", exc, exc_info=True)

    return {"statusCode": 200, "body": "ok"}
