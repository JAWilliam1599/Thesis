# ExecComponent — Execution Utilities

## Purpose

Utilities for executing generated Python code with subprocess isolation and output capture, used by pipeline orchestration and UI.

## Files

| File | Purpose |
|------|---------|
| `exec_code.py` | Code execution wrapper with subprocess management |

## Classes & Methods

### exec_code

Main execution helper class.

#### Static Method: `run_file(file_path, cwd=None, line_handler=None)`

Execute a Python file and capture output.

**Parameters:**
- `file_path` (str) — Path to Python file to execute
- `cwd` (str, optional) — Working directory for execution
- `line_handler` (callable, optional) — Function called on each output line: `line_handler(line, output_lines_list)`

**Returns:**
```python
{
    "return_code": int,      # 0 for success, non-zero for failure
    "output": str            # Combined stdout + stderr as single string
}
```

**Example:**

```python
from ExecComponent.exec_code import exec_code

result = exec_code.run_file("ExecCode/generated_code.py")
print(f"Exit code: {result['return_code']}")
print(f"Output:\n{result['output']}")
```

With line handler (for streaming):

```python
def on_line(line, output_lines):
    print(f"[Stream] {line.strip()}")

result = exec_code.run_file(
    "ExecCode/generated_code.py",
    line_handler=on_line
)
```

## Execution Contract

### Input

- Valid Python file path
- Optional working directory
- Optional line handler for streaming output

### Output

Deterministic result dictionary with:
- `return_code` — Process exit code (0 = success)
- `output` — Combined stdout/stderr as string
- Line-buffered streaming (1 line at a time) if `line_handler` provided

### Behavior

- Subprocess execution (safe isolation from main process)
- Combined stdout/stderr output
- Line-buffered for streaming UI updates
- Preserves exit code from executed script

## Safety Considerations

- **Subprocess Isolation:** Code runs in separate process, preventing main process corruption
- **No Direct eval():** Generated code executed via subprocess, not direct Python eval
- **Output Capture:** All stdout/stderr captured and returned to caller
- **Encoding:** Uses UTF-8 encoding for text processing

## Integration Points

### From UI/Pipeline

Called by:
- `ui_app.py` — Streamlit UI for code execution display
- `AIgen/run_generation_and_eval.py` — Execute generated code as part of pipeline
- Testing scripts

### Dependencies

No external dependencies beyond Python stdlib:
- `subprocess` — Process execution
- `os` — Environment and file operations
- `sys` — System interaction

## Related Documentation

- [AIgen/README.md](../AIgen/README.md) — Code generation
- [Root README.md](../README.md) — Pipeline overview
