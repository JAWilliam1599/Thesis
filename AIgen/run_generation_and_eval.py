import argparse
import importlib.util
import json
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
    model_id = args.model_id or (
        BEDROCK_DEFAULT_MODEL_ID if args.provider == "bedrock" else OPENROUTER_DEFAULT_MODEL_ID
    )

    if args.provider == "openrouter" and not (args.api_key or os.getenv("OPENROUTER_API_KEY")):
        print("OpenRouter requires an API key. Set OPENROUTER_API_KEY or pass --api-key.")
        return 1

    base_prompt = args.prompt or input("Describe the Python code you want to generate: ").strip()
    if not base_prompt:
        print("Prompt cannot be empty.")
        return 1

    if args.max_regen < 0:
        print("--max-regen must be >= 0")
        return 1

    current_prompt = base_prompt
    last_report = None
    total_attempts = args.max_regen + 1

    for attempt_idx in range(total_attempts):
        attempt_number = attempt_idx + 1
        print(f"Generation attempt {attempt_number}/{total_attempts} via {args.provider}")

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
            print(exc)
            return 2
        except (ClientError, BotoCoreError) as exc:
            print(f"Bedrock request failed: {exc}")
            return 2
        except Exception as exc:  # noqa: BLE001
            print(f"Unexpected error: {exc}")
            return 3

        print(f"Generated file: {generated_path}")

        report = evaluator.evaluate_code_file(generated_path)
        last_report = report
        print(json.dumps(report, indent=2))

        passed = report.get("syntax_ok") and report.get("score", 0) >= args.fail_below
        if passed:
            print("Evaluation passed.")
            return 0

        if attempt_idx < args.max_regen:
            print("Evaluation failed. Regenerating with evaluator report as new input...")
            current_prompt = build_regen_prompt(base_prompt, report, attempt_number)

    if last_report is None or not last_report.get("syntax_ok"):
        return 3
    if last_report.get("score", 0) < args.fail_below:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
