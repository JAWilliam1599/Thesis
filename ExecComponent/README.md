# ExecComponent - Runtime Execution Utilities

## Purpose

`ExecComponent/exec_code.py` provides subprocess-based execution helpers used by UI and pipeline modules for:
- running generated Python code
- running CDK shell commands (`cdk synth`, `cdk diff`, `cdk deploy`)
- streaming command output to the UI

## Main APIs

### `exec_code.start_command(command, cwd=None, env=None)`

Starts a command asynchronously and returns a `subprocess.Popen` object.

### `exec_code.run_command(command, cwd=None, env=None, line_handler=None)`

Runs a command to completion and returns:

```python
{
    "return_code": int,
    "output": str
}
```

### `exec_code.run_file(file_path, cwd=None, line_handler=None)`

Runs a Python file with `sys.executable -u` and captures merged stdout/stderr.

## Example

```python
from ExecComponent.exec_code import exec_code

result = exec_code.run_command(["cdk", "synth"], cwd="GeneratedCDK")
print(result["return_code"])
print(result["output"])
```

## Where It Is Used

- `pipeline/cdk_pipeline.py` for CDK CLI execution
- `ui/cdk_control.py` for non-blocking CDK command streaming in Streamlit
- pipeline/runtime code paths that execute generated files

## Behavioral Contract

- stdout and stderr are merged to preserve event order
- output is line-buffered for incremental UI rendering
- exit code is preserved for gate and deploy decisions

## SysSecOps Relevance

This module is the execution backbone between Zone 1 outputs and Zone 2 decisions, especially for CDK command orchestration around the IaC security gate.
