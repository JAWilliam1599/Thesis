import argparse
import os
import re
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

DEFAULT_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "qwen.qwen3-coder-30b-a3b-v1:0")
ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = ROOT_DIR / "ExecCode" / "generated_code.py"

SYSTEM_INSTRUCTION = (
    "You are a code generator. Return only executable Python code and no markdown. "
    "The code should solve the user request and should primarily use boto3 for AWS SDK interactions "
    "when AWS operations are requested. Include minimal but useful error handling."
)


def build_user_prompt(user_request: str) -> str:
    return (
        "Generate Python code for this request:\n"
        f"{user_request}\n\n"
        "Requirements:\n"
        "1) Output only Python code.\n"
        "2) Use boto3 when interacting with AWS.\n"
        "3) Include a small main() entry point if appropriate.\n"
        "4) Keep the code clear and practical."
    )


def extract_code(raw_text: str) -> str:
    fenced = re.findall(r"```(?:python)?\\n([\\s\\S]*?)```", raw_text, flags=re.IGNORECASE)
    if fenced:
        return fenced[0].strip() + "\n"
    return raw_text.strip() + "\n"


def call_bedrock(user_request: str, model_id: str, region: str | None = None, max_tokens: int = 1400) -> str:
    client = boto3.client("bedrock-runtime", region_name=region)
    response = client.converse(
        modelId=model_id,
        system=[{"text": SYSTEM_INSTRUCTION}],
        messages=[
            {
                "role": "user",
                "content": [{"text": build_user_prompt(user_request)}],
            }
        ],
        inferenceConfig={
            "maxTokens": max_tokens,
            "temperature": 0.2,
        },
    )

    content_blocks = response.get("output", {}).get("message", {}).get("content", [])
    joined_text = "\n".join(block.get("text", "") for block in content_blocks if "text" in block)
    return extract_code(joined_text)


def validate_model_id(model_id: str, region: str | None = None) -> None:
    client = boto3.client("bedrock", region_name=region)
    try:
        client.get_foundation_model(modelIdentifier=model_id)
    except ClientError as exc:
        error = exc.response.get("Error", {})
        code = error.get("Code", "UnknownError")
        message = error.get("Message", "Unable to validate the configured model ID.")
        raise ValueError(f"Model validation failed for {model_id}: {code}: {message}") from exc


def is_quota_throttling_error(exc: ClientError) -> bool:
    error = exc.response.get("Error", {})
    message = f"{error.get('Message', '')} {error.get('Code', '')}".lower()
    return "too many tokens per day" in message or "quota" in message or "daily" in message


def format_bedrock_error(exc: ClientError) -> str:
    if is_quota_throttling_error(exc):
        return (
            "Bedrock quota limit reached: this request was throttled because your account/model "
            "has exceeded its daily token allowance. Check Bedrock service quotas in the AWS console, "
            "or try again after the quota window resets."
        )

    error = exc.response.get("Error", {})
    code = error.get("Code", "UnknownError")
    message = error.get("Message", str(exc))
    return f"Bedrock request failed: {code}: {message}"


def save_code(code: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(code, encoding="utf-8")
    return output_path


def generate_and_save(user_request: str, output_path: Path, model_id: str, region: str | None) -> Path:
    code = call_bedrock(user_request=user_request, model_id=model_id, region=region)
    return save_code(code=code, output_path=output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Python code from AWS Bedrock and save it to a file.")
    parser.add_argument("--prompt", help="Natural language request for code generation.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output path for generated Python code.")
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID, help="Bedrock model ID.")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "ap-southeast-2"), help="AWS region for Bedrock runtime.")
    parser.add_argument(
        "--validate-model",
        action="store_true",
        help="Validate the configured Bedrock model ID before generating code.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(f"Using Bedrock model: {args.model_id} in region: {args.region}")
    prompt = args.prompt or input("Describe the Python code you want to generate: ").strip()
    if not prompt:
        print("Prompt cannot be empty.")
        return 1

    try:
        if args.validate_model:
            validate_model_id(model_id=args.model_id, region=args.region)

        saved_path = generate_and_save(
            user_request=prompt,
            output_path=Path(args.output),
            model_id=args.model_id,
            region=args.region,
        )
    except ClientError as exc:
        print(format_bedrock_error(exc))
        return 2
    except BotoCoreError as exc:
        print(f"Bedrock request failed: {exc}")
        return 2
    except ValueError as exc:
        print(exc)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"Unexpected error: {exc}")
        return 3

    print(f"Generated code saved to: {saved_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
