# Eval — Security & Quality Evaluation Module

## Purpose

Evaluate generated Python code for syntax validity, code quality, security risks, and provide structured pass/fail determination with detailed findings.

## Files

| File | Purpose |
|------|---------|
| `main.py` | Coordinator: loads validators and scorers, assembles report |
| `quickVal.py` | Quick validation: syntax, imports, structure heuristics, dangerous patterns |
| `securityAnalysis.py` | Multi-tool security scanning (bandit, semgrep, OWASP findings) |
| `riskScoring.py` | Risk scoring engine with deployment context awareness |
| `evaluate_generated_code.py` | CLI entry point for standalone evaluation |

## Usage

### CLI: Evaluate a File

```bash
python evaluate_generated_code.py --file ../ExecCode/generated_code.py
```

### With Custom Fail Threshold

```bash
python evaluate_generated_code.py --file ../ExecCode/generated_code.py --fail-below 70
```

### With Deployment Context

```bash
python evaluate_generated_code.py --file ../ExecCode/generated_code.py --deployment-context public
```

### Programmatic Usage

```python
from main import evaluate_code_file
from pathlib import Path

report = evaluate_code_file(Path("../ExecCode/generated_code.py"), deployment_context="internal")
print(report["approval"])  # True if passed, False otherwise
print(report["score"])      # Quality score 0-100
print(report["risk_level"]) # Low, Medium, High, Critical
```

## Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--file` | Path to Python file to evaluate | Required |
| `--fail-below` | Exit non-zero if score below this | 60 |
| `--deployment-context` | Risk context: `public`, `internal`, `onprem`, `sandbox` | `internal` |

## Evaluation Report Structure

```json
{
  "syntax_ok": true,
  "line_count": 45,
  "function_count": 3,
  "has_main_guard": true,
  "has_try_except": true,
  "dangerous_patterns": [],
  "quality_score": 85,
  "heuristic_risk_score": 2,
  "risk_score": 15.5,
  "risk_level": "Low",
  "risk_action": "Log for monitoring",
  "risk_summary": { ... },
  "risk_findings": [ ... ],
  "security_issue_count": 0,
  "security_warning_count": 1,
  "security_analysis": { "findings": [ ... ], "warnings": [ ... ], "issues": [ ... ] },
  "approval": true,
  "issues": [ ... ],
  "score": 85,
  "notes": [ ... ]
}
```

## Evaluation Stages

### 1. Quick Validation (quickVal.py)

Checks:
- Python syntax validity
- Import availability
- Code structure (functions, try/except, main guard)
- Dangerous patterns (eval, exec, os.system, subprocess)

### 2. Security Analysis (securityAnalysis.py)

Runs multiple security scanners:
- **bandit** — Python security linting
- **semgrep** — Static code analysis with custom rules
- **OWASP findings** — Known vulnerability patterns

Output: structured findings with severity levels

### 3. Risk Scoring (riskScoring.py)

Combines findings with deployment context:

| Context | Risk Exposure | Examples |
|---------|---------------|----------|
| `public` | Maximum (exposed to internet) | Public APIs, web services |
| `internal` | Medium (internal network only) | Internal tools, dashboards |
| `onprem` | Low-Medium (isolated data center) | On-premises applications |
| `sandbox` | Minimal (isolated test environment) | Development, testing |

Risk factors:
- **Severity:** Finding severity level (critical, high, medium, low)
- **Exploitability:** How easily the issue can be exploited
- **Exposure:** Affected by deployment context
- **Confidence:** Statistical confidence in the finding

### 4. Approval Decision

Code is approved if:
- ✅ Syntax is valid
- ✅ Risk level is Low or Medium
- ✅ No blocking security issues
- ✅ Quality score meets threshold

## Conventions

- **Report Keys:** Stable across all report consumers (UI, regeneration loop, logging)
- **Threshold Behavior:** Pass/fail determined by configurable `--fail-below` parameter
- **Findings Normalization:** Security tool findings are normalized before risk scoring
- **Deployment Context:** Influences risk assessment but not approval logic

## Integration Points

### From AIgen

Receives generated Python file from `AIgen/run_generation_and_eval.py`:
- Code text or file path
- Optional deployment context

### To UI/Pipeline

Returns structured report with keys:
- `approval` — Boolean pass/fail
- `score` — Quality score
- `risk_level` — Human-readable risk classification
- `issues` — List of findings for user feedback

### Auto-Regeneration Loop

Evaluation failure report is converted to JSON and included in regeneration prompt so LLM can learn from mistakes.

## Dependencies

- `bandit` — Python security linter
- `semgrep` — Static analysis engine
- `ast` — Python syntax analysis
- See [requirements.txt](../requirements.txt) for full list

## Related Documentation

- [riskScoring.md](riskScoring.md) — Detailed risk scoring methodology
- [EVALUATION_SECURITY_RISK_REPORT.md](EVALUATION_SECURITY_RISK_REPORT.md) — Evaluation report format specification
