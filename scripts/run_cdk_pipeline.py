from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.cdk_pipeline import (
    can_deploy,
    clear_cdk_out,
    extract_stack_name,
    load_gate_report,
    run_bootstrap,
    run_cdk_command,
    run_iac_gate,
    write_approval,
    write_rejection_record,
)
from pipeline.aws_credentials import get_session
from pipeline.notifier import get_notifier
from pipeline.ssm_store import list_monitored_stacks, read_gate_result, write_gate_result
from pipeline.eventbridge_trigger import publish_gate_event
from Monitor.cloudwatch_publisher import publish_gate_metrics, put_log_event
from Monitor.stack_monitor import setup_stack_monitoring


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CDK pipeline with IaC risk gate.")
    parser.add_argument("--project-dir", default="GeneratedCDK", help="CDK project directory.")
    parser.add_argument("--run-id", default=None, help="Override auto-generated run ID (used for gate report filename).")
    parser.add_argument("--approve-run-id", default=None, metavar="RUN_ID",
                        help="Skip synth+gate and approve an existing review-band report by run_id. Use with --deploy.")
    parser.add_argument("--cost-delta-usd", type=float, default=None, help="Override Infracost cost delta in USD (default: auto-detect via infracost).")
    parser.add_argument("--aws-config-violations", type=int, default=None, help="Override AWS Config violations count (default: auto-fetch via boto3).")
    parser.add_argument("--no-infracost", action="store_true", help="Skip infracost cost analysis.")
    parser.add_argument("--no-aws-config", action="store_true", help="Skip AWS Config violations fetch.")
    parser.add_argument("--manual-approve", action="store_true", help="Approve review decision (21-60) for deploy.")
    parser.add_argument("--deploy", action="store_true", help="Run deploy if gate allows.")
    parser.add_argument("--bootstrap", action="store_true", help="Run cdk bootstrap before synth (required for first deploy).")
    parser.add_argument("--no-checkov", action="store_true", help="Skip checkov scan (useful for fast-path testing).")
    parser.add_argument("--no-cfn-lint", action="store_true", help="Skip cfn-lint scan (useful for fast-path testing).")
    parser.add_argument("--prompt", default=None, help="Original CDK request (used with --regen-on-reject).")
    parser.add_argument("--regen-on-reject", action="store_true", help="On gate reject, invoke CDK regen loop instead of exiting.")
    parser.add_argument("--max-regen-attempts", type=int, default=2, help="Maximum regen loop attempts (default: 2, used with --regen-on-reject).")
    parser.add_argument("--query-status", action="store_true", help="Print last gate result per stack from SSM and exit (read-only).")
    return parser.parse_args()


def query_status_main() -> int:
    """Print the last gate result per stack stored in SSM and exit."""
    stacks = list_monitored_stacks()
    if not stacks:
        print("No stacks found in SSM under /syssecops/gate/ (SSM may be disabled or no runs recorded yet).")
        return 0

    header = f"{'STACK':<40} {'SCORE':<8} {'DECISION':<10} {'RUN_ID':<40}"
    print(header)
    print("-" * len(header))
    for stack in stacks:
        result = read_gate_result(stack) or {}
        score = result.get("latest_score", "—")
        decision = result.get("latest_decision", "—")
        run_id = result.get("latest_run_id", "—")
        print(f"{stack:<40} {score:<8} {decision:<10} {run_id:<40}")
    return 0


def _emit_gate_observability(
    gate_report: dict,
    stack_name: str,
) -> None:
    """Fire all Phase 4 observability calls after a gate evaluation.

    All calls are non-blocking; failures are logged as warnings.
    Skips silently when AWS credentials are not available (local dev mode).
    """
    if get_session() is None:
        import logging
        logging.getLogger(__name__).debug(
            "Phase 4 observability skipped — no AWS credentials available."
        )
        return

    run_id = gate_report.get("run_id", "")
    score = gate_report.get("score", 0)
    decision = gate_report.get("decision", "reject")
    findings = gate_report.get("findings") or []
    report_path = gate_report.get("report_path") or ""

    write_gate_result(stack_name, run_id, score, decision, report_path)
    publish_gate_event(run_id, stack_name, decision, score)
    publish_gate_metrics(stack_name, run_id, score, decision, findings)
    put_log_event(stack_name, run_id, gate_report)


def approve_and_deploy_main(args: argparse.Namespace, project_dir: Path, env: dict) -> int:
    """Approve an existing review-band gate report and optionally deploy.

    Skips synth and gate entirely. Loads the saved report, validates the
    decision, writes an approval record, then runs diff + optional deploy.
    """
    run_id: str = args.approve_run_id

    try:
        gate_report = load_gate_report(run_id)
    except FileNotFoundError as exc:
        print(json.dumps({"stage": "approve", "error": str(exc)}, indent=2))
        return 3

    decision = str(gate_report.get("decision", "reject")).lower()
    score = gate_report.get("score", 0)
    _emit_gate_observability(gate_report, extract_stack_name(gate_report))

    if decision == "reject":
        print(json.dumps({
            "stage": "approve",
            "error": f"Cannot approve a rejected gate report (score={score}). Remediate findings and re-run the pipeline.",
            "run_id": run_id,
        }, indent=2))
        return 22

    approval_path = write_approval(run_id, gate_report, approver="cli")
    print(json.dumps({
        "stage": "approve",
        "run_id": run_id,
        "gate_decision": decision,
        "gate_score": score,
        "approval_path": approval_path,
    }, indent=2))

    diff = run_cdk_command(project_dir, "diff", env=env)
    print(json.dumps({"stage": "diff", **diff}, indent=2))
    if diff["return_code"] != 0:
        return 11

    print(json.dumps({"stage": "decision", "allowed": True, "reason": "Approved via --approve-run-id."}, indent=2))

    if not args.deploy:
        return 0

    notifier = get_notifier()
    deploy = run_cdk_command(project_dir, "deploy", env=env)
    print(json.dumps({"stage": "deploy", **deploy}, indent=2))
    deploy_ok = deploy["return_code"] == 0
    if notifier:
        try:
            notifier.send(
                "deploy_success" if deploy_ok else "deploy_failure",
                gate_report,
                extra={"deploy_return_code": deploy["return_code"]},
            )
        except Exception:
            pass
    if deploy_ok:
        stack_name = extract_stack_name(gate_report)
        setup_stack_monitoring(stack_name, project_dir / "cdk.out")
    return 0 if deploy_ok else 12


def main() -> int:
    args = parse_args()
    project_dir = Path(args.project_dir).resolve()

    if not project_dir.exists():
        print(f"ERROR: project directory not found: {project_dir}")
        return 2

    # --- Query-status path: read-only SSM lookup ---
    if args.query_status:
        return query_status_main()

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    # --- Approve-only path: skip synth+gate, load existing report ---
    if args.approve_run_id:
        return approve_and_deploy_main(args, project_dir, env)

    if args.bootstrap:
        bootstrap = run_bootstrap(project_dir, env=env)
        print(json.dumps({"stage": "bootstrap", **bootstrap}, indent=2))
        if bootstrap["return_code"] != 0:
            return 9

    clear_cdk_out(project_dir)
    synth = run_cdk_command(project_dir, "synth", env=env)
    print(json.dumps({"stage": "synth", **synth}, indent=2))
    if synth["return_code"] != 0:
        return 10

    gate_report = run_iac_gate(
        project_dir,
        cost_delta_usd=args.cost_delta_usd,
        aws_config_violations=args.aws_config_violations,
        use_checkov=not args.no_checkov,
        use_cfn_lint=not args.no_cfn_lint,
        use_infracost=not args.no_infracost,
        use_aws_config=not args.no_aws_config,
        run_id=args.run_id,
    )
    print(json.dumps({"stage": "gate", "gate": gate_report}, indent=2))
    report_path = gate_report.get("report_path")
    if report_path:
        print(json.dumps({"stage": "gate_report", "path": report_path}, indent=2))

    # Phase 4 observability: SSM, EventBridge, CloudWatch metrics + logs
    _emit_gate_observability(gate_report, extract_stack_name(gate_report))

    diff = run_cdk_command(project_dir, "diff", env=env)
    print(json.dumps({"stage": "diff", **diff}, indent=2))
    if diff["return_code"] != 0:
        return 11

    allowed, reason = can_deploy(gate_report, manual_review_approved=args.manual_approve)
    print(json.dumps({"stage": "decision", "allowed": allowed, "reason": reason}, indent=2))

    # Write approval record when --manual-approve is used on a review-band decision
    if args.manual_approve and allowed and str(gate_report.get("decision", "")).lower() == "review":
        run_id_val = gate_report.get("run_id") or args.run_id or ""
        if run_id_val:
            approval_path = write_approval(run_id_val, gate_report, approver="cli")
            print(json.dumps({"stage": "approval_record", "path": approval_path}, indent=2))

    notifier = get_notifier()

    if not allowed:
        decision_lower = str(gate_report.get("decision", "")).lower()
        if decision_lower == "review":
            if notifier:
                try:
                    notifier.send("review_required", gate_report)
                except Exception:
                    pass
            return 21

        # Reject path
        run_id_val = gate_report.get("run_id") or args.run_id or ""
        if run_id_val:
            rejection_path = write_rejection_record(run_id_val, gate_report)
            print(json.dumps({"stage": "rejection_record", "path": rejection_path}, indent=2))
        if notifier:
            try:
                notifier.send("reject", gate_report)
            except Exception:
                pass

        if args.regen_on_reject and args.prompt:
            from AIgen.run_cdk_regen import run_cdk_regen_loop
            print(json.dumps({"stage": "regen", "status": "starting", "max_attempts": args.max_regen_attempts}, indent=2))
            regen_result = run_cdk_regen_loop(
                original_prompt=args.prompt,
                project_dir=project_dir,
                max_attempts=args.max_regen_attempts,
            )
            print(json.dumps({"stage": "regen", **regen_result}, indent=2))
            return 0 if regen_result.get("success") else 22

        return 22

    if not args.deploy:
        return 0

    deploy = run_cdk_command(project_dir, "deploy", env=env)
    print(json.dumps({"stage": "deploy", **deploy}, indent=2))
    deploy_ok = deploy["return_code"] == 0
    if notifier:
        try:
            notifier.send(
                "deploy_success" if deploy_ok else "deploy_failure",
                gate_report,
                extra={"deploy_return_code": deploy["return_code"]},
            )
        except Exception:
            pass
    if deploy_ok:
        stack_name = extract_stack_name(gate_report)
        setup_stack_monitoring(stack_name, project_dir / "cdk.out")
    return 0 if deploy_ok else 12


if __name__ == "__main__":
    raise SystemExit(main())
