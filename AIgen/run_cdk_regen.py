"""CDK-specific regen feedback loop.

Re-invokes AIgen code generation using gate findings as structured feedback,
then runs synth + gate to validate the new code. Loops up to max_attempts.

Usage (CLI):
    python AIgen/run_cdk_regen.py \\
        --prompt "Create an S3 bucket with versioning" \\
        --project-dir GeneratedCDK \\
        --max-attempts 3 \\
        --provider bedrock \\
        --run-id cdk_20260614T120000Z

Artifacts written to:
    logs/cdk_regen/<run_id>/prompt.txt
    logs/cdk_regen/<run_id>/attempt_<N>/code.py
    logs/cdk_regen/<run_id>/attempt_<N>/gate_report.json
    logs/cdk_regen/<run_id>/attempt_<N>/prompt.txt
    logs/cdk_regen/<run_id>/passed/   (symlink or copy of winning attempt dir)
    logs/cdk_regen/<run_id>/failed/   (all failed attempt dirs)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.cdk_pipeline import clear_cdk_out, run_cdk_command, run_iac_gate
from env_bootstrap import load_env

logger = logging.getLogger(__name__)

_DEFAULT_REGEN_LOG_DIR = ROOT_DIR / "logs" / "cdk_regen"

CDK_SYSTEM_INSTRUCTION = (
    "You are a CDK infrastructure code generator. Return only executable Python code and no markdown. "
    "Generate a complete AWS CDK application that is ready to synthesize and deploy. "
    "At the very top of the file, include a short instructions block using comments in this exact format: "
    "'# INSTRUCTIONS:' then one instruction per line prefixed with '# ', then '# END INSTRUCTIONS'. "
    "The instructions must describe how to bootstrap, synthesize, and deploy the stack. "
    "Rules: "
    "(1) The file must include App(), at least one Stack, and app.synth(). "
    "(2) Do not place input() calls inside Stack.__init__ or at import time. "
    "    Use CfnParameter, CDK context, environment variables, or explicit constructor arguments with safe defaults. "
    "(3) The app must run non-interactively with `cdk synth`. "
    "(4) Use only aws-cdk-lib constructs; do not mix boto3 infrastructure definitions with CDK constructs. "
    "(5) Apply least-privilege IAM roles; avoid wildcards (*) on sensitive actions. "
    "(6) Encrypt S3 buckets, RDS instances, and EBS volumes by default. "
    "(7) Do not expose SSH (port 22) or RDP (port 3389) to 0.0.0.0/0. "
    "(8) Use RemovalPolicy.RETAIN for stateful resources unless the user explicitly requests DESTROY."
)


def build_cdk_regen_prompt(
    original_prompt: str,
    gate_report: dict[str, Any],
    attempt: int,
) -> str:
    """Build a structured regen prompt from gate findings."""
    findings = gate_report.get("findings") or []
    decision = gate_report.get("decision", "reject")
    score = gate_report.get("score", 0)

    findings_text = ""
    if findings:
        lines = []
        for i, f in enumerate(findings, 1):
            severity = f.get("severity", "unknown").upper()
            source = f.get("source", "unknown")
            message = f.get("message", "")
            resource = f.get("resource_id", "")
            template = f.get("template", "")
            line = f"{i}. [{severity}] {message}"
            if resource:
                line += f" (resource: {resource})"
            if template:
                line += f" [template: {template}]"
            line += f" — detected by {source}"
            lines.append(line)
        findings_text = "\n".join(lines)
    else:
        findings_text = "No specific findings recorded."

    return (
        f"The previous CDK code failed the IaC security gate (attempt {attempt}).\n"
        f"Gate decision: {decision} | Score: {score} (threshold: pass ≤ 20, review ≤ 80, reject > 80)\n\n"
        f"Original user request:\n{original_prompt}\n\n"
        f"Security gate findings that must be fixed:\n{findings_text}\n\n"
        "Requirements:\n"
        "1) Fix ALL findings listed above.\n"
        "2) Return a complete, synthesizable AWS CDK Python app (App(), Stack, app.synth()).\n"
        "3) No input() calls inside Stack.__init__ or at import time.\n"
        "4) The app must run non-interactively with `cdk synth`.\n"
        "5) Apply least-privilege IAM; avoid wildcard actions on sensitive resources.\n"
        "6) Encrypt stateful resources (S3, RDS, EBS) by default.\n"
        "7) Do not expose SSH (port 22) or RDP (port 3389) to the public internet.\n"
        "8) Return only Python code — no markdown, no explanations."
    )


def _call_bedrock(prompt: str, model_id: str, region: str | None) -> str:
    from AIgen.bedrock_codegen import call_bedrock, SYSTEM_INSTRUCTION  # noqa: F401
    import boto3
    import re

    client = boto3.client("bedrock-runtime", region_name=region)
    response = client.converse(
        modelId=model_id,
        system=[{"text": CDK_SYSTEM_INSTRUCTION}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 4096, "temperature": 0.2},
    )
    content_blocks = response.get("output", {}).get("message", {}).get("content", [])
    raw = "\n".join(block.get("text", "") for block in content_blocks if "text" in block)
    # Strip fenced code blocks if present
    fenced = re.findall(r"```(?:python)?\n([\s\S]*?)```", raw, flags=re.IGNORECASE)
    return (fenced[0].strip() + "\n") if fenced else (raw.strip() + "\n")


def _clean_synth_error(raw: str) -> str:
    """Strip jsii/node banner noise from synth output, keeping only the Python traceback."""
    import re as _re

    noise_patterns = (
        r"<frozen ",
        r"RuntimeWarning",
        r"This software has not been tested",
        r"Should you encounter odd runtime",
        r"This software is currently running",
        r"As of the current release",
        r"Planned end-of-life",
        r"This warning can be silenced",
        r"JSII_SILENCE_WARNING",
        r"^\s*$",
    )
    noise_re = _re.compile("|".join(noise_patterns))
    clean_lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        # Drop raw bytes repr lines: b'!!...'
        if stripped.startswith("b'") or stripped.startswith('b"'):
            continue
        if noise_re.search(line):
            continue
        clean_lines.append(line)
    result = "\n".join(clean_lines).strip()
    # If nothing survived (pure noise), fall back to the last 1000 chars of raw
    return result if result else raw[-1000:].strip()


def _call_openrouter(prompt: str, model_id: str, api_key: str, api_url: str) -> str:
    from AIgen.openrouter_codegen import call_openrouter

    return call_openrouter(
        user_request=prompt,
        model_id=model_id,
        api_key=api_key,
        api_url=api_url,
    )


def run_cdk_regen_loop(
    original_prompt: str,
    project_dir: Path,
    *,
    max_attempts: int = 2,
    provider: str = "bedrock",
    run_id: str | None = None,
    model_id: str | None = None,
    region: str | None = None,
    api_key: str | None = None,
    api_url: str | None = None,
    log_dir: Path | None = None,
) -> dict[str, Any]:
    """Run CDK regen loop: generate → synth → gate → repeat on reject.

    Returns a result dict with keys:
        success (bool), attempts (list), final_decision (str), run_id (str)
    """
    if run_id is None:
        run_id = f"cdk_{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    regen_root = (Path(log_dir) if log_dir else _DEFAULT_REGEN_LOG_DIR) / run_id
    regen_root.mkdir(parents=True, exist_ok=True)

    # Save original prompt
    (regen_root / "prompt.txt").write_text(original_prompt, encoding="utf-8")

    # Resolve generation parameters
    if provider == "bedrock":
        _model_id = model_id or os.environ.get("BEDROCK_MODEL_ID", "qwen.qwen3-coder-30b-a3b-v1:0")
        _region = region or os.environ.get("AWS_REGION", "ap-southeast-2")
    else:
        _model_id = model_id or os.environ.get("OPENROUTER_MODEL_ID", "qwen/qwen3-coder-30b-a3b-instruct")
        _api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        _api_url = api_url or os.environ.get("OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions")
        if not _api_key:
            return {
                "success": False,
                "run_id": run_id,
                "error": "OPENROUTER_API_KEY not set and --api-key not provided.",
                "attempts": [],
                "final_decision": "error",
            }

    attempts: list[dict[str, Any]] = []
    current_prompt = build_cdk_regen_prompt(original_prompt, {}, attempt=0)
    # First attempt uses just the original request as a CDK-focused prompt
    current_prompt = (
        f"Generate a complete AWS CDK Python application for this request:\n{original_prompt}\n\n"
        "Requirements:\n"
        "1) Return only Python code — no markdown, no commentary, no triple backticks.\n"
        "2) Define EXACTLY ONE Stack class. Do not define multiple stacks or helper stacks.\n"
        "3) Include a single App() instantiation, instantiate only that one Stack, and call app.synth().\n"
        "4) No input() at import time or in Stack.__init__.\n"
        "5) Apply least-privilege IAM; no wildcard actions on sensitive resources.\n"
        "6) Encrypt stateful resources by default.\n"
        "7) Do not expose SSH/RDP to 0.0.0.0/0.\n"
        "8) The app must synthesize non-interactively with `cdk synth`."
    )

    gate_report: dict[str, Any] = {}

    for attempt_num in range(1, max_attempts + 1):
        attempt_dir = regen_root / f"attempt_{attempt_num}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        (attempt_dir / "prompt.txt").write_text(current_prompt, encoding="utf-8")

        logger.info("CDK regen attempt %d/%d run_id=%s provider=%s", attempt_num, max_attempts, run_id, provider)

        # Generate code
        try:
            if provider == "bedrock":
                code = _call_bedrock(current_prompt, _model_id, _region)
            else:
                code = _call_openrouter(current_prompt, _model_id, _api_key, _api_url)
        except Exception as exc:
            err = str(exc)
            logger.error("CDK regen attempt %d generation failed: %s", attempt_num, err)
            attempts.append({"attempt": attempt_num, "stage": "generation", "error": err})
            break

        code_path = attempt_dir / "code.py"
        code_path.write_text(code, encoding="utf-8")

        # Write code to CDK project
        app_py = project_dir / "app.py"
        app_py.write_text(code, encoding="utf-8")

        # Clear stale cdk.out templates before synth so the gate only sees
        # templates from the current app.py, not leftovers from prior attempts.
        clear_cdk_out(project_dir)

        # Run synth
        synth = run_cdk_command(project_dir, "synth")
        if synth["return_code"] != 0:
            logger.warning("CDK regen attempt %d synth failed", attempt_num)
            raw_synth_output = synth.get("output", "")
            (attempt_dir / "synth_output.txt").write_text(raw_synth_output, encoding="utf-8")
            attempts.append({"attempt": attempt_num, "stage": "synth", "return_code": synth["return_code"]})
            if attempt_num < max_attempts:
                clean_error = _clean_synth_error(raw_synth_output)
                current_code = (attempt_dir / "code.py").read_text(encoding="utf-8")
                current_prompt = (
                    f"The previous CDK app failed to synthesize (attempt {attempt_num}).\n\n"
                    f"Original user request:\n{original_prompt}\n\n"
                    f"Synth error:\n{clean_error}\n\n"
                    f"Failing code:\n{current_code}\n\n"
                    "Fix the error above and return the corrected complete CDK Python app. "
                    "No input() at import time or in Stack.__init__. Return only Python code."
                )
            continue

        # Run gate
        attempt_run_id = f"{run_id}_a{attempt_num}"
        gate_report = run_iac_gate(project_dir, run_id=attempt_run_id)
        (attempt_dir / "gate_report.json").write_text(
            json.dumps(gate_report, indent=2), encoding="utf-8"
        )

        decision = str(gate_report.get("decision", "reject")).lower()
        score = gate_report.get("score", 0)
        logger.info("CDK regen attempt %d gate=%s score=%s", attempt_num, decision, score)

        attempt_record = {
            "attempt": attempt_num,
            "stage": "gate",
            "decision": decision,
            "score": score,
            "gate_run_id": attempt_run_id,
        }
        attempts.append(attempt_record)

        if decision in ("pass", "review"):
            # Success — record winning artifact
            passed_dir = regen_root / "passed"
            passed_dir.mkdir(exist_ok=True)
            (passed_dir / "code.py").write_text(code, encoding="utf-8")
            (passed_dir / "gate_report.json").write_text(
                json.dumps(gate_report, indent=2), encoding="utf-8"
            )
            (passed_dir / "attempt_number.txt").write_text(str(attempt_num), encoding="utf-8")
            return {
                "success": True,
                "run_id": run_id,
                "final_decision": decision,
                "final_score": score,
                "winning_attempt": attempt_num,
                "code_path": str(app_py),
                "passed_dir": str(passed_dir),
                "gate_report": gate_report,
                "attempts": attempts,
            }

        # Gate rejected — build regen prompt for next iteration
        if attempt_num < max_attempts:
            current_prompt = build_cdk_regen_prompt(original_prompt, gate_report, attempt=attempt_num)

    # All attempts exhausted
    failed_dir = regen_root / "failed"
    failed_dir.mkdir(exist_ok=True)
    (failed_dir / "final_gate_report.json").write_text(
        json.dumps(gate_report, indent=2), encoding="utf-8"
    )
    return {
        "success": False,
        "run_id": run_id,
        "final_decision": gate_report.get("decision", "reject"),
        "final_score": gate_report.get("score"),
        "attempts": attempts,
        "failed_dir": str(failed_dir),
        "gate_report": gate_report,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CDK regen loop: generate → synth → gate → retry on reject.")
    parser.add_argument("--prompt", required=True, help="Original CDK infrastructure request.")
    parser.add_argument("--project-dir", default="GeneratedCDK", help="CDK project directory.")
    parser.add_argument("--max-attempts", type=int, default=2, help="Maximum regen attempts (default: 2).")
    parser.add_argument("--provider", choices=["bedrock", "openrouter"], default="bedrock", help="Generation provider.")
    parser.add_argument("--run-id", default=None, help="Override auto-generated run ID.")
    parser.add_argument("--model-id", default=None, help="Model ID override.")
    parser.add_argument("--region", default=None, help="AWS region (Bedrock).")
    parser.add_argument("--api-key", default=None, help="OpenRouter API key.")
    parser.add_argument("--api-url", default=None, help="OpenRouter API URL override.")
    return parser.parse_args()


def main() -> int:
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    project_dir = Path(args.project_dir).resolve()
    if not project_dir.exists():
        print(json.dumps({"error": f"project-dir not found: {project_dir}"}))
        return 2

    result = run_cdk_regen_loop(
        original_prompt=args.prompt,
        project_dir=project_dir,
        max_attempts=args.max_attempts,
        provider=args.provider,
        run_id=args.run_id,
        model_id=args.model_id,
        region=args.region,
        api_key=args.api_key,
        api_url=args.api_url,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 22


if __name__ == "__main__":
    raise SystemExit(main())
