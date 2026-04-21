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


def _load_security_module():
    security_file = Path(__file__).resolve().parent / "securityAnalysis.py"
    spec = importlib.util.spec_from_file_location("securityAnalysis", security_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load securityAnalysis module from {security_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


securityAnalysis = _load_security_module()


def evaluate_code_text(code: str, model=None, source_path: Path | None = None) -> dict:
    validator = quickVal.QuickVal(model=model, code=code)
    quick_report = validator.validate()
    security_validator = securityAnalysis.Security(code=code)
    security_report = security_validator.analyze(file_path=str(source_path) if source_path is not None else None)
    if security_report is None:
        security_report = {
            "issues": [],
            "warnings": ["Security tool scan skipped because no source file path was provided."],
        }

    risk_score = quick_report.get("risk_score", 0)
    quick_approval = quick_report.get("approval", False)
    quick_issues = list(quick_report.get("issues", []))

    security_issues = [f"Security issue: {item}" for item in security_report.get("issues", [])]
    security_warnings = [f"Security warning: {item}" for item in security_report.get("warnings", [])]
    security_issue_count = len(security_issues)
    security_warning_count = len(security_warnings)
    security_penalty = min(40, (security_issue_count * 10) + (security_warning_count * 3))

    issues = quick_issues + security_issues + security_warnings
    approval = quick_approval and security_issue_count == 0

    # Adapter mapping for AIgen/run_generation_and_eval.py expectations.
    score = max(0, min(100, 100 - (risk_score * 20) - security_penalty))
    return {
        "syntax_ok": not any(str(issue).lower().startswith("syntax error:") for issue in quick_issues),
        "line_count": len(code.splitlines()),
        "risk_score": risk_score,
        "security_issue_count": security_issue_count,
        "security_warning_count": security_warning_count,
        "security_analysis": security_report,
        "approval": approval,
        "issues": issues,
        "score": score,
        "notes": issues,
    }


def evaluate_code_file(path: Path, model=None) -> dict:
    code = path.read_text(encoding="utf-8")
    report = evaluate_code_text(code=code, model=model, source_path=path)
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