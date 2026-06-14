"""AWS Config adapter for IaC gate: fetches non-compliant rule counts via boto3.

Gracefully degrades when credentials are absent, AWS Config is not enabled in
the target account/region, or boto3 is not installed.

Status values returned:
    ok             – Config API call succeeded
    skipped        – disabled by caller
    not_installed  – boto3 library not available
    no_credentials – AWS credentials not found or expired
    not_configured – AWS Config service not enabled in account/region
    error          – unexpected boto3 or API error
"""
from __future__ import annotations

from typing import Any


_OK_STATUS = "ok"
_NOT_INSTALLED_STATUS = "not_installed"
_NO_CREDENTIALS_STATUS = "no_credentials"
_NOT_CONFIGURED_STATUS = "not_configured"
_ERROR_STATUS = "error"
_SKIPPED_STATUS = "skipped"


def fetch_violations(
    region: str | None = None,
    stack_name: str | None = None,  # reserved for future stack-scoped filtering
    *,
    enabled: bool = True,
) -> dict[str, Any]:
    """Fetch non-compliant AWS Config rule count for the given region.

    Returns a dict with keys:
        status              – "ok" | "skipped" | "not_installed" | "no_credentials"
                              | "not_configured" | "error"
        violation_count     – total non-compliant rule count (int)
        non_compliant_rules – list of non-compliant rule names (list[str])
        message             – human-readable status detail
    """
    if not enabled:
        return {
            "status": _SKIPPED_STATUS,
            "violation_count": 0,
            "non_compliant_rules": [],
            "message": "AWS Config check disabled by caller.",
        }

    try:
        import boto3
        from botocore.exceptions import ClientError, EndpointResolutionError, NoCredentialsError
    except ImportError:
        return {
            "status": _NOT_INSTALLED_STATUS,
            "violation_count": 0,
            "non_compliant_rules": [],
            "message": "boto3 is not installed.",
        }

    try:
        client = boto3.client("config", region_name=region)
        paginator = client.get_paginator("describe_compliance_by_config_rule")
        pages = paginator.paginate(ComplianceTypes=["NON_COMPLIANT"])

        non_compliant: list[str] = []
        for page in pages:
            for rule in page.get("ComplianceByConfigRules", []):
                compliance = rule.get("Compliance", {})
                if compliance.get("ComplianceType") == "NON_COMPLIANT":
                    non_compliant.append(str(rule.get("ConfigRuleName", "unknown")))

        return {
            "status": _OK_STATUS,
            "violation_count": len(non_compliant),
            "non_compliant_rules": non_compliant,
            "message": f"{len(non_compliant)} non-compliant rule(s) found.",
        }

    except NoCredentialsError:
        return {
            "status": _NO_CREDENTIALS_STATUS,
            "violation_count": 0,
            "non_compliant_rules": [],
            "message": "AWS credentials not found — Config check skipped.",
        }
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {
            "AccessDeniedException",
            "NoSuchConfigurationRecorderException",
            "ConfigServiceNotAvailableException",
        }:
            return {
                "status": _NOT_CONFIGURED_STATUS,
                "violation_count": 0,
                "non_compliant_rules": [],
                "message": f"AWS Config not available in this account/region: {exc}",
            }
        return {
            "status": _ERROR_STATUS,
            "violation_count": 0,
            "non_compliant_rules": [],
            "message": f"AWS Config API error: {exc}",
        }
    except Exception as exc:
        return {
            "status": _ERROR_STATUS,
            "violation_count": 0,
            "non_compliant_rules": [],
            "message": f"Unexpected error fetching Config violations: {exc}",
        }
