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

import json
import os
import subprocess
from typing import Any


_OK_STATUS = "ok"
_NOT_INSTALLED_STATUS = "not_installed"
_NO_CREDENTIALS_STATUS = "no_credentials"
_NOT_CONFIGURED_STATUS = "not_configured"
_ERROR_STATUS = "error"
_SKIPPED_STATUS = "skipped"


def _cli_credential_session(boto3: Any, profile_name: str | None, region: str | None) -> Any:
    """Return a boto3.Session with explicit credentials obtained via the AWS CLI.

    Uses ``aws configure export-credentials --format process`` which supports
    credential types that botocore cannot resolve natively (e.g. IAM Identity
    Center 'login' sessions).  Returns None if the CLI call fails.
    """
    cmd = ["aws", "configure", "export-credentials", "--format", "process"]
    if profile_name:
        cmd += ["--profile", profile_name]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        return boto3.Session(
            aws_access_key_id=data["AccessKeyId"],
            aws_secret_access_key=data["SecretAccessKey"],
            aws_session_token=data.get("SessionToken"),
            region_name=region,
        )
    except Exception:
        return None


def fetch_violations(
    region: str | None = None,
    stack_name: str | None = None,  # reserved for future stack-scoped filtering
    *,
    enabled: bool = True,
    profile_name: str | None = None,
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
        from botocore.exceptions import (
            ClientError,
            CredentialRetrievalError,
            EndpointResolutionError,
            NoCredentialsError,
            ProfileNotFound,
        )
    except ImportError:
        return {
            "status": _NOT_INSTALLED_STATUS,
            "violation_count": 0,
            "non_compliant_rules": [],
            "message": "boto3 is not installed.",
        }

    try:
        effective_profile = profile_name or os.environ.get("AWS_PROFILE")
        session = boto3.Session(profile_name=effective_profile)

        # boto3 cannot natively resolve some AWS CLI credential types (e.g.
        # IAM Identity Center 'login' sessions stored via aws sso login).
        # Fall back to the CLI exporter to get explicit short-lived credentials.
        if session.get_credentials() is None:
            session = _cli_credential_session(boto3, effective_profile, region)
            if session is None:
                return {
                    "status": _NO_CREDENTIALS_STATUS,
                    "violation_count": 0,
                    "non_compliant_rules": [],
                    "message": (
                        "boto3 could not resolve credentials and "
                        "'aws configure export-credentials' also failed. "
                        "Ensure your AWS session is active (e.g. aws sso login)."
                    ),
                }

        client = session.client("config", region_name=region)
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

    except (NoCredentialsError, CredentialRetrievalError, ProfileNotFound) as exc:
        return {
            "status": _NO_CREDENTIALS_STATUS,
            "violation_count": 0,
            "non_compliant_rules": [],
            "message": f"AWS credentials not available — Config check skipped: {exc}",
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
