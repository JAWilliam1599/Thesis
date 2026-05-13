import argparse
import ast
import importlib.util
import json
import sys
from pathlib import Path


DANGEROUS_PATTERNS = [
    "os.system",
    "subprocess.Popen",
    "subprocess.call",
    "eval(",
    "exec(",
]


def _load_quickval_module():
    quickval_file = Path(__file__).resolve().parent / "quickVal.py"
    spec = importlib.util.spec_from_file_location("quickVal", quickval_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load quickVal module from {quickval_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_security_module():
    security_file = Path(__file__).resolve().parent / "securityAnalysis.py"
    spec = importlib.util.spec_from_file_location("securityAnalysis", security_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load securityAnalysis module from {security_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_risk_scoring_module():
    risk_file = Path(__file__).resolve().parent / "riskScoring.py"
    spec = importlib.util.spec_from_file_location("riskScoring", risk_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load riskScoring module from {risk_file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


quickVal = _load_quickval_module()
securityAnalysis = _load_security_module()
riskScoring = _load_risk_scoring_module()


def _quickval_penalty(findings: list[dict]) -> int:
    severity_weights = {
        "critical": 5,
        "high": 3,
        "medium": 2,
        "low": 1,
        "warning": 1,
        "info": 1,
    }
    return sum(severity_weights.get(str(finding.get("severity", "low")).lower(), 1) for finding in findings)


def evaluate_code_text(code: str, model=None, source_path: Path | None = None, deployment_context: str = "internal") -> dict:
    validator = quickVal.QuickVal(model=model, code=code)
    quick_report = validator.validate()
    security_validator = securityAnalysis.Security(code=code)
    security_report = security_validator.analyze(file_path=str(source_path) if source_path is not None else None)
    if security_report is None:
        security_report = {
            "issues": [],
            "warnings": ["Security tool scan skipped because no source file path was provided."],
            "findings": [],
        }

    risk_scorer = riskScoring.RiskScorer(deployment_context=deployment_context)
    quick_findings = list(quick_report.get("findings", []))
    combined_findings = list(security_report.get("findings", [])) + quick_findings
    risk_report = risk_scorer.score(code=code, findings=combined_findings)

    report = {
        "syntax_ok": False,
        "line_count": len(code.splitlines()),
        "quality_score": 0,
        "heuristic_risk_score": _quickval_penalty(quick_findings),
        "risk_score": risk_report.get("risk_score", 0),
        "risk_level": risk_report.get("risk_level", "Low"),
        "risk_action": risk_report.get("recommended_action", "Log for monitoring"),
        "risk_summary": risk_report.get("risk_summary", {}),
        "risk_findings": risk_report.get("risk_findings", []),
        "security_analysis": security_report,
        "function_count": 0,
        "has_try_except": "try:" in code and "except" in code,
        "has_main_guard": "if __name__ == \"__main__\":" in code,
        "dangerous_patterns": [p for p in DANGEROUS_PATTERNS if p in code],
        "score": 0,
        "notes": [],
        "issues": quick_report.get("issues", []) + [f"Security issue: {item}" for item in security_report.get("issues", [])] + [f"Security warning: {item}" for item in security_report.get("warnings", [])],
    }

    try:
        tree = ast.parse(code)
        report["syntax_ok"] = True
        report["function_count"] = sum(isinstance(node, ast.FunctionDef) for node in ast.walk(tree))
    except SyntaxError as exc:
        report["notes"].append(f"Syntax error: {exc}")
        report["issues"].append(f"Syntax error: {exc}")
        report["approval"] = False
        return report

    score = 0
    score += 40

    if report["has_try_except"]:
        score += 15
    else:
        report["notes"].append("No try/except block detected.")

    if report["has_main_guard"]:
        score += 15
    else:
        report["notes"].append("No main guard detected.")

    if report["function_count"] > 0:
        score += 15
    else:
        report["notes"].append("No function definitions detected.")

    if report["dangerous_patterns"]:
        score -= 15
        report["notes"].append("Potentially dangerous execution patterns detected.")
    else:
        score += 15

    report["score"] = max(0, min(100, score))
    report["quality_score"] = report["score"]
    report["approval"] = quick_report.get("approval", False) and report["risk_level"] in {"Low", "Medium"}
    return report


def evaluate_code_file(path: Path, deployment_context: str = "internal") -> dict:
    code = path.read_text(encoding="utf-8")
    report = evaluate_code_text(code, source_path=path, deployment_context=deployment_context)
    report["file"] = str(path)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate generated Python code quality and safety heuristics.")
    parser.add_argument("--file", required=True, help="Path to Python file to evaluate.")
    parser.add_argument("--fail-below", type=int, default=60, help="Exit non-zero if score is below this threshold.")
    parser.add_argument(
        "--deployment-context",
        choices=["public", "internal", "onprem", "sandbox"],
        default="internal",
        help="Deployment context used to estimate exposure for risk scoring.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = Path(args.file)
    if not target.exists():
        print(json.dumps({"error": f"File not found: {target}"}, indent=2))
        return 2

    report = evaluate_code_file(target, deployment_context=args.deployment_context)
    print(json.dumps(report, indent=2))

    if not report.get("syntax_ok"):
        return 3
    if not report.get("approval", False):
        return 4
    if report.get("score", 0) < args.fail_below:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
