"""Execute the pre-registered evaluation campaign.

Each run is a separate invocation of the hybrid orchestrator, so a crash in one
run cannot contaminate another and every run produces its own persisted report.
The runner writes one row per run to ``logs/experiments/<campaign_id>/runs.jsonl``
and copies each hybrid report alongside it, so the analysis stage never has to
re-read anything from the shared ``logs/`` directory.

    python -m evaluation.run_campaign --list
    python -m evaluation.run_campaign --scenario ans-pass-gate --replicates 1
    python -m evaluation.run_campaign                      # full offline campaign
    python -m evaluation.run_campaign --allow target-host  # include deploy runs
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from evaluation.provenance import collect_provenance  # noqa: E402
from evaluation.scenarios import Scenario, load_scenarios, total_runs  # noqa: E402

ORCHESTRATOR = ROOT_DIR / "scripts" / "run_hybrid_pipeline.py"
EXPERIMENTS_DIR = ROOT_DIR / "logs" / "experiments"


# Infracost prices against a live feed and AWS Config reports live account
# state, so both make a run's score depend on the day it was executed.  The
# registered campaign disables them; --online re-enables them for a separate,
# explicitly non-deterministic arm.
DETERMINISM_FLAGS = ("--no-infracost", "--no-aws-config")


def _make_campaign_id(prefix: str = "rq12") -> str:
    return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def _run_once(scenario: Scenario, replicate: int, campaign_id: str,
              out_dir: Path, timeout: int, online: bool = False) -> dict:
    """Invoke the orchestrator once and return the campaign row for that run."""
    extra: list[str] = []
    if not online and scenario.branch == "cdk":
        extra = [f for f in DETERMINISM_FLAGS if f not in scenario.flags]

    command = [
        sys.executable, str(ORCHESTRATOR),
        *scenario.command_args(),
        *extra,
        "--campaign-id", campaign_id,
        "--replicate", str(replicate),
    ]

    started = time.monotonic()
    try:
        proc = subprocess.run(
            command, cwd=str(ROOT_DIR), capture_output=True, text=True, timeout=timeout
        )
        return_code, stdout, stderr, timed_out = proc.returncode, proc.stdout, proc.stderr, False
    except subprocess.TimeoutExpired as exc:
        return_code, timed_out = -1, True
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")

    wall_s = round(time.monotonic() - started, 3)

    row: dict = {
        "campaign_id": campaign_id,
        "scenario": scenario.id,
        "replicate": replicate,
        "branch": scenario.branch,
        "fixture": scenario.fixture.id,
        "band": scenario.fixture.band,
        "degradation": scenario.degradation,
        "flags": scenario.flags,
        "expect_decision": scenario.expect_decision,
        "expect_status": scenario.expect_status,
        "exit_code": return_code,
        "timed_out": timed_out,
        "wall_s": wall_s,
    }

    report = _locate_report(stdout)
    if report is None:
        # No summary at all: the run is unclassifiable, and that is itself the
        # observation.  Keep the transcript so it can be diagnosed later.
        row.update(observed_decision=None, observed_status=None,
                   report_missing=True, stdout_tail=stdout[-4000:], stderr_tail=stderr[-4000:])
        return row

    saved = out_dir / "reports" / f"{scenario.id}_r{replicate}.json"
    saved.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(report, saved)

    data = json.loads(Path(report).read_text(encoding="utf-8"))
    branches = data.get("branches") or []
    branch = branches[0] if branches else {}

    # The hybrid summary references the gate report but does not embed its
    # findings, and detection coverage is computed from individual findings.
    gate_saved = _copy_gate_report(branch.get("report_path"), saved)

    row.update(
        run_id=data.get("run_id"),
        run_status=data.get("status"),
        duration_s=data.get("duration_s"),
        report_path=str(saved.relative_to(ROOT_DIR)),
        gate_report_path=(str(gate_saved.relative_to(ROOT_DIR)) if gate_saved else None),
        report_missing=False,
        observed_decision=branch.get("decision"),
        observed_status=branch.get("status"),
        score=branch.get("score"),
        components=branch.get("components"),
        finding_count=branch.get("finding_count"),
        scanner_status=branch.get("scanner_status"),
        failure_class=branch.get("failure_class"),
        stages=branch.get("stages"),
        connectivity=branch.get("connectivity"),
        verification=branch.get("verification"),
        idempotence=branch.get("idempotence"),
        approval_record=branch.get("approval_record"),
        rejection_record=branch.get("rejection_record"),
    )
    if data.get("abort"):
        row["abort"] = data["abort"]

    row["decision_conformant"] = row["observed_decision"] == scenario.expect_decision
    row["status_conformant"] = row["observed_status"] == scenario.expect_status
    return row


def _copy_gate_report(gate_path: str | None, saved_hybrid: Path) -> Path | None:
    """Copy the per-branch gate report next to its hybrid summary."""
    if not gate_path:
        return None
    source = Path(gate_path)
    if not source.is_absolute():
        source = ROOT_DIR / source
    if not source.is_file():
        return None
    destination = saved_hybrid.with_name(f"{saved_hybrid.stem}_gate.json")
    shutil.copy2(source, destination)
    return destination


def _locate_report(stdout: str) -> Path | None:
    """Find the hybrid report path in the orchestrator's JSON output.

    Scans backwards so the final hybrid summary wins over the per-stage gate
    report paths printed earlier in the transcript.
    """
    marker = '"report_path": "'
    index = stdout.rfind(marker)
    while index != -1:
        start = index + len(marker)
        end = stdout.find('"', start)
        candidate = Path(stdout[start:end])
        if candidate.name.startswith("hybrid_") and candidate.is_file():
            return candidate
        index = stdout.rfind(marker, 0, index)
    return None


def _selected(scenarios: list[Scenario], args) -> list[Scenario]:
    allowed = set(args.allow or [])
    selected = []
    for scenario in scenarios:
        if args.scenario and scenario.id not in args.scenario:
            continue
        if args.branch and scenario.branch != args.branch:
            continue
        missing = [r for r in scenario.requires if r not in allowed]
        if missing:
            print(f"skip {scenario.id}: requires {', '.join(missing)}")
            continue
        selected.append(scenario)
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", action="append", help="Run only these scenario ids.")
    parser.add_argument("--branch", choices=("cdk", "ansible"), default=None)
    parser.add_argument("--replicates", type=int, default=None,
                        help="Override the declared replicate count (for a pilot run).")
    parser.add_argument("--allow", action="append", default=[],
                        help="Grant a required capability, e.g. --allow target-host.")
    parser.add_argument("--campaign-id", default=None)
    parser.add_argument("--timeout", type=int, default=1800, help="Per-run timeout in seconds.")
    parser.add_argument("--online", action="store_true",
                        help="Allow live Infracost and AWS Config lookups (non-deterministic).")
    parser.add_argument("--list", action="store_true", help="Print the matrix and exit.")
    args = parser.parse_args()

    scenarios = load_scenarios()
    selected = _selected(scenarios, args)

    if not selected:
        print("No scenarios selected.")
        return 2

    if args.list:
        print(f"{'scenario':<28}{'branch':<9}{'decision':<10}{'status':<12}{'reps':>5}")
        print("-" * 64)
        for scenario in selected:
            reps = args.replicates or scenario.replicates
            print(f"{scenario.id:<28}{scenario.branch:<9}{scenario.expect_decision:<10}"
                  f"{scenario.expect_status:<12}{reps:>5}")
        planned = (len(selected) * args.replicates) if args.replicates else total_runs(selected)
        print(f"\n{len(selected)} scenarios, {planned} runs.")
        return 0

    campaign_id = args.campaign_id or _make_campaign_id()
    out_dir = EXPERIMENTS_DIR / campaign_id
    out_dir.mkdir(parents=True, exist_ok=True)
    rows_path = out_dir / "runs.jsonl"

    planned = (len(selected) * args.replicates) if args.replicates else total_runs(selected)
    (out_dir / "manifest.json").write_text(json.dumps({
        "campaign_id": campaign_id,
        "started": datetime.now(timezone.utc).isoformat(),
        "planned_runs": planned,
        "replicate_override": args.replicates,
        "online": bool(args.online),
        "determinism_flags": [] if args.online else list(DETERMINISM_FLAGS),
        "allowed_capabilities": sorted(set(args.allow or [])),
        "provenance": collect_provenance(),
        "scenarios": [
            {
                "id": s.id, "branch": s.branch, "fixture": s.fixture.id,
                "expect_decision": s.expect_decision, "expect_status": s.expect_status,
                "flags": s.flags, "degradation": s.degradation,
                "replicates": args.replicates or s.replicates,
                "purpose": s.purpose,
            }
            for s in selected
        ],
    }, indent=2), encoding="utf-8")

    print(f"campaign {campaign_id}: {len(selected)} scenarios, {planned} runs")
    print(f"output: {out_dir.relative_to(ROOT_DIR)}\n")

    completed = 0
    nonconformant = 0
    with rows_path.open("a", encoding="utf-8") as handle:
        for scenario in selected:
            reps = args.replicates or scenario.replicates
            for replicate in range(1, reps + 1):
                completed += 1
                label = f"[{completed}/{planned}] {scenario.id} r{replicate}"
                print(f"{label} ...", flush=True)

                row = _run_once(scenario, replicate, campaign_id, out_dir,
                                args.timeout, online=args.online)
                handle.write(json.dumps(row) + "\n")
                handle.flush()

                conformant = row.get("decision_conformant") and row.get("status_conformant")
                if not conformant:
                    nonconformant += 1
                mark = "ok " if conformant else "NON"
                print(f"{label} {mark} decision={row.get('observed_decision')} "
                      f"(want {scenario.expect_decision}) "
                      f"status={row.get('observed_status')} "
                      f"(want {scenario.expect_status}) "
                      f"score={row.get('score')} {row.get('wall_s')}s", flush=True)

    print(f"\n{completed} runs written to {rows_path.relative_to(ROOT_DIR)}")
    print(f"{completed - nonconformant}/{completed} conformant")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
