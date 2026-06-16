"""EventBridge custom event publisher for CDK pipeline gate decisions.

Publishes a GateDecision event to the EventBridge default bus after every
gate evaluation so downstream automation (Lambda, Step Functions) can react.

Configuration via environment variables:
    EVENTBRIDGE_ENABLED — set to "false" to disable publishing (default: enabled)
    AWS_DEFAULT_REGION  — region for EventBridge client (falls back to us-east-1)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_SOURCE = "syssecops.gate"
_DETAIL_TYPE = "GateDecision"


def _is_enabled() -> bool:
    return os.environ.get("EVENTBRIDGE_ENABLED", "true").strip().lower() not in ("false", "0", "no")


def _get_client():
    from pipeline.aws_credentials import get_session

    session = get_session()
    if session is not None:
        return session.client("events")
    # Fallback: direct boto3 (reads env vars / ~/.aws/credentials)
    import boto3

    region = (
        os.environ.get("AWS_DEFAULT_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("CDK_DEFAULT_REGION")
        or "us-east-1"
    )
    return boto3.client("events", region_name=region)


def publish_gate_event(
    run_id: str,
    stack_name: str,
    decision: str,
    score: int | float,
) -> None:
    """Publish a GateDecision event to the EventBridge default bus.

    Never raises — logs a warning on any failure so the pipeline is never blocked.
    No-ops when EVENTBRIDGE_ENABLED=false.
    """
    if not _is_enabled():
        logger.debug("EventBridge disabled; skipping publish_gate_event run_id=%r", run_id)
        return

    detail = {
        "run_id": run_id,
        "stack_name": stack_name,
        "decision": decision,
        "score": score,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }

    try:
        client = _get_client()
        response = client.put_events(
            Entries=[
                {
                    "Source": _SOURCE,
                    "DetailType": _DETAIL_TYPE,
                    "Detail": json.dumps(detail),
                }
            ]
        )
        failed = response.get("FailedEntryCount", 0)
        if failed:
            logger.warning(
                "EventBridge: %d entries failed for run_id=%r — %s",
                failed,
                run_id,
                response.get("Entries"),
            )
        else:
            logger.info(
                "EventBridge: published GateDecision run_id=%r stack=%r decision=%r",
                run_id,
                stack_name,
                decision,
            )
    except Exception as exc:
        logger.warning("EventBridge: publish_gate_event failed run_id=%r — %s", run_id, exc)
