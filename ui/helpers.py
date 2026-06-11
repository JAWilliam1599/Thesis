"""General helper functions for formatting and utilities."""
from datetime import datetime
from pathlib import Path


def extract_instructions(code_text: str) -> str:
    """Extract INSTRUCTIONS block from code text."""
    lines = code_text.splitlines()
    if not lines or lines[0].strip() != "# INSTRUCTIONS:":
        return ""

    instructions = []
    for line in lines[1:]:
        if line.strip() == "# END INSTRUCTIONS":
            break
        if line.lstrip().startswith("#"):
            content = line.lstrip()[1:]
            if content.startswith(" "):
                content = content[1:]
            instructions.append(content)
        else:
            instructions.append(line)

    return "\n".join(instructions).strip()


def load_instructions(code_path: Path, code_text: str | None = None) -> str:
    """Load instructions from file or extract from code text."""
    instructions_path = code_path.with_suffix(".instructions.txt")
    if instructions_path.exists():
        return instructions_path.read_text(encoding="utf-8")

    if code_text is None:
        code_text = code_path.read_text(encoding="utf-8")
    return extract_instructions(code_text)


def format_run_label(run_dir: Path) -> str:
    """Format a run directory name for display."""
    run_name = run_dir.name
    if not run_name.startswith("run_"):
        return run_name

    timestamp_text = run_name[len("run_"):]
    try:
        parsed = datetime.strptime(timestamp_text, "%Y%m%dT%H%M%S%fZ")
        return f"{run_name} | {parsed.strftime('%Y-%m-%d %H:%M:%S UTC')}"
    except ValueError:
        return run_name


def format_report_value(value):
    """Format a report value for display."""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, (list, tuple, set)):
        return str(len(value))
    if isinstance(value, dict):
        return f"{len(value)} items"
    return str(value)
