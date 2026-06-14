"""AWS SNS notifier for CDK pipeline gate events.

Usage:
    from pipeline.notifier import get_notifier

    notifier = get_notifier()
    if notifier:
        notifier.send("reject", gate_report)

Configuration via environment variables:
    SNS_TOPIC_ARN      — required; notifications are skipped if unset
    AWS_DEFAULT_REGION — used for SNS client region (falls back to us-east-1)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_EVENT_TYPES = frozenset({"review_required", "reject", "deploy_success", "deploy_failure"})


class SNSNotifier:
    """Send CDK pipeline event notifications via AWS SNS."""

    def __init__(self, topic_arn: str, region: str) -> None:
        self._topic_arn = topic_arn
        self._region = region

    def send(
        self,
        event_type: str,
        gate_report: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Publish an event notification to SNS.

        Never raises — logs a warning on failure so the pipeline is never blocked.
        """
        if event_type not in _EVENT_TYPES:
            logger.warning("SNSNotifier: unknown event_type=%r; skipping.", event_type)
            return

        gate_report = gate_report or {}
        top_findings = (gate_report.get("findings") or [])[:5]

        payload: dict[str, Any] = {
            "event_type": event_type,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "run_id": gate_report.get("run_id"),
            "decision": gate_report.get("decision"),
            "score": gate_report.get("score"),
            "top_findings": top_findings,
        }
        if extra:
            payload.update(extra)

        try:
            import boto3  # local import keeps module importable without boto3 installed

            client = boto3.client("sns", region_name=self._region)
            client.publish(
                TopicArn=self._topic_arn,
                Subject=f"CDK Pipeline: {event_type}",
                Message=json.dumps(payload, indent=2),
                MessageAttributes={
                    "event_type": {
                        "DataType": "String",
                        "StringValue": event_type,
                    }
                },
            )
            logger.info("SNSNotifier: published event_type=%r run_id=%r", event_type, payload.get("run_id"))
        except Exception as exc:  # pragma: no cover
            logger.warning("SNSNotifier: failed to publish %r — %s", event_type, exc)


def get_notifier() -> SNSNotifier | None:
    """Return a configured SNSNotifier or None if SNS_TOPIC_ARN is not set."""
    topic_arn = os.environ.get("SNS_TOPIC_ARN", "").strip()
    if not topic_arn:
        return None
    region = (
        os.environ.get("AWS_DEFAULT_REGION")
        or os.environ.get("AWS_REGION")
        or "us-east-1"
    )
    return SNSNotifier(topic_arn=topic_arn, region=region)
