import argparse
import datetime
import importlib.util
import json
import logging
import os
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

from bedrock_codegen import (
    DEFAULT_MODEL_ID as BEDROCK_DEFAULT_MODEL_ID,
    DEFAULT_OUTPUT_PATH,
    generate_and_save as generate_and_save_bedrock,
)
from openrouter_codegen import (
    DEFAULT_API_URL as OPENROUTER_DEFAULT_API_URL,
    DEFAULT_MODEL_ID as OPENROUTER_DEFAULT_MODEL_ID,
    OpenRouterError,
    generate_and_save as generate_and_save_openrouter,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT_DIR / "Eval"
DEFAULT_LOG_PATH = ROOT_DIR / "logs" / "generation_and_eval.log"
DEFAULT_FAILED_DIR = ROOT_DIR / "ExecCode" / "failed"
DEFAULT_PASSED_DIR = ROOT_DIR / "ExecCode" / "passed"


def build_runtime_id() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%S%fZ")


def build_runtime_log_path(base_log_path: Path, runtime_id: str) -> Path:
    return base_log_path.with_name(f"{base_log_path.stem}_{runtime_id}{base_log_path.suffix or '.log'}")


def build_runtime_root_dir(base_failed_dir: Path, base_passed_dir: Path, runtime_id: str) -> Path:
    if base_failed_dir.parent == base_passed_dir.parent:
        base_dir = base_failed_dir.parent
    else:
        base_dir = ROOT_DIR / "ExecCode"
    return base_dir / f"run_{runtime_id}"


def build_runtime_failed_dir(runtime_root_dir: Path) -> Path:
    return runtime_root_dir / "failed"


def build_runtime_passed_dir(runtime_root_dir: Path) -> Path:
    return runtime_root_dir / "passed"


def configure_logger(log_path: Path, verbose: bool) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("generation_and_eval")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    if verbose:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
    return logger


def save_failed_code_snapshot(source_path: Path, failed_dir: Path, attempt_number: int, report: dict) -> tuple[Path, Path]:
    failed_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    failed_code_path = failed_dir / f"failed_attempt_{attempt_number}_{timestamp}.py"
    failed_report_path = failed_dir / f"failed_attempt_{attempt_number}_{timestamp}.json"

    code_text = source_path.read_text(encoding="utf-8")
    failed_code_path.write_text(code_text, encoding="utf-8")
    failed_report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return failed_code_path, failed_report_path


def save_passed_code_snapshot(source_path: Path, passed_dir: Path, attempt_number: int, report: dict) -> tuple[Path, Path]:
    passed_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    passed_code_path = passed_dir / f"passed_attempt_{attempt_number}_{timestamp}.py"
    passed_report_path = passed_dir / f"passed_attempt_{attempt_number}_{timestamp}.json"

    code_text = source_path.read_text(encoding="utf-8")
    passed_code_path.write_text(code_text, encoding="utf-8")
    passed_report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return passed_code_path, passed_report_path


def load_evaluator_module():
    eval_file = EVAL_DIR / "main.py"
    spec = importlib.util.spec_from_file_location("evaluate_generated_code", eval_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load evaluator module from {eval_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Python code and evaluate it with Eval/evaluate_generated_code.py"
    )
    parser.add_argument(
        "--provider",
        choices=["bedrock", "openrouter"],
        default="bedrock",
        help="Model provider to use for code generation.",
    )
    parser.add_argument("--prompt", help="Code generation request.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Generated code output path.")
    parser.add_argument(
        "--model-id",
        default=None,
        help="Model ID. Defaults to provider-specific model when omitted.",
    )
    parser.add_argument("--region", default=None, help="AWS region for Bedrock runtime.")
    parser.add_argument("--api-key", default=None, help="OpenRouter API key. If omitted, uses OPENROUTER_API_KEY.")
    parser.add_argument("--api-url", default=None, help="OpenRouter API URL. If omitted, uses openrouter default endpoint.")
    parser.add_argument("--app-name", default=None, help="Optional OpenRouter app name for request attribution.")
    parser.add_argument("--app-url", default=None, help="Optional OpenRouter app URL for request attribution.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show runtime logs in console.")
    parser.add_argument("--log-file", default=str(DEFAULT_LOG_PATH), help="Path to pipeline runtime log file.")
    parser.add_argument(
        "--failed-dir",
        default=str(DEFAULT_FAILED_DIR),
        help="Directory where failed generated code and reports are saved.",
    )
    parser.add_argument(
        "--passed-dir",
        default=str(DEFAULT_PASSED_DIR),
        help="Directory where passed generated code and reports are saved.",
    )
    parser.add_argument("--fail-below", type=int, default=60, help="Pipeline fails if eval score is below this value.")
    parser.add_argument("--max-regen", type=int, default=2, help="Number of auto-regeneration retries after a failed evaluation.")
    return parser.parse_args()


def build_regen_prompt(original_prompt: str, report: dict, attempt_number: int) -> str:
    report_json = json.dumps(report, indent=2)
    return (
        "The previous generated Python code failed evaluation. Regenerate and improve the code.\n\n"
        f"Original user request:\n{original_prompt}\n\n"
        f"Evaluation failure report (attempt {attempt_number}):\n{report_json}\n\n"
        "Requirements:\n"
        "1) Fix all issues mentioned in the report.\n"
        "2) Return complete executable Python code only (no markdown).\n"
        "3) Keep the main functionality required by the original request.\n"
        "4) Use boto3 for AWS interactions and include basic error handling."
    )


def main() -> int:
    evaluator = load_evaluator_module()
    args = parse_args()
    runtime_id = build_runtime_id()
    runtime_log_path = build_runtime_log_path(Path(args.log_file), runtime_id)
    logger = configure_logger(runtime_log_path, verbose=args.verbose)
    model_id = args.model_id or (
        BEDROCK_DEFAULT_MODEL_ID if args.provider == "bedrock" else OPENROUTER_DEFAULT_MODEL_ID
    )
    failed_dir = Path(args.failed_dir)
    passed_dir = Path(args.passed_dir)
    runtime_root_dir = build_runtime_root_dir(failed_dir, passed_dir, runtime_id)
    runtime_failed_dir = build_runtime_failed_dir(runtime_root_dir)
    runtime_failed_dir.mkdir(parents=True, exist_ok=True)
    runtime_passed_dir = build_runtime_passed_dir(runtime_root_dir)
    runtime_passed_dir.mkdir(parents=True, exist_ok=True)

    if not args.verbose:
        print(f"Provider: {args.provider}")
        print(f"Model ID: {model_id}")
        print(f"Log file: {runtime_log_path}")
        print(f"Run folder: {runtime_root_dir}")
        print(f"Failed folder: {runtime_failed_dir}")
        print(f"Passed folder: {runtime_passed_dir}")

    logger.info("Pipeline started provider=%s model_id=%s output=%s", args.provider, model_id, args.output)

    if args.provider == "openrouter" and not (args.api_key or os.getenv("OPENROUTER_API_KEY")):
        logger.error("OpenRouter requires an API key. Set OPENROUTER_API_KEY or pass --api-key.")
        return 1

    base_prompt = args.prompt or input("Describe the Python code you want to generate: ").strip()
    if not base_prompt:
        logger.error("Prompt cannot be empty.")
        return 1

    if args.max_regen < 0:
        logger.error("--max-regen must be >= 0")
        return 1

    current_prompt = base_prompt
    last_report = None
    total_attempts = args.max_regen + 1

    for attempt_idx in range(total_attempts):
        attempt_number = attempt_idx + 1
        logger.info("Generation attempt %s/%s via %s", attempt_number, total_attempts, args.provider)

        try:
            if args.provider == "bedrock":
                generated_path = generate_and_save_bedrock(
                    user_request=current_prompt,
                    output_path=Path(args.output),
                    model_id=model_id,
                    region=args.region,
                )
            else:
                generated_path = generate_and_save_openrouter(
                    user_request=current_prompt,
                    output_path=Path(args.output),
                    model_id=model_id,
                    api_key=args.api_key or os.getenv("OPENROUTER_API_KEY", ""),
                    api_url=args.api_url or OPENROUTER_DEFAULT_API_URL,
                    app_name=args.app_name,
                    app_url=args.app_url,
                )
        except OpenRouterError as exc:
            logger.exception("OpenRouter request failed: %s", exc)
            return 2
        except (ClientError, BotoCoreError) as exc:
            logger.exception("Bedrock request failed: %s", exc)
            return 2
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error: %s", exc)
            return 3

        logger.info("Generated file: %s", generated_path)

        report = evaluator.evaluate_code_file(generated_path)
        last_report = report
        logger.info("Evaluation report: %s", json.dumps(report, ensure_ascii=False))
        if not args.verbose:
            print(json.dumps(report, indent=2))

        passed = report.get("syntax_ok") and report.get("score", 0) >= args.fail_below
        if passed:
            passed_code_path, passed_report_path = save_passed_code_snapshot(
                source_path=generated_path,
                passed_dir=runtime_passed_dir,
                attempt_number=attempt_number,
                report=report,
            )
            logger.info(
                "Evaluation passed with score=%s saved_passed_code=%s saved_report=%s",
                report.get("score", 0),
                passed_code_path,
                passed_report_path,
            )
            return 0

        failed_code_path, failed_report_path = save_failed_code_snapshot(
            source_path=generated_path,
            failed_dir=runtime_failed_dir,
            attempt_number=attempt_number,
            report=report,
        )
        logger.warning(
            "Evaluation failed score=%s syntax_ok=%s saved_failed_code=%s saved_report=%s",
            report.get("score", 0),
            report.get("syntax_ok", False),
            failed_code_path,
            failed_report_path,
        )

        if attempt_idx < args.max_regen:
            logger.info("Evaluation failed. Regenerating with evaluator report as new input...")
            current_prompt = build_regen_prompt(base_prompt, report, attempt_number)

    if last_report is None or not last_report.get("syntax_ok"):
        logger.error("Pipeline failed due to syntax errors or missing evaluation report.")
        return 3
    if last_report.get("score", 0) < args.fail_below:
        logger.error("Pipeline failed because score=%s is below threshold=%s", last_report.get("score", 0), args.fail_below)
        return 4
    logger.info("Pipeline completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
