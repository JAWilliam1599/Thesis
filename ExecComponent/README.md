# ExecComponent — Runtime Execution Utilities

## Purpose

`ExecComponent/exec_code.py` provides the subprocess-based execution backbone used by the
pipeline to:
- run AWS CDK shell commands (`cdk synth`, `cdk diff`, `cdk deploy`, `cdk bootstrap`)
- run generated Python files
- stream merged stdout/stderr output line-by-line for live UI rendering

It is the execution layer between **Zone 1** outputs and **Zone 2** decisions: the
`return_code` it returns drives gate and deploy decisions and Phase 4 observability calls.

## Files

| File | Role |
|---|---|
| `exec_code.py` | `exec_code` class: subprocess helpers + (legacy) project scaffolding |

## The `exec_code` class

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

- `pipeline/cdk_pipeline.py` — all CDK CLI execution (`run_cdk_command`, `run_bootstrap`)
- `AIgen/run_cdk_regen.py` — indirectly via the pipeline helpers during the regen loop
- runtime code paths that execute generated files

## Behavioral Contract

- stdout and stderr are merged to preserve event order
- output is line-buffered for incremental UI rendering
- exit code is preserved for gate and deploy decisions

## SysSecOps Relevance

This module is the execution backbone between Zone 1 outputs and Zone 2 decisions, especially for CDK command orchestration around the IaC security gate.

In Phase 4, CDK commands are still executed through this module, but credential resolution is handled upstream by `pipeline/aws_credentials.py` which sets environment variables before subprocess invocation. The `run_command` return dict (`return_code` + `output`) feeds directly into gate decisions and Phase 4 observability calls.
