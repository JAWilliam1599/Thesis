"""Pipeline orchestration and execution."""
import importlib.util
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

from ui.config import ROOT_DIR
from ui.helpers import load_instructions
from ui.reports import extract_json_report


def load_run_generation_module():
    """Dynamically load the run_generation_and_eval module."""
    run_gen_file = ROOT_DIR / "AIgen" / "run_generation_and_eval.py"
    spec = importlib.util.spec_from_file_location("run_generation_and_eval", run_gen_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load run_generation_and_eval module from {run_gen_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_pipeline_with_prompt(
    prompt_text: str,
    provider: str,
    model_id: str,
    region: str | None,
    api_key: str | None,
    fail_below: int,
    max_regen: int,
    verbose: bool,
    show_run_output: bool,
) -> dict:
    """Run the generation and evaluation pipeline with the given prompt."""
    cmd = [
        sys.executable,
        "-u",
        str(ROOT_DIR / "AIgen" / "run_generation_and_eval.py"),
        "--provider",
        provider,
        "--prompt",
        prompt_text,
        "--fail-below",
        str(fail_below),
        "--max-regen",
        str(max_regen),
    ]
    env = os.environ.copy()

    if provider == "bedrock":
        if region:
            cmd.extend(["--region", region])
        if model_id:
            cmd.extend(["--model-id", model_id])
    else:
        if model_id:
            cmd.extend(["--model-id", model_id])
        api_key_input = (api_key or "").strip()
        env_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if api_key_input:
            env["OPENROUTER_API_KEY"] = api_key_input
        elif not env_api_key:
            st.warning("API Key field is empty and OPENROUTER_API_KEY is not set.")

    if verbose:
        cmd.append("--verbose")

    env["PYTHONUNBUFFERED"] = "1"

    live_status = st.empty() if show_run_output else None
    live_log = st.empty() if show_run_output else None
    if live_status is not None:
        live_status.info("Streaming pipeline output in real time...")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(ROOT_DIR / "AIgen"),
        env=env,
        bufsize=1,
    )

    stdout_lines = []
    in_json_report = False
    if process.stdout is not None:
        for line in iter(process.stdout.readline, ""):
            stdout_lines.append(line)
            if live_log is not None:
                stripped = line.lstrip()
                if "Evaluation report:" in line or stripped.startswith("{"):
                    in_json_report = True
                if in_json_report:
                    if stripped.strip() == "}":
                        in_json_report = False
                    continue
                live_log.code("".join(stdout_lines[-400:]), language="text")
        process.stdout.close()

    return_code = process.wait()
    combined_output = "".join(stdout_lines)

    if live_status is not None:
        live_status.empty()

    json_output = extract_json_report(combined_output)

    generated_code = None
    generated_code_path = ROOT_DIR / "ExecCode" / "generated_code.py"
    if generated_code_path.exists():
        generated_code = generated_code_path.read_text(encoding="utf-8")

    generated_instructions = None
    if generated_code_path.exists():
        generated_instructions = load_instructions(generated_code_path, generated_code)

    return {
        "return_code": return_code,
        "stdout": combined_output,
        "stderr": "",
        "json_output": json_output,
        "generated_code": generated_code,
        "generated_instructions": generated_instructions,
        "timestamp": datetime.now().isoformat(),
    }
