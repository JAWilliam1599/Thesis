import argparse
import importlib.util
import json
from pathlib import Path


def _load_quickval_module():
    quickval_file = Path(__file__).resolve().parent / "quickVal.py"
    spec = importlib.util.spec_from_file_location("quickVal", quickval_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load quickVal module from {quickval_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


quickVal = _load_quickval_module()


def evaluate_code_text(code: str, model=None) -> dict:
    validator = quickVal.QuickVal(model=model, code=code)
    quick_report = validator.validate()

    risk_score = quick_report.get("risk_score", 0)
    approval = quick_report.get("approval", False)
    issues = quick_report.get("issues", [])

    # Adapter mapping for AIgen/run_generation_and_eval.py expectations.
    score = max(0, min(100, 100 - (risk_score * 20)))
    return {
        "syntax_ok": not any(str(issue).lower().startswith("syntax error:") for issue in issues),
        "line_count": len(code.splitlines()),
        "risk_score": risk_score,
        "approval": approval,
        "issues": issues,
        "score": score,
        "notes": issues,
    }


def evaluate_code_file(path: Path, model=None) -> dict:
    code = path.read_text(encoding="utf-8")
    report = evaluate_code_text(code=code, model=model)
    report["file"] = str(path)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Quick validation wrapper for generated Python code.")
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