"""CDK deployment control functions."""
import os
import subprocess
from datetime import datetime
from pathlib import Path

import streamlit as st

from ExecComponent.exec_code import exec_code
from pipeline.cdk_pipeline import can_deploy, run_iac_gate
from ui.config import GENERATED_CDK_DIR, CDK_JSON_CONTENT, CDK_REQUIREMENTS_CONTENT
from ui.exec_control import drain_process_output


def get_generated_cdk_source() -> str | None:
    """Get generated CDK source code from latest run."""
    run_results = st.session_state.get("run_results") or {}
    generated_code = run_results.get("generated_code")
    if generated_code:
        return generated_code

    root_dir = Path(__file__).resolve().parents[1]
    generated_code_path = root_dir / "ExecCode" / "generated_code.py"
    if generated_code_path.exists():
        return generated_code_path.read_text(encoding="utf-8")
    return None


def reset_cdk_command_state() -> None:
    """Reset CDK command state."""
    st.session_state.cdk_terminal_output = ""
    st.session_state.cdk_return_code = None
    st.session_state.cdk_command_name = ""
    st.session_state.cdk_error = ""


def cdk_deploy_allowed() -> tuple[bool, str]:
    return can_deploy(
        st.session_state.get("cdk_gate_report"),
        manual_review_approved=bool(st.session_state.get("cdk_manual_review_approved")),
    )


def build_cdk_env() -> dict[str, str]:
    """Build the CDK command environment from local defaults."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    region = env.get("CDK_DEFAULT_REGION") or env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or "us-east-1"
    env["CDK_DEFAULT_REGION"] = region
    env["AWS_REGION"] = region
    env["AWS_DEFAULT_REGION"] = region

    if not env.get("CDK_DEFAULT_ACCOUNT"):
        try:
            venv_python = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python"
            if venv_python.exists():
                result = subprocess.run(
                    [
                        str(venv_python),
                        "-c",
                        "import boto3; print(boto3.client('sts').get_caller_identity()['Account'])",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30,
                )
                account = result.stdout.strip()
                if account:
                    env["CDK_DEFAULT_ACCOUNT"] = account
        except Exception:
            pass

    return env


def prepare_generated_cdk_project() -> Path | None:
    """Prepare a CDK project from generated code."""
    generated_code = get_generated_cdk_source()
    if not generated_code:
        st.session_state.cdk_error = "No generated code available. Run the pipeline first."
        st.session_state.cdk_prepared = False
        st.session_state.cdk_synth_ok = False
        st.session_state.cdk_diff_ok = False
        return None

    GENERATED_CDK_DIR.mkdir(parents=True, exist_ok=True)
    (GENERATED_CDK_DIR / "app.py").write_text(generated_code, encoding="utf-8")
    (GENERATED_CDK_DIR / "cdk.json").write_text(CDK_JSON_CONTENT, encoding="utf-8")
    (GENERATED_CDK_DIR / "requirements.txt").write_text(CDK_REQUIREMENTS_CONTENT, encoding="utf-8")

    st.session_state.cdk_project_dir = str(GENERATED_CDK_DIR)
    st.session_state.cdk_prepared = True
    st.session_state.cdk_synth_ok = False
    st.session_state.cdk_diff_ok = False
    st.session_state.cdk_running = False
    st.session_state.cdk_process = None
    st.session_state.cdk_gate_report = None
    st.session_state.cdk_manual_review_approved = False
    reset_cdk_command_state()
    return GENERATED_CDK_DIR


def build_cdk_command(command_name: str) -> list[str]:
    """Build a CDK command."""
    command = ["cdk", command_name]
    if command_name == "deploy":
        command.extend(["--all", "--require-approval", "never"])
    return command


def log_cdk_session(project_dir: Path, command_name: str, return_code: int | None, output: str) -> Path:
    """Log CDK command session."""
    log_dir = project_dir / "command_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    log_path = log_dir / f"{command_name}_{timestamp}.log"
    command_text = " ".join(build_cdk_command(command_name))
    log_content = (
        f"Command: {command_text}\n"
        f"Return code: {return_code}\n"
        "\n"
        "Output:\n"
        f"{output}\n"
    )
    log_path.write_text(log_content, encoding="utf-8")
    return log_path


def start_cdk_command_from_state(command_name: str) -> None:
    """Start a CDK command from session state."""
    project_dir = Path(st.session_state.cdk_project_dir) if st.session_state.cdk_project_dir else GENERATED_CDK_DIR
    if not project_dir.exists():
        st.session_state.cdk_error = "Generated CDK project not found. Prepare the project first."
        st.session_state.cdk_running = False
        st.session_state.cdk_process = None
        return

    if command_name == "deploy":
        allowed, reason = cdk_deploy_allowed()
        if not allowed:
            st.session_state.cdk_error = reason
            st.session_state.cdk_running = False
            st.session_state.cdk_process = None
            return

    env = build_cdk_env()

    st.session_state.cdk_terminal_output = ""
    st.session_state.cdk_return_code = None
    st.session_state.cdk_command_name = command_name
    st.session_state.cdk_error = ""
    st.session_state.cdk_process = exec_code.start_command(build_cdk_command(command_name), cwd=str(project_dir), env=env)
    st.session_state.cdk_running = True

    if st.session_state.cdk_process:
        new_output = drain_process_output(st.session_state.cdk_process)
        if new_output:
            st.session_state.cdk_terminal_output += new_output


def refresh_cdk_output_from_state() -> None:
    """Refresh CDK output and check command status."""
    if st.session_state.cdk_process and st.session_state.cdk_running:
        new_output = drain_process_output(st.session_state.cdk_process)
        if new_output:
            st.session_state.cdk_terminal_output += new_output
        if st.session_state.cdk_process.poll() is not None:
            st.session_state.cdk_return_code = st.session_state.cdk_process.returncode
            st.session_state.cdk_running = False
            st.session_state.cdk_process = None

            command_name = st.session_state.cdk_command_name
            if command_name == "synth":
                st.session_state.cdk_synth_ok = st.session_state.cdk_return_code == 0
                if st.session_state.cdk_return_code != 0:
                    st.session_state.cdk_diff_ok = False
                    st.session_state.cdk_gate_report = None
                    st.session_state.cdk_manual_review_approved = False
                else:
                    project_dir = Path(st.session_state.cdk_project_dir) if st.session_state.cdk_project_dir else GENERATED_CDK_DIR
                    env = build_cdk_env()
                    region = env.get("CDK_DEFAULT_REGION") or "us-east-1"
                    run_id = f"cdk_{datetime.now().strftime('%Y%m%dT%H%M%SZ')}"
                    st.session_state.cdk_gate_report = run_iac_gate(
                        project_dir,
                        run_id=run_id,
                        region=region,
                    )
                    st.session_state.cdk_gate_report_path = (
                        st.session_state.cdk_gate_report.get("report_path")
                    )
                    st.session_state.cdk_manual_review_approved = False
            elif command_name == "diff":
                st.session_state.cdk_diff_ok = st.session_state.cdk_return_code == 0
            project_dir = Path(st.session_state.cdk_project_dir) if st.session_state.cdk_project_dir else GENERATED_CDK_DIR
            if project_dir.exists() and command_name:
                log_cdk_session(
                    project_dir=project_dir,
                    command_name=command_name,
                    return_code=st.session_state.cdk_return_code,
                    output=st.session_state.cdk_terminal_output,
                )


def stop_cdk_command_from_state() -> None:
    """Stop a running CDK command."""
    if st.session_state.cdk_process:
        st.session_state.cdk_process.terminate()
    st.session_state.cdk_running = False
    st.session_state.cdk_process = None


def sync_cdk_process_state() -> None:
    """Sync CDK process state."""
    if st.session_state.cdk_process:
        refresh_cdk_output_from_state()
    elif st.session_state.cdk_running:
        st.session_state.cdk_running = False
