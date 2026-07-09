"""Credential management for AWS (Bedrock) and OpenRouter.

Loads from and saves to the standard locations so the existing pipeline
scripts (which use boto3's default chain and the repo ``.env``) pick them up:

- AWS keys/region -> ``~/.aws/credentials`` + ``~/.aws/config`` ([default] profile)
- OpenRouter key   -> repo-root ``.env`` (already gitignored)

Security: secret values are never logged. Callers should keep only a
``creds_loaded`` boolean in Streamlit session state, not the raw secrets.
"""
from __future__ import annotations

import configparser
import json
import urllib.error
import urllib.request

from ui import config


# --- Loading ----------------------------------------------------------------
def load_credentials() -> dict[str, str]:
    """Read currently stored credentials. Missing values become empty strings."""
    creds = {
        "access_key": "",
        "secret_key": "",
        "session_token": "",
        "region": "",
        "openrouter_key": "",
        "infracost_key": "",
        "tailscale_key": "",
        "tailscale_tailnet": "",
    }

    # AWS credentials file
    if config.AWS_CREDS_PATH.exists():
        parser = configparser.ConfigParser()
        try:
            parser.read(config.AWS_CREDS_PATH)
            if parser.has_section("default"):
                section = parser["default"]
                creds["access_key"] = section.get("aws_access_key_id", "")
                creds["secret_key"] = section.get("aws_secret_access_key", "")
                creds["session_token"] = section.get("aws_session_token", "")
        except configparser.Error:
            pass

    # AWS config file (region)
    if config.AWS_CONFIG_PATH.exists():
        parser = configparser.ConfigParser()
        try:
            parser.read(config.AWS_CONFIG_PATH)
            # In config the default profile is the literal section [default]
            if parser.has_section("default"):
                creds["region"] = parser["default"].get("region", "")
        except configparser.Error:
            pass

    # Fall back to the repo .env for any AWS value not found in ~/.aws.
    # The pipeline scripts read these same variables, so the Login tab can
    # auto-fill from .env without a prior terminal login.
    if not creds["access_key"]:
        creds["access_key"] = _read_env_value("AWS_ACCESS_KEY_ID")
    if not creds["secret_key"]:
        creds["secret_key"] = _read_env_value("AWS_SECRET_ACCESS_KEY")
    if not creds["session_token"]:
        creds["session_token"] = _read_env_value("AWS_SESSION_TOKEN")
    if not creds["region"]:
        creds["region"] = _read_env_value("AWS_REGION") or _read_env_value("AWS_DEFAULT_REGION")

    # OpenRouter key from .env
    creds["openrouter_key"] = _read_env_value("OPENROUTER_API_KEY")

    # Infracost + Tailscale from .env
    creds["infracost_key"] = _read_env_value("INFRACOST_API_KEY")
    creds["tailscale_key"] = _read_env_value("TAILSCALE_API_KEY")
    creds["tailscale_tailnet"] = _read_env_value("TAILSCALE_TAILNET")

    if not creds["region"]:
        creds["region"] = config.DEFAULT_REGION

    return creds


# --- Saving -----------------------------------------------------------------
def save_aws_credentials(
    access_key: str,
    secret_key: str,
    session_token: str,
    region: str,
) -> None:
    """Write the [default] profile to ~/.aws/credentials and ~/.aws/config."""
    config.AWS_DIR.mkdir(parents=True, exist_ok=True)

    # credentials file
    creds_parser = configparser.ConfigParser()
    if config.AWS_CREDS_PATH.exists():
        creds_parser.read(config.AWS_CREDS_PATH)
    if not creds_parser.has_section("default"):
        creds_parser.add_section("default")
    creds_parser["default"]["aws_access_key_id"] = access_key.strip()
    creds_parser["default"]["aws_secret_access_key"] = secret_key.strip()
    if session_token.strip():
        creds_parser["default"]["aws_session_token"] = session_token.strip()
    else:
        creds_parser["default"].pop("aws_session_token", None)
    with config.AWS_CREDS_PATH.open("w", encoding="utf-8") as fh:
        creds_parser.write(fh)
    _chmod_600(config.AWS_CREDS_PATH)

    # config file (region)
    config_parser = configparser.ConfigParser()
    if config.AWS_CONFIG_PATH.exists():
        config_parser.read(config.AWS_CONFIG_PATH)
    if not config_parser.has_section("default"):
        config_parser.add_section("default")
    config_parser["default"]["region"] = (region.strip() or config.DEFAULT_REGION)
    with config.AWS_CONFIG_PATH.open("w", encoding="utf-8") as fh:
        config_parser.write(fh)


def save_openrouter_key(api_key: str) -> None:
    """Update only the OPENROUTER_API_KEY line in the repo .env, preserving others."""
    _write_env_value("OPENROUTER_API_KEY", api_key.strip())


def save_tailscale_settings(api_key: str, tailnet: str) -> None:
    """Update the TAILSCALE_API_KEY / TAILSCALE_TAILNET lines in the repo .env."""
    _write_env_value("TAILSCALE_API_KEY", api_key.strip())
    _write_env_value("TAILSCALE_TAILNET", tailnet.strip())


# --- Validation -------------------------------------------------------------
def test_aws_credentials(
    access_key: str,
    secret_key: str,
    session_token: str,
    region: str,
) -> tuple[bool, str]:
    """Verify AWS keys by calling STS GetCallerIdentity. No secrets are logged."""
    try:
        import boto3
    except ImportError:
        return False, "boto3 is not installed."

    try:
        session = boto3.Session(
            aws_access_key_id=access_key.strip() or None,
            aws_secret_access_key=secret_key.strip() or None,
            aws_session_token=session_token.strip() or None,
            region_name=region.strip() or config.DEFAULT_REGION,
        )
        identity = session.client("sts").get_caller_identity()
        return True, f"Connected as {identity.get('Arn', 'unknown ARN')}"
    except Exception as exc:  # noqa: BLE001 - surface any boto/credential error
        return False, _short_error(exc)


def test_openrouter_key(api_key: str) -> tuple[bool, str]:
    """Verify an OpenRouter key with a lightweight models listing request."""
    key = api_key.strip()
    if not key:
        return False, "No API key provided."

    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/models",
        headers={"Authorization": f"Bearer {key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if 200 <= response.status < 300:
                return True, "Key accepted by OpenRouter."
            return False, f"Unexpected status {response.status}."
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, "Invalid or unauthorized API key."
        return False, f"HTTP {exc.code} from OpenRouter."
    except urllib.error.URLError as exc:
        return False, f"Network error: {exc.reason}"
    except Exception as exc:  # noqa: BLE001
        return False, _short_error(exc)


# --- .env helpers -----------------------------------------------------------
def _read_env_value(key: str) -> str:
    if not config.ENV_FILE.exists():
        return ""
    try:
        for raw in config.ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            name, _, value = line.partition("=")
            if name.strip() == key:
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                    value = value[1:-1]
                return value
    except OSError:
        return ""
    return ""


def _write_env_value(key: str, value: str) -> None:
    lines: list[str] = []
    if config.ENV_FILE.exists():
        lines = config.ENV_FILE.read_text(encoding="utf-8").splitlines()

    new_line = f"{key}={value}"
    replaced = False
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        candidate = stripped[len("export "):] if stripped.startswith("export ") else stripped
        if candidate.partition("=")[0].strip() == key:
            lines[i] = new_line
            replaced = True
            break
    if not replaced:
        lines.append(new_line)

    config.ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- Misc -------------------------------------------------------------------
def _chmod_600(path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _short_error(exc: Exception) -> str:
    message = str(exc)
    return message if len(message) <= 200 else message[:197] + "..."
