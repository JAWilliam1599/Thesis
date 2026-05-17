Evaluator script:

- evaluate_generated_code.py

What it checks:

- Python syntax validity.
- Presence of boto3 import.
- Basic structure heuristics (functions, try/except, main guard).
- Simple dangerous pattern detection (eval/exec/os.system/subprocess).
- Multi-factor risk scoring with severity, exploitability, exposure, and confidence.

Run:

python evaluate_generated_code.py --file ../ExecCode/generated_code.py --fail-below 60

Optional deployment context:

python evaluate_generated_code.py --file ../ExecCode/generated_code.py --deployment-context internal

Supported deployment contexts:

- public
- internal
- onprem
- sandbox
