"""Shared .env loader for all pipeline entry points.

Call ``load_env()`` early in each CLI ``main()`` (or at import time of an entry
point) so that credentials and configuration placed in the repo-root ``.env``
file are available via ``os.environ``/``os.getenv`` before any AWS, Bedrock, or
OpenRouter client is constructed.

This is intentionally dependency-light: it prefers ``python-dotenv`` when it is
installed, but falls back to a minimal built-in parser so the pipeline still
loads ``.env`` even if the package is missing.
"""
from __future__ import annotations

import os
from pathlib import Path

# Repo root = directory containing this file.
ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = ROOT_DIR / ".env"

_LOADED = False


def _parse_minimal(env_path: Path) -> dict[str, str]:
    """Very small ``.env`` parser used when python-dotenv is unavailable."""
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def load_env(env_path: Path | str | None = None, *, override: bool = False) -> bool:
    """Load environment variables from a ``.env`` file.

    Existing environment variables are preserved unless ``override`` is True.
    Returns True if a ``.env`` file was found and loaded, False otherwise.
    """
    global _LOADED

    path = Path(env_path) if env_path is not None else DEFAULT_ENV_PATH
    if not path.is_file():
        return False

    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(dotenv_path=path, override=override)
        _LOADED = True
        return True
    except ImportError:
        pass

    for key, value in _parse_minimal(path).items():
        if override or key not in os.environ:
            os.environ[key] = value

    _LOADED = True
    return True
