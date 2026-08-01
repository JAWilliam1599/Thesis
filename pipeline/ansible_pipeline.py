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

import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from execution.exec_code import exec_code
from security_gate.iac_security_gate import IaCSecurityGate, THRESHOLDS, COST_BANDS
from pipeline.git_changes import changed_files

_YAML_EXTS = (".yml", ".yaml")
_DEFAULT_PLAYBOOK_NAMES = ("site.yml", "site.yaml", "playbook.yml", "main.yml")
_DEFAULT_INVENTORY_NAMES = ("inventory.ini", "inventory.yml", "inventory.yaml", "hosts", "hosts.ini")
_DEFAULT_VERIFY_NAMES = ("verify.yml", "verify.yaml", "assert.yml")


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
    use_ansible_rules: bool = True,
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
        use_ansible_rules=use_ansible_rules,
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


# --------------------------------------------------------------------------- #
# Target-state evidence (RQ2 checkpoints)
# --------------------------------------------------------------------------- #
_RECAP_LINE = re.compile(
    r"^(?P<host>\S+)\s*:\s*ok=(?P<ok>\d+)\s+changed=(?P<changed>\d+)\s+"
    r"unreachable=(?P<unreachable>\d+)\s+failed=(?P<failed>\d+)",
    re.MULTILINE,
)


def find_verify_playbook(ansible_dir: Path, verify: str | None = None) -> Path | None:
    """Resolve the post-deployment assertion playbook (None if absent)."""
    ansible_dir = Path(ansible_dir)
    if verify:
        candidate = Path(verify)
        if not candidate.is_absolute():
            candidate = ansible_dir / candidate
        return candidate if candidate.is_file() else None
    for name in _DEFAULT_VERIFY_NAMES:
        candidate = ansible_dir / name
        if candidate.is_file():
            return candidate
    return None


def parse_play_recap(output: str) -> dict[str, Any]:
    """Parse the PLAY RECAP block into per-host and aggregate task counters.

    Returns ``{"hosts": {...}, "totals": {...}, "parsed": bool}``.  ``parsed``
    is False when no recap was emitted (e.g. the run aborted before any play),
    which must not be confused with a recap reporting zero changes.
    """
    hosts: dict[str, dict[str, int]] = {}
    for match in _RECAP_LINE.finditer(output or ""):
        hosts[match.group("host")] = {
            "ok": int(match.group("ok")),
            "changed": int(match.group("changed")),
            "unreachable": int(match.group("unreachable")),
            "failed": int(match.group("failed")),
        }
    totals = {key: sum(h[key] for h in hosts.values()) for key in ("ok", "changed", "unreachable", "failed")}
    return {"hosts": hosts, "totals": totals, "parsed": bool(hosts)}


def classify_ansible_failure(result: dict[str, Any]) -> str:
    """Classify a non-zero ansible-playbook result for failure accounting.

    One of: ``ok``, ``connectivity``, ``authentication``, ``task_error``,
    ``validation``, ``unknown``.  Distinguishing these is what turns an
    unattributed deploy failure into usable evidence.
    """
    if int(result.get("return_code", 1)) == 0:
        return "ok"
    output = result.get("output") or ""
    lowered = output.lower()
    recap = parse_play_recap(output)

    if recap["totals"]["unreachable"] or "unreachable!" in lowered:
        if any(token in lowered for token in (
            "permission denied", "authentication failure", "invalid/incorrect password",
            "host key verification failed",
        )):
            return "authentication"
        return "connectivity"
    if any(token in lowered for token in (
        "missing sudo password", "incorrect sudo password", "permission denied",
        "authentication failure",
    )):
        return "authentication"
    if "syntax error" in lowered or "erroneous" in lowered:
        return "validation"
    if recap["totals"]["failed"] or "failed!" in lowered:
        return "task_error"
    return "unknown"


def ping_target(
    ansible_dir: Path,
    inventory: Path | str | None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Verify network reachability and authenticated access via ``ansible -m ping``.

    Returns the standard result dict plus a ``classification`` field so a
    pre-deployment failure is attributable to connectivity vs authentication.
    """
    if inventory is None:
        return {"command": [], "command_name": "ping", "return_code": 1,
                "output": "no inventory or target host provided", "classification": "connectivity"}
    command = [_resolve_executable("ansible"), "all", "-i", str(inventory), "-m", "ping"]
    result = exec_code.run_command(command, cwd=str(ansible_dir), env=env)
    payload = {
        "command": command,
        "command_name": "ping",
        "return_code": int(result.get("return_code", 1)),
        "output": result.get("output", ""),
    }
    payload["classification"] = classify_ansible_failure(payload)
    return payload


def run_verification(
    ansible_dir: Path,
    verify_playbook: Path,
    inventory: Path | str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run the post-deployment assertion playbook and summarise its recap."""
    result = run_ansible_command(ansible_dir, "deploy", verify_playbook, inventory, env=env)
    recap = parse_play_recap(result["output"])
    return {
        "playbook": str(verify_playbook),
        "return_code": result["return_code"],
        "verified": result["return_code"] == 0 and recap["parsed"] and recap["totals"]["failed"] == 0,
        "recap": recap,
        "classification": classify_ansible_failure(result),
        "output_tail": result["output"][-2000:] if result["return_code"] != 0 else "",
    }


def run_idempotence_check(
    ansible_dir: Path,
    playbook: Path,
    inventory: Path | str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Re-apply *playbook* and report whether the second run changed anything.

    A converged, idempotent play reports ``changed=0`` on re-application.
    """
    result = run_ansible_command(ansible_dir, "deploy", playbook, inventory, env=env)
    recap = parse_play_recap(result["output"])
    return {
        "return_code": result["return_code"],
        "recap": recap,
        "idempotent": (
            result["return_code"] == 0
            and recap["parsed"]
            and recap["totals"]["changed"] == 0
        ),
        "classification": classify_ansible_failure(result),
        "output_tail": result["output"][-2000:] if result["return_code"] != 0 else "",
    }

