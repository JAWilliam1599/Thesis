"""Hybrid status helpers: on-prem node visibility for the monitoring layer.

Read-only collectors that give the hybrid system a view across the AWS/on-prem
boundary.  All functions are best-effort and never raise — they return a status
string alongside the data so the CLI (and, later, the UI) can render partial
results when a backend is unavailable.

Sources:
    - AWS SSM managed nodes (mi-* hybrid activations + EC2 instances)
    - AWS SSM compliance summaries (State Manager / Patch drift)
    - Tailscale device API (AWS <-> on-prem mesh health / network flow)

Configuration via environment variables:
    AWS_DEFAULT_REGION  — region for SSM client (falls back to us-east-1)
    TAILSCALE_API_KEY   — Tailscale API access token (tskey-api-...)
    TAILSCALE_TAILNET   — tailnet name (e.g. "example.com" or "-" for default)
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


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


def list_ssm_managed_nodes() -> tuple[list[dict[str, Any]], str]:
    """Return SSM-managed nodes (EC2 + hybrid mi-* activations).

    Status: "ok" | "no_credentials" | "error"
    """
    try:
        client = _get_client("ssm")
    except Exception as exc:
        logger.debug("SSM client unavailable — %s", exc)
        return [], "no_credentials"

    nodes: list[dict[str, Any]] = []
    try:
        paginator = client.get_paginator("describe_instance_information")
        for page in paginator.paginate():
            for info in page.get("InstanceInformationList", []):
                instance_id = info.get("InstanceId", "")
                nodes.append(
                    {
                        "id": instance_id,
                        "name": info.get("Name") or info.get("ComputerName") or instance_id,
                        "ping_status": info.get("PingStatus", "Unknown"),
                        "platform": info.get("PlatformName", ""),
                        "ip": info.get("IPAddress", ""),
                        "agent_version": info.get("AgentVersion", ""),
                        "last_ping": str(info.get("LastPingDateTime", "")),
                        # mi-* IDs are hybrid (on-prem) activations; i-* are EC2.
                        "is_hybrid": instance_id.startswith("mi-"),
                    }
                )
        return nodes, "ok"
    except Exception as exc:
        logger.warning("list_ssm_managed_nodes failed — %s", exc)
        return [], "error"


def get_ssm_compliance() -> tuple[list[dict[str, Any]], str]:
    """Return SSM resource compliance summaries (Association / Patch drift).

    Status: "ok" | "no_credentials" | "error"
    """
    try:
        client = _get_client("ssm")
    except Exception as exc:
        logger.debug("SSM client unavailable — %s", exc)
        return [], "no_credentials"

    items: list[dict[str, Any]] = []
    try:
        paginator = client.get_paginator("list_resource_compliance_summaries")
        for page in paginator.paginate():
            for summary in page.get("ResourceComplianceSummaryItems", []):
                counts = summary.get("NonCompliantSummary", {}).get("SeveritySummary", {})
                items.append(
                    {
                        "resource_id": summary.get("ResourceId", ""),
                        "resource_type": summary.get("ResourceType", ""),
                        "compliance_type": summary.get("ComplianceType", ""),
                        "status": summary.get("Status", ""),
                        "critical": counts.get("CriticalCount", 0),
                        "high": counts.get("HighCount", 0),
                    }
                )
        return items, "ok"
    except Exception as exc:
        logger.warning("get_ssm_compliance failed — %s", exc)
        return [], "error"


def list_tailscale_devices() -> tuple[list[dict[str, Any]], str]:
    """Return Tailscale devices in the tailnet (AWS <-> on-prem mesh).

    Status: "ok" | "not_configured" | "error"

    Requires TAILSCALE_API_KEY and TAILSCALE_TAILNET environment variables.
    """
    api_key = os.environ.get("TAILSCALE_API_KEY", "").strip()
    tailnet = os.environ.get("TAILSCALE_TAILNET", "-").strip() or "-"
    if not api_key:
        return [], "not_configured"

    url = f"https://api.tailscale.com/api/v2/tailnet/{tailnet}/devices"
    req = urllib.request.Request(url)
    # Tailscale uses HTTP basic auth with the API key as the username.
    import base64

    token = base64.b64encode(f"{api_key}:".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 (fixed host)
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        logger.warning("Tailscale API HTTP %s", exc.code)
        return [], "error"
    except Exception as exc:
        logger.warning("Tailscale API request failed — %s", exc)
        return [], "error"

    devices: list[dict[str, Any]] = []
    for dev in payload.get("devices", []):
        devices.append(
            {
                "name": dev.get("name", ""),
                "hostname": dev.get("hostname", ""),
                "addresses": dev.get("addresses", []),
                "os": dev.get("os", ""),
                "online": bool(dev.get("online", False)),
                "last_seen": dev.get("lastSeen", ""),
                "update_available": bool(dev.get("updateAvailable", False)),
            }
        )
    return devices, "ok"


def collect_hybrid_status() -> dict[str, Any]:
    """Aggregate all hybrid status sources into a single dict for CLI/UI output."""
    nodes, nodes_status = list_ssm_managed_nodes()
    compliance, compliance_status = get_ssm_compliance()
    devices, devices_status = list_tailscale_devices()
    return {
        "ssm_nodes": {"status": nodes_status, "items": nodes},
        "ssm_compliance": {"status": compliance_status, "items": compliance},
        "tailscale_devices": {"status": devices_status, "items": devices},
    }
