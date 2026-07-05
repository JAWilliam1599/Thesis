"""Subprocess orchestration for the three pipeline stages.

Each stage shells out to an existing project script. Credentials are injected
into the child process environment (never as CLI args, to avoid shell-history
leakage) by merging the values returned from :mod:`ui.credentials`.

Run IDs are generated here and passed explicitly via ``--run-id`` so the
resulting gate report can be located deterministically on disk afterwards.
"""
from __future__ import annotations

import os
import json
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Callable

from ui import config, credentials, helpers


def make_run_id() -> str:
    return "cdk_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def make_hybrid_run_id() -> str:
    return "hybrid_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _build_env(logs_root: Path | None = None) -> dict[str, str]:
    """Copy os.environ and overlay stored credentials as env vars.

    When *logs_root* points at a non-default project directory, the pipeline
    subprocess is redirected there via SYSSECOPS_LOG_DIR so every artifact
    (gate reports, approvals, rejections, regen runs, hybrid reports) stays
    project-scoped.
    """
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    if logs_root is not None and Path(logs_root) != config.LOGS_DIR:
        env["SYSSECOPS_LOG_DIR"] = str(logs_root)
    else:
        env.pop("SYSSECOPS_LOG_DIR", None)

    creds = credentials.load_credentials()
    if creds.get("access_key"):
        env["AWS_ACCESS_KEY_ID"] = creds["access_key"]
    if creds.get("secret_key"):
        env["AWS_SECRET_ACCESS_KEY"] = creds["secret_key"]
    if creds.get("session_token"):
        env["AWS_SESSION_TOKEN"] = creds["session_token"]
    else:
        env.pop("AWS_SESSION_TOKEN", None)
    if creds.get("region"):
        env["AWS_DEFAULT_REGION"] = creds["region"]
        env["AWS_REGION"] = creds["region"]
    if creds.get("openrouter_key"):
        env["OPENROUTER_API_KEY"] = creds["openrouter_key"]
    if creds.get("infracost_key"):
        env["INFRACOST_API_KEY"] = creds["infracost_key"]
    if creds.get("tailscale_key"):
        env["TAILSCALE_API_KEY"] = creds["tailscale_key"]
    if creds.get("tailscale_tailnet"):
        env["TAILSCALE_TAILNET"] = creds["tailscale_tailnet"]
    return env


def stream_subprocess(
    args: list[str],
    on_line: Callable[[str], None] | None = None,
    timeout: float | None = None,
    logs_root: Path | None = None,
) -> tuple[int, str]:
    """Run a command from the repo root, streaming merged stdout/stderr.

    Returns ``(return_code, full_output)``. ``on_line`` is invoked per line
    for live UI updates when provided.

    When ``timeout`` is set, the process is killed if it produces no completion
    within that many seconds (wall-clock). A timeout yields return code 124 so
    callers can distinguish a hang from a normal non-zero exit. A reader thread
    is used so the wall-clock deadline is enforced even when the child emits no
    output at all (e.g. a hung interactive prompt).
    """
    env = _build_env(logs_root)
    lines: list[str] = []
    process = subprocess.Popen(
        args,
        cwd=str(config.ROOT_DIR),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None

    if timeout is None:
        for raw in process.stdout:
            line = raw.rstrip("\n")
            lines.append(line)
            if on_line is not None:
                on_line(line)
        process.wait()
        return process.returncode, "\n".join(lines)

    # Timeout path: drain stdout on a background thread so the main thread can
    # enforce a wall-clock deadline even when no output arrives.
    queue: Queue[str | None] = Queue()

    def _reader() -> None:
        try:
            for raw in process.stdout:  # type: ignore[union-attr]
                queue.put(raw)
        finally:
            queue.put(None)  # sentinel: stdout closed

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()

    deadline = datetime.now(timezone.utc).timestamp() + timeout
    stdout_done = False
    while True:
        remaining = deadline - datetime.now(timezone.utc).timestamp()
        if remaining <= 0:
            process.kill()
            timeout_msg = (
                f"[ui] Deploy exceeded {int(timeout)}s without completing — "
                "killing the process. Check the AWS CloudFormation console for "
                "the stack's real status (it may have rolled back)."
            )
            lines.append(timeout_msg)
            if on_line is not None:
                on_line(timeout_msg)
            process.wait()
            return 124, "\n".join(lines)
        try:
            item = queue.get(timeout=min(remaining, 1.0))
        except Empty:
            continue
        if item is None:
            stdout_done = True
            break
        line = item.rstrip("\n")
        lines.append(line)
        if on_line is not None:
            on_line(line)

    if stdout_done:
        try:
            process.wait(timeout=max(deadline - datetime.now(timezone.utc).timestamp(), 0))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            return 124, "\n".join(lines)
    return process.returncode, "\n".join(lines)


# --- Stage 1: generate + synth + gate (+ regen loop) ------------------------
def run_generate_stage(
    settings: dict[str, Any],
    prompt: str,
    on_line: Callable[[str], None] | None = None,
    logs_root: Path | None = None,
) -> dict[str, Any]:
    """Generate CDK code and run the gate via AIgen/run_cdk_regen.py."""
    run_id = make_run_id()
    args = [
        sys.executable,
        str(config.REGEN_SCRIPT),
        "--prompt", prompt,
        "--project-dir", str(config.GENERATED_CDK_DIR),
        "--provider", settings.get("provider", "bedrock"),
        "--max-attempts", str(settings.get("max_regen_attempts", 2)),
        "--run-id", run_id,
    ]
    if settings.get("model_id"):
        args += ["--model-id", settings["model_id"]]
    if settings.get("region"):
        args += ["--region", settings["region"]]

    return_code, logs = stream_subprocess(args, on_line, logs_root=logs_root)

    gate_report = helpers.find_cdk_regen_gate_report(run_id, logs_root)
    code = _read_generated_code()

    return {
        "return_code": return_code,
        "logs": logs,
        "run_id": run_id,
        "gate_report": gate_report,
        "decision": helpers.decision_of(gate_report),
        "approve_run_id": (gate_report or {}).get("run_id", run_id),
        "code": code,
    }


# --- Edit loop: synth + gate only (no deploy) -------------------------------
def run_synth_gate_stage(
    settings: dict[str, Any],
    on_line: Callable[[str], None] | None = None,
    logs_root: Path | None = None,
) -> dict[str, Any]:
    """Re-run synth + gate on the current GeneratedCDK/app.py (no deploy)."""
    run_id = make_run_id()
    args = [
        sys.executable,
        str(config.PIPELINE_SCRIPT),
        "--project-dir", str(config.GENERATED_CDK_DIR),
        "--run-id", run_id,
    ]
    args += _scanner_flags(settings)

    return_code, logs = stream_subprocess(args, on_line, logs_root=logs_root)

    report_path = (logs_root or config.LOGS_DIR) / "gate_reports" / f"gate_{run_id}.json"
    gate_report = helpers.load_gate_report(report_path) if report_path.exists() else helpers.newest_gate_report(logs_root)

    return {
        "return_code": return_code,
        "logs": logs,
        "run_id": run_id,
        "gate_report": gate_report,
        "decision": helpers.decision_of(gate_report),
        "approve_run_id": (gate_report or {}).get("run_id", run_id),
    }


# --- Stage 4: deploy --------------------------------------------------------
def run_deploy_stage(
    approve_run_id: str,
    manual_approve: bool,
    on_line: Callable[[str], None] | None = None,
    logs_root: Path | None = None,
) -> dict[str, Any]:
    """Approve an existing gate report and deploy via scripts/run_cdk_pipeline.py."""
    args = [
        sys.executable,
        str(config.PIPELINE_SCRIPT),
        "--project-dir", str(config.GENERATED_CDK_DIR),
        "--approve-run-id", approve_run_id,
        "--deploy",
    ]
    if manual_approve:
        args.append("--manual-approve")

    return_code, logs = stream_subprocess(
        args, on_line, timeout=config.DEPLOY_TIMEOUT_SECONDS, logs_root=logs_root
    )
    return {"return_code": return_code, "logs": logs}


# --- Hybrid workflow: gate (and optional deploy) both branches --------------
def run_hybrid_stage(
    settings: dict[str, Any],
    project: dict[str, Any],
    on_line: Callable[[str], None] | None = None,
    logs_root: Path | None = None,
    deploy: bool = False,
    manual_approve: bool = False,
) -> dict[str, Any]:
    """Run scripts/run_hybrid_pipeline.py for the project's CDK/Ansible dirs.

    Gates each configured branch; with ``deploy=True`` it also deploys every
    branch the gate allows (``manual_approve`` covers the review band).
    Returns the combined hybrid report parsed from logs.
    """
    run_id = make_hybrid_run_id()
    args = [sys.executable, str(config.HYBRID_SCRIPT), "--run-id", run_id]

    if project.get("cdk_path"):
        args += ["--cdk-path", project["cdk_path"]]
    if project.get("ansible_path"):
        args += ["--ansible-path", project["ansible_path"]]
    if project.get("playbook"):
        args += ["--playbook", project["playbook"]]
    if project.get("inventory"):
        args += ["--inventory", project["inventory"]]
    if project.get("target_host"):
        args += ["--target-host", project["target_host"]]

    args += _scanner_flags(settings)
    args += _hybrid_only_flags(settings)
    if deploy:
        args.append("--deploy")
        if manual_approve:
            args.append("--manual-approve")

    timeout = config.DEPLOY_TIMEOUT_SECONDS if deploy else None
    return_code, logs = stream_subprocess(args, on_line, timeout=timeout, logs_root=logs_root)

    report_path = (logs_root or config.LOGS_DIR) / f"{run_id}.json"
    hybrid_report: dict[str, Any] | None = None
    if report_path.exists():
        try:
            hybrid_report = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            hybrid_report = None

    return {
        "return_code": return_code,
        "logs": logs,
        "run_id": run_id,
        "hybrid_report": hybrid_report,
        "report_path": str(report_path),
    }


# --- Internal ---------------------------------------------------------------
def _scanner_flags(settings: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if not settings.get("use_checkov", True):
        flags.append("--no-checkov")
    if not settings.get("use_cfn_lint", True):
        flags.append("--no-cfn-lint")
    if not settings.get("use_infracost", True):
        flags.append("--no-infracost")
    if not settings.get("use_aws_config", True):
        flags.append("--no-aws-config")
    if not settings.get("use_ml_risk", True):
        flags.append("--no-ml-risk")
    return flags


def _hybrid_only_flags(settings: dict[str, Any]) -> list[str]:
    """Ansible-branch flags accepted only by run_hybrid_pipeline.py."""
    flags: list[str] = []
    if not settings.get("use_ansible_lint", True):
        flags.append("--no-ansible-lint")
    if not settings.get("use_secret_scan", True):
        flags.append("--no-secret-scan")
    return flags


def _read_generated_code() -> str:
    if config.GENERATED_CDK_APP.exists():
        try:
            return config.GENERATED_CDK_APP.read_text(encoding="utf-8")
        except OSError:
            return ""
    return ""
