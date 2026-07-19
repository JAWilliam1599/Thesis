"""Hybrid pipeline entrypoint: AWS CDK + on-prem Ansible, no code generation.

Runs the existing IaC security gate / risk-scoring / deploy / observability
workflow over BOTH sides of a hybrid project that the user already wrote:

    <hybrid-root>/<cdk-name>      -> CDK app   (synth -> gate -> diff -> deploy)
    <hybrid-root>/<ansible-name>  -> playbooks  (syntax -> gate -> check -> deploy)

There is intentionally NO generation step here — both sides are "bring your own
code".  Each branch is gated independently with the same risk engine and emits
the same Phase 4 observability (SSM / EventBridge / CloudWatch / SNS).  A combined
hybrid report is written to logs/hybrid_<run_id>.json.

Examples:
    python scripts/run_hybrid_pipeline.py \
        --cdk-path examples/hybrid-demo/cdk \
        --ansible-path examples/hybrid-demo/ansible \
        --base-ref HEAD~1

    # On-prem only, deploy to a Tailscale node:
    python scripts/run_hybrid_pipeline.py \
        --ansible-path examples/hybrid-demo/ansible \
        --target-host 100.101.102.103 --deploy

    # Read-only status of all gated targets:
    python scripts/run_hybrid_pipeline.py --query-status
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from env_bootstrap import load_env

load_env()

from pipeline.cdk_pipeline import (
    can_deploy,
    clear_cdk_out,
    extract_stack_name,
    run_bootstrap,
    run_cdk_command,
    run_iac_gate,
    write_approval,
    write_rejection_record,
)
from pipeline.ansible_pipeline import (
    extract_node_name,
    find_inventory,
    find_playbook,
    make_ansible_run_id,
    run_ansible_command,
    run_ansible_gate,
)
from pipeline.aws_credentials import get_session
from pipeline.notifier import get_notifier
from security_gate.iac_security_gate import THRESHOLDS, COST_BANDS
from security_gate.scanners.ml_risk_adapter import ML_MAX_POINTS
from pipeline.ssm_store import list_monitored_stacks, read_gate_result, write_gate_result
from pipeline.eventbridge_trigger import publish_gate_event
from monitoring.cloudwatch_publisher import publish_gate_metrics, put_log_event
from monitoring.stack_monitor import setup_stack_monitoring

logger = logging.getLogger("hybrid_pipeline")


def _log_dir() -> Path:
    """Logs root, overridable per project via SYSSECOPS_LOG_DIR (call time)."""
    override = os.environ.get("SYSSECOPS_LOG_DIR")
    return Path(override) if override else ROOT_DIR / "logs"


def _make_run_id() -> str:
    return "hybrid_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _configure_logger(log_path: Path, verbose: bool) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    if verbose:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)


def _stream_line(line: str, _output_lines: list) -> None:
    print(line, end="", flush=True)


def _emit_observability(gate_report: dict, name: str) -> None:
    """Fire Phase 4 observability after a gate evaluation (best-effort).

    Skips silently when AWS credentials are unavailable (local dev mode).
    *name* is the SSM/metric dimension (stack name for CDK, ``ansible-<node>``
    for the on-prem side) so the two targets never collide.
    """
    if get_session() is None:
        logger.debug("Observability skipped — no AWS credentials available.")
        return
    run_id = gate_report.get("run_id", "")
    score = gate_report.get("score", 0)
    decision = gate_report.get("decision", "reject")
    findings = gate_report.get("findings") or []
    report_path = gate_report.get("report_path") or ""
    try:
        write_gate_result(name, run_id, score, decision, report_path)
        publish_gate_event(run_id, name, decision, score)
        ml_analysis = gate_report.get("ml_analysis") or {}
        ml_score = ml_analysis.get("ml_score") if ml_analysis.get("status") == "ok" else None
        publish_gate_metrics(name, run_id, score, decision, findings, ml_score=ml_score)
        put_log_event(name, run_id, gate_report)
    except Exception as exc:
        logger.warning("observability emit failed for %s — %s", name, exc)


def _notify(event_type: str, gate_report: dict, extra: dict | None = None) -> None:
    notifier = get_notifier()
    if not notifier:
        return
    try:
        notifier.send(event_type, gate_report, extra=extra)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# CDK branch
# --------------------------------------------------------------------------- #
def run_cdk_branch(args: argparse.Namespace, run_id: str, env: dict) -> dict:
    project_dir = Path(args.cdk_path).resolve()
    summary: dict = {"target": "cdk", "project_dir": str(project_dir), "run_id": run_id}

    if not project_dir.exists():
        summary.update(status="error", error=f"CDK path not found: {project_dir}")
        print(json.dumps({"stage": "cdk", **summary}, indent=2))
        return summary

    if args.bootstrap:
        bootstrap = run_bootstrap(project_dir, env=env)
        print(json.dumps({"stage": "cdk.bootstrap", **bootstrap}, indent=2))
        if bootstrap["return_code"] != 0:
            summary.update(status="error", error="bootstrap failed")
            return summary

    clear_cdk_out(project_dir)
    synth = run_cdk_command(project_dir, "synth", env=env)
    print(json.dumps({"stage": "cdk.synth", **synth}, indent=2))
    if synth["return_code"] != 0:
        summary.update(status="error", error="synth failed")
        return summary

    gate_report = run_iac_gate(
        project_dir,
        cost_delta_usd=args.cost_delta_usd,
        aws_config_violations=args.aws_config_violations,
        use_checkov=not args.no_checkov,
        use_cfn_lint=not args.no_cfn_lint,
        use_infracost=not args.no_infracost,
        use_aws_config=not args.no_aws_config,
        use_ml_risk=not args.no_ml_risk,
        run_id=run_id,
        pass_max=args.pass_max,
        review_max=args.review_max,
        cost_high_usd=args.cost_high_usd,
        cost_high_points=args.cost_high_points,
        cost_med_usd=args.cost_med_usd,
        cost_med_points=args.cost_med_points,
        ml_max_points=args.ml_max_points,
    )
    print(json.dumps({"stage": "cdk.gate", "gate": gate_report}, indent=2))
    stack_name = extract_stack_name(gate_report)
    _emit_observability(gate_report, stack_name)
    summary.update(
        decision=gate_report.get("decision"),
        score=gate_report.get("score"),
        report_path=gate_report.get("report_path"),
        stack_name=stack_name,
    )

    diff = run_cdk_command(project_dir, "diff", env=env)
    print(json.dumps({"stage": "cdk.diff", "return_code": diff["return_code"]}, indent=2))

    allowed, reason = can_deploy(gate_report, manual_review_approved=args.manual_approve)
    print(json.dumps({"stage": "cdk.decision", "allowed": allowed, "reason": reason}, indent=2))
    summary.update(allowed=allowed, reason=reason)

    if not allowed:
        decision = str(gate_report.get("decision", "")).lower()
        if decision == "review":
            _notify("review_required", gate_report)
            summary["status"] = "review"
        else:
            write_rejection_record(run_id, gate_report)
            _notify("reject", gate_report)
            summary["status"] = "reject"
        return summary

    if args.manual_approve and str(gate_report.get("decision", "")).lower() == "review":
        write_approval(run_id, gate_report, approver="hybrid-cli")

    if not args.deploy:
        summary["status"] = "gated_ok"
        return summary

    print(json.dumps({"stage": "cdk.deploy", "status": "started"}), flush=True)
    deploy = run_cdk_command(project_dir, "deploy", env=env, line_handler=_stream_line)
    deploy_ok = deploy["return_code"] == 0
    _notify("deploy_success" if deploy_ok else "deploy_failure", gate_report,
            extra={"deploy_return_code": deploy["return_code"]})
    if deploy_ok:
        setup_stack_monitoring(stack_name, project_dir / "cdk.out")
    summary["status"] = "deployed" if deploy_ok else "deploy_failed"
    return summary


# --------------------------------------------------------------------------- #
# Ansible branch
# --------------------------------------------------------------------------- #
def _resolve_inventory(args: argparse.Namespace, ansible_dir: Path):
    """Return inventory as a file Path, a Tailscale host string, or None."""
    if args.target_host:
        host = args.target_host.strip()
        return host if host.endswith(",") else f"{host},"
    return find_inventory(ansible_dir, args.inventory)


def run_ansible_branch(args: argparse.Namespace, run_id: str, env: dict) -> dict:
    ansible_dir = Path(args.ansible_path).resolve()
    summary: dict = {"target": "ansible", "project_dir": str(ansible_dir), "run_id": run_id}

    if not ansible_dir.exists():
        summary.update(status="error", error=f"Ansible path not found: {ansible_dir}")
        print(json.dumps({"stage": "ansible", **summary}, indent=2))
        return summary

    playbook = find_playbook(ansible_dir, args.playbook)
    if playbook is None:
        summary.update(status="error", error="No playbook found (looked for site.yml/playbook.yml/main.yml).")
        print(json.dumps({"stage": "ansible", **summary}, indent=2))
        return summary

    inventory = _resolve_inventory(args, ansible_dir)
    node_name = "ansible-" + extract_node_name(ansible_dir, playbook)

    # 1. Local validate (Zone 1): syntax-check.
    syntax = run_ansible_command(ansible_dir, "syntax-check", playbook, inventory, env=env)
    print(json.dumps({"stage": "ansible.syntax", "return_code": syntax["return_code"]}, indent=2))
    if syntax["return_code"] != 0:
        print(json.dumps({"stage": "ansible.syntax", "output": syntax["output"][-1200:]}, indent=2))
        summary.update(status="error", error="ansible syntax-check failed")
        return summary

    # 2. Security gate (Zone 2): scan git-changed YAML (or all).
    gate_report = run_ansible_gate(
        ansible_dir,
        base_ref=args.base_ref,
        run_id=run_id,
        use_ansible_lint=not args.no_ansible_lint,
        use_checkov=not args.no_checkov,
        use_secret_scan=not args.no_secret_scan,
        aws_config_violations=args.aws_config_violations,
        pass_max=args.pass_max,
        review_max=args.review_max,
        cost_high_usd=args.cost_high_usd,
        cost_high_points=args.cost_high_points,
        cost_med_usd=args.cost_med_usd,
        cost_med_points=args.cost_med_points,
    )
    print(json.dumps({"stage": "ansible.gate", "gate": gate_report}, indent=2))
    _emit_observability(gate_report, node_name)
    summary.update(
        decision=gate_report.get("decision"),
        score=gate_report.get("score"),
        report_path=gate_report.get("report_path"),
        node_name=node_name,
        playbook=str(playbook),
    )

    allowed, reason = can_deploy(gate_report, manual_review_approved=args.manual_approve)
    print(json.dumps({"stage": "ansible.decision", "allowed": allowed, "reason": reason}, indent=2))
    summary.update(allowed=allowed, reason=reason)

    if not allowed:
        decision = str(gate_report.get("decision", "")).lower()
        if decision == "review":
            _notify("review_required", gate_report)
            summary["status"] = "review"
        else:
            write_rejection_record(run_id, gate_report)
            _notify("reject", gate_report)
            summary["status"] = "reject"
        return summary

    if args.manual_approve and str(gate_report.get("decision", "")).lower() == "review":
        write_approval(run_id, gate_report, approver="hybrid-cli")

    # 3. Dry-run (Zone 2): ansible-playbook --check --diff.
    check = run_ansible_command(ansible_dir, "check", playbook, inventory, env=env)
    print(json.dumps({"stage": "ansible.check", "return_code": check["return_code"]}, indent=2))
    # --check can fail when a task cannot predict changes without connectivity;
    # treat as advisory unless deploying.
    if not args.deploy:
        summary["status"] = "gated_ok"
        return summary

    if inventory is None:
        summary.update(status="error", error="Deploy requested but no inventory/--target-host provided.")
        return summary

    print(json.dumps({"stage": "ansible.deploy", "status": "started"}), flush=True)
    deploy = run_ansible_command(ansible_dir, "deploy", playbook, inventory, env=env, line_handler=_stream_line)
    deploy_ok = deploy["return_code"] == 0
    _notify("deploy_success" if deploy_ok else "deploy_failure", gate_report,
            extra={"deploy_return_code": deploy["return_code"]})
    summary["status"] = "deployed" if deploy_ok else "deploy_failed"
    return summary


# --------------------------------------------------------------------------- #
# Query status
# --------------------------------------------------------------------------- #
def query_status_main() -> int:
    targets = list_monitored_stacks()
    if not targets:
        print("No targets found in SSM under /syssecops/gate/ (SSM may be disabled or no runs recorded yet).")
    else:
        header = f"{'TARGET':<40} {'SCORE':<8} {'DECISION':<10} {'RUN_ID':<40}"
        print(header)
        print("-" * len(header))
        for target in targets:
            result = read_gate_result(target) or {}
            print(f"{target:<40} {result.get('latest_score', '—'):<8} "
                  f"{result.get('latest_decision', '—'):<10} {result.get('latest_run_id', '—'):<40}")
    return 0


def hybrid_status_main() -> int:
    """Print on-prem / hybrid mesh status (SSM nodes, compliance, Tailscale)."""
    from pipeline.hybrid_status import collect_hybrid_status

    status = collect_hybrid_status()

    nodes = status["ssm_nodes"]
    print(f"\n== SSM managed nodes ({nodes['status']}) ==")
    if nodes["items"]:
        for n in nodes["items"]:
            kind = "hybrid" if n["is_hybrid"] else "ec2"
            print(f"  {n['id']:<22} {kind:<7} {n['ping_status']:<12} {n['platform']:<14} {n['ip']}")
    else:
        print("  (none)")

    comp = status["ssm_compliance"]
    print(f"\n== SSM compliance ({comp['status']}) ==")
    if comp["items"]:
        for c in comp["items"]:
            print(f"  {c['resource_id']:<22} {c['compliance_type']:<14} {c['status']:<14} "
                  f"crit={c['critical']} high={c['high']}")
    else:
        print("  (none)")

    dev = status["tailscale_devices"]
    print(f"\n== Tailscale devices ({dev['status']}) ==")
    if dev["items"]:
        for d in dev["items"]:
            state = "online" if d["online"] else "offline"
            addr = d["addresses"][0] if d["addresses"] else ""
            print(f"  {d['hostname']:<24} {state:<8} {d['os']:<10} {addr}")
    else:
        print("  (none — set TAILSCALE_API_KEY / TAILSCALE_TAILNET to enable)")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run the hybrid (CDK + Ansible) IaC risk gate pipeline.")
    p.add_argument("--cdk-path", default=None, help="Path to the CDK app directory (omit to skip the CDK branch).")
    p.add_argument("--ansible-path", default=None, help="Path to the Ansible project directory (omit to skip the Ansible branch).")
    p.add_argument("--base-ref", default=None, help="Git ref to diff against for changed-file scoping (e.g. HEAD~1). Default: scan all files.")
    p.add_argument("--playbook", default=None, help="Playbook filename relative to the Ansible path (default: auto-detect site.yml/playbook.yml/main.yml).")
    p.add_argument("--inventory", default=None, help="Inventory file relative to the Ansible path (default: auto-detect).")
    p.add_argument("--target-host", default=None, help="Tailscale host/IP for the on-prem node; used as an inline inventory when no file is given.")
    p.add_argument("--run-id", default=None, help="Override the hybrid run ID.")
    p.add_argument("--cost-delta-usd", type=float, default=None, help="Override Infracost cost delta (CDK branch).")
    p.add_argument("--aws-config-violations", type=int, default=None, help="Override AWS Config violations count.")
    p.add_argument("--pass-max", type=int, default=THRESHOLDS["pass_max"], help=f"Max score for an auto-PASS decision (default: {THRESHOLDS['pass_max']}).")
    p.add_argument("--review-max", type=int, default=THRESHOLDS["review_max"], help=f"Max score for a REVIEW decision; above this is REJECT (default: {THRESHOLDS['review_max']}).")
    p.add_argument("--cost-high-usd", type=float, default=COST_BANDS["high_usd"], help=f"Cost delta (USD) above which the high cost-band points apply (default: {COST_BANDS['high_usd']}).")
    p.add_argument("--cost-high-points", type=int, default=COST_BANDS["high_points"], help=f"Points added when cost delta exceeds --cost-high-usd (default: {COST_BANDS['high_points']}).")
    p.add_argument("--cost-med-usd", type=float, default=COST_BANDS["med_usd"], help=f"Cost delta (USD) above which the medium cost-band points apply (default: {COST_BANDS['med_usd']}).")
    p.add_argument("--cost-med-points", type=int, default=COST_BANDS["med_points"], help=f"Points added when cost delta exceeds --cost-med-usd (default: {COST_BANDS['med_points']}).")
    p.add_argument("--ml-max-points", type=int, default=ML_MAX_POINTS, help=f"Max points contributed by the ML risk model at P(insecure)=1.0, CDK branch (default: {ML_MAX_POINTS}).")
    p.add_argument("--manual-approve", action="store_true", help="Approve review-band (21-80) decisions for deploy.")
    p.add_argument("--deploy", action="store_true", help="Deploy each branch that the gate allows.")
    p.add_argument("--bootstrap", action="store_true", help="Run cdk bootstrap before synth (CDK branch).")
    p.add_argument("--no-checkov", action="store_true", help="Skip checkov on both branches.")
    p.add_argument("--no-cfn-lint", action="store_true", help="Skip cfn-lint (CDK branch).")
    p.add_argument("--no-infracost", action="store_true", help="Skip infracost (CDK branch).")
    p.add_argument("--no-ml-risk", action="store_true", help="Skip the ML risk score on the CDK Python source (CDK branch).")
    p.add_argument("--no-aws-config", action="store_true", help="Skip AWS Config fetch (CDK branch).")
    p.add_argument("--no-ansible-lint", action="store_true", help="Skip ansible-lint (Ansible branch).")
    p.add_argument("--no-secret-scan", action="store_true", help="Skip secret scan (Ansible branch).")
    p.add_argument("--query-status", action="store_true", help="Print last gate result per target from SSM and exit.")
    p.add_argument("--hybrid-status", action="store_true", help="Print on-prem mesh status (SSM nodes, compliance, Tailscale) and exit.")
    p.add_argument("--log-file", default=None, help="Override log file path.")
    p.add_argument("--verbose", action="store_true", help="Also print logs to stderr.")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.query_status:
        return query_status_main()

    if args.hybrid_status:
        return hybrid_status_main()

    if not args.cdk_path and not args.ansible_path:
        print("ERROR: provide at least one of --cdk-path or --ansible-path (or use --query-status).")
        return 2

    run_id = args.run_id or _make_run_id()
    log_path = Path(args.log_file) if args.log_file else _log_dir() / f"{run_id}.log"
    _configure_logger(log_path, args.verbose)
    logger.info("run_id=%s cdk=%s ansible=%s", run_id, args.cdk_path, args.ansible_path)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    branches: list[dict] = []
    ts = run_id.replace("hybrid_", "")

    if args.cdk_path:
        branches.append(run_cdk_branch(args, f"cdk_{ts}", env))
    if args.ansible_path:
        branches.append(run_ansible_branch(args, make_ansible_run_id(), env))

    hybrid_report = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "branches": branches,
    }
    report_path = _log_dir() / f"{run_id}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(hybrid_report, indent=2), encoding="utf-8")
    print(json.dumps({"stage": "hybrid", "report_path": str(report_path), "branches": [
        {k: b.get(k) for k in ("target", "status", "decision", "score")} for b in branches
    ]}, indent=2))

    # Exit non-zero if any attempted branch failed hard or was rejected.
    bad = {"error", "reject", "deploy_failed"}
    failed = [b for b in branches if b.get("status") in bad]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
