Evaluator script:

- evaluate_generated_code.py

What it checks:

- Python syntax validity.
- Presence of boto3 import.
- Basic structure heuristics (functions, try/except, main guard).
- Simple dangerous pattern detection (eval/exec/os.system/subprocess).

Run:

python evaluate_generated_code.py --file ../ExecCode/generated_code.py --fail-below 60
