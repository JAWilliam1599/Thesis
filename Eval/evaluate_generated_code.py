import argparse
import ast
import json
from pathlib import Path


DANGEROUS_PATTERNS = [
    "os.system",
    "subprocess.Popen",
    "subprocess.call",
    "eval(",
    "exec(",
]


def evaluate_code_text(code: str) -> dict:
    report = {
        "syntax_ok": False,
        "line_count": len(code.splitlines()),
        "function_count": 0,
        "imports_boto3": "import boto3" in code or "from boto3" in code,
        "has_try_except": "try:" in code and "except" in code,
        "has_main_guard": "if __name__ == \"__main__\":" in code,
        "dangerous_patterns": [p for p in DANGEROUS_PATTERNS if p in code],
        "score": 0,
        "notes": [],
    }

    try:
        tree = ast.parse(code)
        report["syntax_ok"] = True
        report["function_count"] = sum(isinstance(node, ast.FunctionDef) for node in ast.walk(tree))
    except SyntaxError as exc:
        report["notes"].append(f"Syntax error: {exc}")
        return report

    score = 0
    score += 40

    if report["imports_boto3"]:
        score += 20
    else:
        report["notes"].append("No boto3 import detected.")

    if report["has_try_except"]:
        score += 15
    else:
        report["notes"].append("No try/except block detected.")

    if report["has_main_guard"]:
        score += 10
    else:
        report["notes"].append("No main guard detected.")

    if report["function_count"] > 0:
        score += 10
    else:
        report["notes"].append("No function definitions detected.")

    if report["dangerous_patterns"]:
        score -= 15
        report["notes"].append("Potentially dangerous execution patterns detected.")
    else:
        score += 5

    report["score"] = max(0, min(100, score))
    return report


def evaluate_code_file(path: Path) -> dict:
    code = path.read_text(encoding="utf-8")
    report = evaluate_code_text(code)
    report["file"] = str(path)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate generated Python code quality and safety heuristics.")
    parser.add_argument("--file", required=True, help="Path to Python file to evaluate.")
    parser.add_argument("--fail-below", type=int, default=60, help="Exit non-zero if score is below this threshold.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = Path(args.file)
    if not target.exists():
        print(json.dumps({"error": f"File not found: {target}"}, indent=2))
        return 2

    report = evaluate_code_file(target)
    print(json.dumps(report, indent=2))

    if not report.get("syntax_ok"):
        return 3
    if report.get("score", 0) < args.fail_below:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
