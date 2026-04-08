import argparse
import json
import os
import re
from pathlib import Path
from urllib import error, request

DEFAULT_MODEL_ID = os.getenv("OPENROUTER_MODEL_ID", "qwen/qwen3-coder-30b-a3b-instruct")
DEFAULT_API_URL = os.getenv("OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions")
ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = ROOT_DIR / "ExecCode" / "generated_code.py"

SYSTEM_INSTRUCTION = (
    "You are a code generator. Return only executable Python code and no markdown. "
    "The code should solve the user request and should primarily use boto3 for AWS SDK interactions "
    "when AWS operations are requested. Include minimal but useful error handling."
)


class OpenRouterError(Exception):
    pass


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
    fenced = re.findall(r"```(?:python)?\n([\s\S]*?)```", raw_text, flags=re.IGNORECASE)
    if fenced:
        return fenced[0].strip() + "\n"
    return raw_text.strip() + "\n"


def _normalize_content(content: object) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)

    return ""


def call_openrouter(
    user_request: str,
    model_id: str,
    api_key: str,
    api_url: str = DEFAULT_API_URL,
    max_tokens: int = 1400,
    temperature: float = 0.2,
    app_name: str | None = None,
    app_url: str | None = None,
) -> str:
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": build_user_prompt(user_request)},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    body = json.dumps(payload).encode("utf-8")
    req = request.Request(api_url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")

    if app_name:
        req.add_header("X-Title", app_name)
    if app_url:
        req.add_header("HTTP-Referer", app_url)

    try:
        with request.urlopen(req, timeout=60) as resp:
            response_data = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise OpenRouterError(format_openrouter_http_error(exc.code, details)) from exc
    except error.URLError as exc:
        raise OpenRouterError(f"OpenRouter request failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise OpenRouterError("OpenRouter request timed out.") from exc

    choices = response_data.get("choices", [])
    if not choices:
        raise OpenRouterError("OpenRouter response did not include any choices.")

    message = choices[0].get("message", {})
    content = _normalize_content(message.get("content", ""))
    if not content.strip():
        raise OpenRouterError("OpenRouter response did not include message content.")

    return extract_code(content)


def is_quota_throttling_message(text: str) -> bool:
    msg = text.lower()
    return "quota" in msg or "rate limit" in msg or "too many" in msg or "daily" in msg


def format_openrouter_http_error(status: int, details: str) -> str:
    if is_quota_throttling_message(details):
        return (
            "OpenRouter quota or rate limit reached: this request was throttled. "
            "Check your OpenRouter account limits, model pricing, and try again later."
        )

    if details:
        return f"OpenRouter request failed with HTTP {status}: {details}"
    return f"OpenRouter request failed with HTTP {status}."


def save_code(code: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(code, encoding="utf-8")
    return output_path


def generate_and_save(
    user_request: str,
    output_path: Path,
    model_id: str,
    api_key: str,
    api_url: str,
    app_name: str | None,
    app_url: str | None,
) -> Path:
    code = call_openrouter(
        user_request=user_request,
        model_id=model_id,
        api_key=api_key,
        api_url=api_url,
        app_name=app_name,
        app_url=app_url,
    )
    return save_code(code=code, output_path=output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Python code via OpenRouter and save it to a file.")
    parser.add_argument("--prompt", help="Natural language request for code generation.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output path for generated Python code.")
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID, help="OpenRouter model ID.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="OpenRouter chat completions endpoint.")
    parser.add_argument("--api-key", default=os.getenv("OPENROUTER_API_KEY"), help="OpenRouter API key.")
    parser.add_argument(
        "--app-name",
        default=os.getenv("OPENROUTER_APP_NAME", "thesis-codegen"),
        help="Optional app name for OpenRouter request attribution.",
    )
    parser.add_argument(
        "--app-url",
        default=os.getenv("OPENROUTER_APP_URL"),
        help="Optional app URL for OpenRouter request attribution.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(f"Using OpenRouter model: {args.model_id}")

    if not args.api_key:
        print("Missing API key. Set OPENROUTER_API_KEY or pass --api-key.")
        return 1

    prompt = args.prompt or input("Describe the Python code you want to generate: ").strip()
    if not prompt:
        print("Prompt cannot be empty.")
        return 1

    try:
        saved_path = generate_and_save(
            user_request=prompt,
            output_path=Path(args.output),
            model_id=args.model_id,
            api_key=args.api_key,
            api_url=args.api_url,
            app_name=args.app_name,
            app_url=args.app_url,
        )
    except OpenRouterError as exc:
        print(exc)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"Unexpected error: {exc}")
        return 3

    print(f"Generated code saved to: {saved_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
