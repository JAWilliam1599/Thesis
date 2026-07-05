"""Discovery and loading helpers for run folders and gate reports.

All discovery functions accept an optional ``logs_root`` (the active
project's artifact directory); they default to the legacy flat ``logs/``
layout used by the built-in default project.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ui import config


# --- Timestamp / label formatting ------------------------------------------
def parse_run_timestamp(name: str) -> datetime | None:
    """Parse a ``cdk_<ISO>Z`` / ``gate_cdk_<ISO>Z`` style name to datetime."""
    token = name
    for prefix in ("gate_cdk_", "gate_", "cdk_"):
        if token.startswith(prefix):
            token = token[len(prefix):]
            break
    # Strip any trailing attempt suffix like "_a3".
    if "_" in token:
        token = token.split("_")[0]
    token = token.rstrip("Z")
    for fmt in ("%Y%m%dT%H%M%S%f", "%Y%m%dT%H%M%S"):
        try:
            return datetime.strptime(token, fmt)
        except ValueError:
            continue
    return None


def format_run_label(path: Path) -> str:
    """Human-friendly label for a report file."""
    ts = parse_run_timestamp(path.stem if path.is_file() else path.name)
    when = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else "unknown time"
    return f"{path.name}  ·  {when}"


# --- Gate reports -----------------------------------------------------------
def list_gate_reports(logs_root: Path | None = None) -> list[Path]:
    """All persisted gate report JSON files, most recent (mtime) first."""
    reports_dir = (logs_root or config.LOGS_DIR) / "gate_reports"
    if not reports_dir.exists():
        return []
    found = list(reports_dir.glob("gate_*.json"))
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def load_gate_report(path: Path) -> dict[str, Any] | None:
    return _read_json(path)


def newest_gate_report(logs_root: Path | None = None) -> dict[str, Any] | None:
    found = list_gate_reports(logs_root)
    return _read_json(found[0]) if found else None


def load_all_gate_reports(logs_root: Path | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in list_gate_reports(logs_root):
        data = _read_json(path)
        if data:
            out.append(data)
    return out


# --- Approvals / rejections -------------------------------------------------
def load_approvals(logs_root: Path | None = None) -> list[dict[str, Any]]:
    """All approval records, most recent (mtime) first."""
    return _load_record_dir((logs_root or config.LOGS_DIR) / "approvals")


def load_rejections(logs_root: Path | None = None) -> list[dict[str, Any]]:
    """All rejection records, most recent (mtime) first."""
    return _load_record_dir((logs_root or config.LOGS_DIR) / "rejections")


def _load_record_dir(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    files = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[dict[str, Any]] = []
    for path in files:
        data = _read_json(path)
        if data:
            out.append(data)
    return out


# --- CDK regen runs ---------------------------------------------------------
def find_cdk_regen_gate_report(run_id: str, logs_root: Path | None = None) -> dict[str, Any] | None:
    """Load the winning/final gate report for a regen run id from disk."""
    run_dir = (logs_root or config.LOGS_DIR) / "cdk_regen" / run_id
    candidates = [
        run_dir / "passed" / "gate_report.json",
        run_dir / "failed" / "final_gate_report.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return _read_json(candidate)
    return None


# --- Score / decision presentation -----------------------------------------
def decision_of(gate_report: dict[str, Any] | None) -> str:
    if not gate_report:
        return "reject"
    return str(gate_report.get("decision", "reject")).lower()


def format_score_color(score: float) -> str:
    """Pick a color for a 0-100 gate score (lower is safer)."""
    if score <= config.GATE_PASS_MAX:
        return config.SEVERITY_COLOR["low"]
    if score <= config.GATE_REVIEW_MAX:
        return config.SEVERITY_COLOR["medium"]
    return config.SEVERITY_COLOR["critical"]


# --- Internal ---------------------------------------------------------------
def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
