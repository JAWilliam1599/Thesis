"""Code execution control functions."""
import os
import select
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

from ExecComponent.exec_code import exec_code


def run_generated_code(code_path: Path) -> dict:
    """Run generated code with line handler for live output."""
    live_log = st.empty()

    def handle_line(_line, lines):
        live_log.code("".join(lines[-400:]), language="text")

    return exec_code.run_file(
        str(code_path),
        cwd=str(code_path.parent),
        line_handler=handle_line,
    )


def start_exec_process(code_path: Path) -> subprocess.Popen:
    """Start execution of generated code in subprocess."""
    return subprocess.Popen(
        [sys.executable, "-u", str(code_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(code_path.parent),
        bufsize=1,
    )


def drain_process_output(process: subprocess.Popen, max_lines: int = 2000) -> str:
    """Read available output from process without blocking."""
    if process.stdout is None:
        return ""

    lines = []
    while True:
        ready, _, _ = select.select([process.stdout], [], [], 0)
        if not ready:
            break
        line = process.stdout.readline()
        if not line:
            break
        lines.append(line)
        if len(lines) >= max_lines:
            break

    return "".join(lines)


def get_attempt_files(run_dir: Path, attempt_type: str) -> dict[str, Path]:
    """Get all attempt files (passed or failed) from a run directory."""
    target_dir = run_dir / attempt_type
    if not target_dir.exists():
        return {}

    json_files = sorted(target_dir.glob("*.json"), reverse=True)
    attempt_map = {}
    for json_file in json_files:
        py_file = json_file.with_suffix(".py")
        if py_file.exists():
            attempt_map[json_file.stem] = py_file
    return attempt_map


def start_exec_from_state() -> None:
    """Start code execution from session state."""
    code_path = Path(st.session_state.exec_code_path) if st.session_state.exec_code_path else None
    if code_path is None or not code_path.exists():
        st.session_state.exec_terminal_output = ""
        st.session_state.exec_process = None
        st.session_state.exec_running = False
        st.session_state.exec_error = "Code file not found for this attempt."
        st.session_state.exec_return_code = None
        st.session_state.exec_logged = False
        return

    st.session_state.exec_terminal_output = ""
    st.session_state.exec_process = start_exec_process(code_path)
    st.session_state.exec_running = True
    st.session_state.exec_error = ""
    st.session_state.exec_return_code = None
    st.session_state.exec_logged = False

    if st.session_state.exec_process:
        new_output = drain_process_output(st.session_state.exec_process)
        if new_output:
            st.session_state.exec_terminal_output += new_output


def stop_exec_from_state() -> None:
    """Stop code execution."""
    if st.session_state.exec_process:
        st.session_state.exec_process.terminate()
    st.session_state.exec_running = False
    st.session_state.exec_process = None


def refresh_exec_output_from_state() -> None:
    """Refresh execution output and check process status."""
    if st.session_state.exec_process and st.session_state.exec_running:
        new_output = drain_process_output(st.session_state.exec_process)
        if new_output:
            st.session_state.exec_terminal_output += new_output
        if st.session_state.exec_process.poll() is not None:
            st.session_state.exec_return_code = st.session_state.exec_process.returncode
            st.session_state.exec_running = False
            st.session_state.exec_process = None
            if not st.session_state.exec_logged and st.session_state.exec_code_path:
                code_path = Path(st.session_state.exec_code_path)
                run_dir = code_path.parent.parent
                log_exec_session(
                    run_dir=run_dir,
                    code_path=code_path,
                    return_code=st.session_state.exec_return_code,
                    output=st.session_state.exec_terminal_output,
                )
                st.session_state.exec_logged = True


def sync_exec_process_state() -> None:
    """Sync execution process state."""
    if st.session_state.exec_process:
        refresh_exec_output_from_state()
    elif st.session_state.exec_running:
        st.session_state.exec_running = False


def log_exec_session(run_dir: Path, code_path: Path, return_code: int | None, output: str) -> Path:
    """Log execution session to file."""
    run_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    log_path = run_dir / f"exec_{timestamp}.log"
    command = f"{sys.executable} -u {code_path}"
    log_content = (
        f"Command: {command}\n"
        f"Return code: {return_code}\n"
        "\n"
        "Output:\n"
        f"{output}\n"
    )
    log_path.write_text(log_content, encoding="utf-8")
    return log_path


def build_exec_regen_prompt(base_prompt: str, error_output: str) -> str:
    """Build regeneration prompt with execution error."""
    trimmed_output = error_output[-4000:] if len(error_output) > 4000 else error_output
    return (
        f"{base_prompt}\n\n"
        "The previous generated code failed during execution. Regenerate and fix the issues.\n\n"
        "Execution error output:\n"
        f"{trimmed_output}\n"
    )


def load_saved_prompt(run_dir: Path) -> str:
    """Load saved prompt from run directory."""
    prompt_path = run_dir / "prompt.txt"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return ""
