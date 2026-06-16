"""Central AWS credential resolver for the SysSecOps pipeline.

Single source of truth for credential resolution used by both the CLI pipeline
and (later) the GUI.  All pipeline modules should call ``get_session()`` to
obtain a boto3 Session rather than constructing one themselves.

Credential sources, tried in order:
    1. Existing module-level cache (short-circuits all checks).
    2. Environment variables (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY /
       AWS_SESSION_TOKEN) — set by ``export_sso_credentials()``.
    3. Named AWS profile, when ``profile_name`` is passed.
    4. boto3 default credential chain (SSO token cache, instance metadata,
       ~/.aws/credentials, etc.).

Public API:
    get_session(profile_name, force_refresh) -> boto3.Session | None
    get_identity(session)                    -> dict | None
    list_sso_profiles()                      -> list[str]
    login_sso(profile_name)                  -> bool
    export_sso_credentials(profile_name)     -> bool
    invalidate_cache()
"""
from __future__ import annotations

import configparser
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level session cache
# ---------------------------------------------------------------------------
_cached_session: "Any | None" = None   # boto3.Session or None


def _default_region() -> str:
    return (
        os.environ.get("AWS_DEFAULT_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("CDK_DEFAULT_REGION")
        or "us-east-1"
    )


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_session(
    profile_name: str | None = None,
    force_refresh: bool = False,
) -> "Any | None":
    """Return a valid boto3.Session, or None if credentials cannot be resolved.

    Resolution order:
        1. Module-level cache (skipped when force_refresh=True).
        2. Named profile or boto3 default credential chain (env vars, ~/.aws/credentials,
           EC2/ECS instance metadata).
        3. Automatic SSO token export — if the default chain fails and SSO profiles
           exist in ~/.aws/config, each profile is tried via
           ``aws configure export-credentials`` so that a prior ``aws sso login``
           is always picked up without manual env-var setup.

    The result is cached for the lifetime of the process (or until
    ``invalidate_cache()`` / ``export_sso_credentials()`` is called).

    Args:
        profile_name:  AWS named profile (e.g. ``"default"``, ``"sso-dev"``).
                       When *None* the boto3 default credential chain is used.
        force_refresh: Ignore the cache and attempt fresh credential resolution.
    """
    global _cached_session

    if not force_refresh and _cached_session is not None:
        return _cached_session

    import boto3

    region = _default_region()

    # --- Attempt 1: standard boto3 credential chain (or named profile) ---
    try:
        kwargs: dict[str, Any] = {"region_name": region}
        if profile_name:
            kwargs["profile_name"] = profile_name
        session = boto3.Session(**kwargs)
        session.client("sts").get_caller_identity()
        _cached_session = session
        logger.debug("aws_credentials: session resolved via default chain (profile=%r)", profile_name)
        return session
    except Exception as exc:
        logger.debug("aws_credentials: default chain failed — %s", exc)

    # --- Attempt 2: auto-export SSO tokens via the AWS CLI ---
    # This covers the common case where the user has already run `aws sso login`
    # but the venv's botocore cannot find the token in the SSO cache automatically.
    # We try three sources in order:
    #   a) No --profile flag (uses the CLI's current default / active SSO session)
    #   b) Each SSO profile detected in ~/.aws/config
    if profile_name is None:
        _cli_profiles_to_try: list[str | None] = [None] + list_sso_profiles()
        for _cli_profile in _cli_profiles_to_try:
            logger.debug(
                "aws_credentials: trying CLI export-credentials (profile=%r)", _cli_profile
            )
            try:
                cmd = ["aws", "configure", "export-credentials", "--format", "env-no-export"]
                if _cli_profile:
                    cmd += ["--profile", _cli_profile]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
                if result.returncode != 0:
                    logger.debug(
                        "aws_credentials: CLI export failed (profile=%r) — %s",
                        _cli_profile, result.stderr.strip(),
                    )
                    continue

                exported: dict[str, str] = {}
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        key, _, value = line.partition("=")
                        key = key.strip()
                        if key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                                   "AWS_SESSION_TOKEN", "AWS_CREDENTIAL_EXPIRATION"):
                            exported[key] = value.strip()

                if "AWS_ACCESS_KEY_ID" not in exported:
                    continue

                # Apply to os.environ so boto3 picks them up in the new session
                for k, v in exported.items():
                    os.environ[k] = v

                session = boto3.Session(region_name=region)
                session.client("sts").get_caller_identity()
                _cached_session = session
                logger.info(
                    "aws_credentials: session resolved via CLI export (profile=%r)",
                    _cli_profile,
                )
                return session
            except Exception as exc:
                logger.debug(
                    "aws_credentials: CLI export attempt failed (profile=%r) — %s",
                    _cli_profile, exc,
                )

    _cached_session = None
    logger.debug("aws_credentials: all credential resolution attempts failed")
    return None


def get_identity(session: "Any | None" = None) -> dict | None:
    """Return ``{UserId, Account, Arn}`` for the current caller, or None.

    Args:
        session: An existing boto3.Session.  If None, ``get_session()`` is used.
    """
    s = session or get_session()
    if s is None:
        return None
    try:
        return s.client("sts").get_caller_identity()
    except Exception as exc:
        logger.debug("aws_credentials: get_identity failed — %s", exc)
        return None


def invalidate_cache() -> None:
    """Clear the cached boto3.Session so the next call re-resolves credentials.

    Call this after ``export_sso_credentials()`` or when the GUI detects that
    credentials have changed.
    """
    global _cached_session
    _cached_session = None
    logger.debug("aws_credentials: cache invalidated")


# ---------------------------------------------------------------------------
# SSO helpers (used by CLI and, later, GUI login tab)
# ---------------------------------------------------------------------------

def list_sso_profiles() -> list[str]:
    """Return the names of all AWS CLI profiles configured with SSO.

    Reads ``~/.aws/config`` and returns profiles that have an ``sso_start_url``
    or ``sso_session`` key.  Returns an empty list if the config file does not
    exist or is unreadable.
    """
    config_path = Path.home() / ".aws" / "config"
    if not config_path.exists():
        return []

    try:
        parser = configparser.ConfigParser()
        parser.read(str(config_path))

        profiles: list[str] = []
        for section in parser.sections():
            if parser.has_option(section, "sso_start_url") or parser.has_option(section, "sso_session"):
                # Section names are like "profile dev" or "default"
                name = re.sub(r"^profile\s+", "", section).strip()
                profiles.append(name)
        return profiles
    except Exception as exc:
        logger.debug("aws_credentials: list_sso_profiles failed — %s", exc)
        return []


def login_sso(profile_name: str) -> bool:
    """Trigger ``aws sso login --profile <profile_name>`` in a subprocess.

    This opens the browser-based SSO login flow.  The function blocks until the
    process exits and returns True on success.

    Note: This is an interactive operation. When called from the GUI, run it in
    a background thread so the UI is not blocked.
    """
    try:
        result = subprocess.run(
            ["aws", "sso", "login", "--profile", profile_name],
            check=False,
        )
        if result.returncode == 0:
            logger.info("aws_credentials: SSO login succeeded for profile=%r", profile_name)
            # Automatically export credentials into os.environ after a successful login
            return export_sso_credentials(profile_name)
        logger.warning("aws_credentials: SSO login failed for profile=%r (exit %d)", profile_name, result.returncode)
        return False
    except FileNotFoundError:
        logger.error("aws_credentials: 'aws' CLI not found — install the AWS CLI v2")
        return False
    except Exception as exc:
        logger.error("aws_credentials: login_sso failed — %s", exc)
        return False


def export_sso_credentials(profile_name: str) -> bool:
    """Export SSO session tokens into ``os.environ`` so boto3 clients find them.

    Runs ``aws configure export-credentials --profile <name> --format env-no-export``
    and sets ``AWS_ACCESS_KEY_ID``, ``AWS_SECRET_ACCESS_KEY``, and
    ``AWS_SESSION_TOKEN`` in the current process environment.

    After a successful export, the session cache is invalidated so the next
    ``get_session()`` call picks up the fresh credentials.

    Returns True on success, False if the command fails or credentials are
    unavailable.
    """
    try:
        result = subprocess.run(
            ["aws", "configure", "export-credentials",
             "--profile", profile_name,
             "--format", "env-no-export"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.warning(
                "aws_credentials: export_sso_credentials failed for profile=%r — %s",
                profile_name,
                result.stderr.strip(),
            )
            return False

        # Parse "AWS_ACCESS_KEY_ID=AKIA..." lines
        exported: list[str] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
                           "AWS_CREDENTIAL_EXPIRATION"):
                    os.environ[key] = value
                    exported.append(key)

        if not exported:
            logger.warning("aws_credentials: export_sso_credentials produced no credential vars for profile=%r", profile_name)
            return False

        logger.info("aws_credentials: exported credentials for profile=%r (%s)", profile_name, ", ".join(exported))
        invalidate_cache()   # force next get_session() to pick up the new env vars
        return True

    except FileNotFoundError:
        logger.error("aws_credentials: 'aws' CLI not found — install the AWS CLI v2")
        return False
    except Exception as exc:
        logger.error("aws_credentials: export_sso_credentials failed — %s", exc)
        return False
