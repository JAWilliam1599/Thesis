"""ML risk adapter: logistic-regression risk score for generated Python IaC code.

Uses the model trained in ``risk_scoring/`` (bandit + semgrep finding
counts -> P(insecure)). Feature extraction mirrors
``risk_scoring/GeneratingSecureCode.py`` exactly (same tools, same
severity mapping, per-file scanning) so inference matches the training
distribution.

The adapter scans every eligible ``*.py`` file under the given source
directory, predicts a probability per file, and reports the worst (max)
probability. The gate converts it to points: ``ml_score = round(p * 20)``.

Status values returned:
    ok             – model ran and produced a probability
    skipped        – disabled by caller
    not_installed  – bandit/semgrep binary or sklearn/joblib import missing
    model_missing  – .pkl artifacts not found (run risk_scoring/LogisticRegression.py)
    no_python_files – no eligible Python files under source_dir
    error          – unexpected subprocess/model failure
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Any

_OK_STATUS = "ok"
_SKIPPED_STATUS = "skipped"
_NOT_INSTALLED_STATUS = "not_installed"
_MODEL_MISSING_STATUS = "model_missing"
_NO_FILES_STATUS = "no_python_files"
_ERROR_STATUS = "error"

# Points added to the gate score at P(insecure) == 1.0.
ML_MAX_POINTS = 20

# Feature order must match the training dataset columns
# (dataset.csv minus sample_id/label — see scaler.feature_names_in_).
_FEATURE_ORDER = [
    "bandit_high",
    "bandit_medium",
    "bandit_low",
    "bandit_conf_high",
    "bandit_conf_medium",
    "bandit_conf_low",
    "semgrep_high",
    "semgrep_medium",
    "semgrep_low",
    "total_bandit",
    "total_semgrep",
]

_MODEL_DIR = Path(__file__).resolve().parents[2] / "risk_scoring"
_MODEL_PATH = _MODEL_DIR / "logistic_regression.pkl"
_SCALER_PATH = _MODEL_DIR / "scaler.pkl"

_EXCLUDED_DIRS = {"cdk.out", "__pycache__", ".venv", "node_modules", ".git"}
_MAX_FILES = 25
_MAX_FILE_BYTES = 200_000


def _resolve_executable(name: str) -> str:
    """Return the absolute path to *name*, preferring the active venv's bin dir."""
    venv_bin = Path(sys.executable).parent
    candidate = venv_bin / name
    if candidate.is_file():
        return str(candidate)
    found = shutil.which(name)
    return found if found else name


def _result(status: str, message: str, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "status": status,
        "probability": 0.0,
        "ml_score": 0,
        "files": [],
        "message": message,
    }
    base.update(extra)
    return base


def _eligible_files(source_dir: Path) -> list[Path]:
    """Python files to score. Mirrors the training filter for tests/packages."""
    files: list[Path] = []
    for path in sorted(source_dir.rglob("*.py")):
        if any(part in _EXCLUDED_DIRS for part in path.parts):
            continue
        if path.name == "__init__.py" or path.name.startswith("test_"):
            continue
        if "test" in path.parts or "tests" in path.parts:
            continue
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        files.append(path)
    return files[:_MAX_FILES]


def _run_bandit(file_path: Path) -> dict[str, int] | None:
    """Bandit severity/confidence counts for one file. None => tool unusable."""
    features = {
        "bandit_high": 0,
        "bandit_medium": 0,
        "bandit_low": 0,
        "bandit_conf_high": 0,
        "bandit_conf_medium": 0,
        "bandit_conf_low": 0,
        "total_bandit": 0,
    }
    try:
        proc = subprocess.run(
            [_resolve_executable("bandit"), "-f", "json", str(file_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        return None
    except Exception:
        return features
    if proc.returncode not in (0, 1):
        return features
    try:
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return features
    for finding in data.get("results", []):
        sev = str(finding.get("issue_severity", "")).upper()
        conf = str(finding.get("issue_confidence", "")).upper()
        features["total_bandit"] += 1
        if sev == "HIGH":
            features["bandit_high"] += 1
        elif sev == "MEDIUM":
            features["bandit_medium"] += 1
        elif sev == "LOW":
            features["bandit_low"] += 1
        if conf == "HIGH":
            features["bandit_conf_high"] += 1
        elif conf == "MEDIUM":
            features["bandit_conf_medium"] += 1
        elif conf == "LOW":
            features["bandit_conf_low"] += 1
    return features


def _run_semgrep(file_path: Path) -> dict[str, int] | None:
    """Semgrep severity counts for one file. None => tool unusable."""
    features = {
        "semgrep_high": 0,
        "semgrep_medium": 0,
        "semgrep_low": 0,
        "total_semgrep": 0,
    }
    try:
        proc = subprocess.run(
            [
                _resolve_executable("semgrep"),
                "scan",
                "--config=auto",
                "--json",
                "--quiet",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError:
        return None
    except Exception:
        return features
    if proc.returncode not in (0, 1):
        return features
    try:
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return features
    for finding in data.get("results", []):
        sev = str(finding.get("extra", {}).get("severity", "")).upper()
        features["total_semgrep"] += 1
        if sev in ("ERROR", "HIGH"):
            features["semgrep_high"] += 1
        elif sev in ("WARNING", "MEDIUM"):
            features["semgrep_medium"] += 1
        elif sev in ("INFO", "LOW"):
            features["semgrep_low"] += 1
    return features


def run_ml_risk(
    source_dir: Path,
    *,
    enabled: bool = True,
    max_points: int = ML_MAX_POINTS,
) -> dict[str, Any]:
    """Score the Python source under *source_dir* with the trained model.

    Returns a dict with keys:
        status      – see module docstring
        probability – worst-file P(insecure), 0.0-1.0
        ml_score    – round(probability * max_points)
        files       – per-file [{file, probability, features}] breakdown
        message     – human-readable status detail
    """
    if not enabled:
        return _result(_SKIPPED_STATUS, "ML risk scoring disabled by caller.")

    try:
        import joblib  # noqa: PLC0415 - optional dependency, fail soft
    except ImportError:
        return _result(
            _NOT_INSTALLED_STATUS,
            "joblib/scikit-learn not installed (pip install scikit-learn joblib).",
        )

    if not (_MODEL_PATH.is_file() and _SCALER_PATH.is_file()):
        return _result(
            _MODEL_MISSING_STATUS,
            "Model artifacts not found in risk_scoring/ — run "
            "LogisticRegression.py to train and export them.",
        )

    source_dir = Path(source_dir)
    if not source_dir.is_dir():
        return _result(_NO_FILES_STATUS, f"Source directory not found: {source_dir}")
    files = _eligible_files(source_dir)
    if not files:
        return _result(
            _NO_FILES_STATUS,
            f"No eligible Python files under {source_dir}; ML risk not applied.",
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # sklearn version-skew warnings
            model = joblib.load(_MODEL_PATH)
            scaler = joblib.load(_SCALER_PATH)
    except Exception as exc:
        return _result(_ERROR_STATUS, f"Failed to load model artifacts: {exc}")

    per_file: list[dict[str, Any]] = []
    for path in files:
        bandit = _run_bandit(path)
        if bandit is None:
            return _result(
                _NOT_INSTALLED_STATUS, "bandit is not installed or not on PATH."
            )
        semgrep = _run_semgrep(path)
        if semgrep is None:
            return _result(
                _NOT_INSTALLED_STATUS, "semgrep is not installed or not on PATH."
            )
        features = {**bandit, **semgrep}
        vector = [[features[name] for name in _FEATURE_ORDER]]
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # fitted-with-feature-names warning
                probability = float(model.predict_proba(scaler.transform(vector))[0][1])
        except Exception as exc:
            return _result(_ERROR_STATUS, f"Model inference failed: {exc}")
        try:
            rel = str(path.relative_to(source_dir))
        except ValueError:
            rel = str(path)
        per_file.append(
            {"file": rel, "probability": round(probability, 4), "features": features}
        )

    worst = max(per_file, key=lambda item: item["probability"])
    probability = worst["probability"]
    ml_score = round(probability * max(0, int(max_points)))
    return {
        "status": _OK_STATUS,
        "probability": probability,
        "ml_score": ml_score,
        "files": per_file,
        "message": (
            f"P(insecure)={probability:.2f} across {len(per_file)} file(s) "
            f"(worst: {worst['file']}) -> +{ml_score} point(s)."
        ),
    }
