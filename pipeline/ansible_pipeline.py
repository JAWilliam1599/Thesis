"""Ansible execution pipeline (on-prem side of the hybrid system).

Mirrors :mod:`pipeline.cdk_pipeline` but drives ``ansible-playbook`` instead of
the CDK CLI.  The three execution stages map onto the same gate workflow:

    syntax-check  -> local validate (Zone 1, analogous to ``cdk synth``)
    check         -> dry-run / plan   (Zone 2, analogous to ``cdk diff``)
    deploy        -> apply            (Zone 2, analogous to ``cdk deploy``)

The security gate itself lives in :class:`IaCSecurityGate.evaluate_ansible`.
Approval / rejection / can-deploy helpers are reused from cdk_pipeline so both
targets share identical decision semantics; the ``ansible_`` run-id prefix makes
the persisted records (approval_ansible_*.json) self-describing.
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ExecComponent.exec_code import exec_code
from Eval.iac_security_gate import IaCSecurityGate, THRESHOLDS, COST_BANDS
from pipeline.git_changes import changed_files

_YAML_EXTS = (".yml", ".yaml")
_DEFAULT_PLAYBOOK_NAMES = ("site.yml", "site.yaml", "playbook.yml", "main.yml")
_DEFAULT_INVENTORY_NAMES = ("inventory.ini", "inventory.yml", "inventory.yaml", "hosts", "hosts.ini")


def make_ansible_run_id() -> str:
    return "ansible_" + datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _resolve_executable(name: str) -> str:
    """Return the absolute path to *name*, preferring the active venv's bin dir."""
    venv_bin = Path(sys.executable).parent
    candidate = venv_bin / name
    if candidate.is_file():
        return str(candidate)
    found = shutil.which(name)
    return found if found else name


def find_playbook(ansible_dir: Path, playbook: str | None = None) -> Path | None:
    """Resolve the playbook to run inside *ansible_dir*.

    Uses *playbook* when given (relative or absolute); otherwise probes the
    conventional names (site.yml, playbook.yml, main.yml).
    """
    ansible_dir = Path(ansible_dir)
    if playbook:
        candidate = Path(playbook)
        if not candidate.is_absolute():
            candidate = ansible_dir / candidate
        return candidate if candidate.is_file() else None
    for name in _DEFAULT_PLAYBOOK_NAMES:
        candidate = ansible_dir / name
        if candidate.is_file():
            return candidate
    return None


def find_inventory(ansible_dir: Path, inventory: str | None = None) -> Path | None:
    """Resolve the inventory file inside *ansible_dir* (None if absent)."""
    ansible_dir = Path(ansible_dir)
    if inventory:
        candidate = Path(inventory)
        if not candidate.is_absolute():
            candidate = ansible_dir / candidate
        return candidate if candidate.exists() else None
    for name in _DEFAULT_INVENTORY_NAMES:
        candidate = ansible_dir / name
        if candidate.exists():
            return candidate
    return None


def build_ansible_command(
    command_name: str,
    playbook: Path,
    inventory: Path | str | None = None,
) -> list[str]:
    base = [_resolve_executable("ansible-playbook")]
    if command_name == "syntax-check":
        cmd = base + ["--syntax-check"]
    elif command_name == "check":
        cmd = base + ["--check", "--diff"]
    elif command_name == "deploy":
        cmd = list(base)
    else:
        raise ValueError(f"Unknown ansible command: {command_name!r}")

    if inventory is not None:
        cmd += ["-i", str(inventory)]
    cmd.append(str(playbook))
    return cmd


def run_ansible_command(
    ansible_dir: Path,
    command_name: str,
    playbook: Path,
    inventory: Path | str | None = None,
    env: dict[str, str] | None = None,
    line_handler=None,
) -> dict[str, Any]:
    """Execute an ansible-playbook stage and return the standard result dict.

    Result contract matches run_cdk_command:
        {command, command_name, return_code, output}
    """
    command = build_ansible_command(command_name, playbook, inventory)
    result = exec_code.run_command(
        command, cwd=str(ansible_dir), env=env, line_handler=line_handler
    )
    return {
        "command": command,
        "command_name": command_name,
        "return_code": int(result.get("return_code", 1)),
        "output": result.get("output", ""),
    }


def run_ansible_gate(
    ansible_dir: Path,
    *,
    base_ref: str | None = None,
    run_id: str | None = None,
    use_ansible_lint: bool = True,
    use_checkov: bool = True,
    use_secret_scan: bool = True,
    aws_config_violations: int | None = None,
    pass_max: int = THRESHOLDS["pass_max"],
    review_max: int = THRESHOLDS["review_max"],
    cost_high_usd: float = COST_BANDS["high_usd"],
    cost_high_points: int = COST_BANDS["high_points"],
    cost_med_usd: float = COST_BANDS["med_usd"],
    cost_med_points: int = COST_BANDS["med_points"],
) -> dict[str, Any]:
    """Run the Ansible security gate over *ansible_dir*.

    *base_ref*:
        When provided, only git-changed YAML files under *ansible_dir* are
        scanned.  When None, every YAML file is scanned.  If git detection is
        not possible the gate falls back to a full scan automatically.
    """
    ansible_dir = Path(ansible_dir)
    if run_id is None:
        run_id = make_ansible_run_id()

    scoped: list[Path] | None = None
    if base_ref is not None:
        scoped = changed_files(ansible_dir, base_ref=base_ref, exts=_YAML_EXTS)
        # None => detection impossible => fall back to full scan (handled by gate).

    gate = IaCSecurityGate()
    return gate.evaluate_ansible(
        ansible_dir,
        changed_files=scoped,
        run_id=run_id,
        use_ansible_lint=use_ansible_lint,
        use_checkov=use_checkov,
        use_secret_scan=use_secret_scan,
        aws_config_violations=aws_config_violations,
        pass_max=pass_max,
        review_max=review_max,
        cost_high_usd=cost_high_usd,
        cost_high_points=cost_high_points,
        cost_med_usd=cost_med_usd,
        cost_med_points=cost_med_points,
    )


def extract_node_name(ansible_dir: Path, playbook: Path | None = None) -> str:
    """Derive a stable name for SSM/observability keys from the playbook/dir."""
    if playbook is not None:
        return playbook.stem
    return Path(ansible_dir).name or "ansible"
