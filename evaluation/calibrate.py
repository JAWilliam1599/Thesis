"""Confirm every evaluation fixture still scores inside its declared band.

Scanner upgrades move absolute scores.  This check is what keeps the declared
expectations in ``examples/eval-fixtures/expectations.yaml`` honest: it reports
the observed score and decision for each fixture and exits non-zero if any
fixture has drifted out of the band it claims.

    python -m evaluation.calibrate            # all fixtures
    python -m evaluation.calibrate --verbose  # plus a per-finding breakdown
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from evaluation.scenarios import load_fixtures  # noqa: E402


def _score_fixture(fixture, online: bool) -> dict:
    """Score one fixture through the same gate the pipeline uses.

    Infracost and AWS Config are off by default: both need network and account
    credentials, and neither is deterministic, so including them would make
    calibration depend on the environment rather than on the fixture.
    """
    if fixture.branch == "ansible":
        from pipeline.ansible_pipeline import run_ansible_gate

        return run_ansible_gate(fixture.path, run_id=None)

    from pipeline.cdk_pipeline import clear_cdk_out, run_cdk_command, run_iac_gate

    clear_cdk_out(fixture.path)
    synth = run_cdk_command(fixture.path, "synth")
    if synth["return_code"] != 0:
        return {"score": None, "decision": "synth_failed",
                "findings": [], "scanner_status": {},
                "error": synth["output"][-800:]}
    return run_iac_gate(
        fixture.path,
        run_id=None,
        use_infracost=online,
        use_aws_config=online,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", choices=("cdk", "ansible"), default=None)
    parser.add_argument("--fixture", default=None, help="Calibrate a single fixture by id.")
    parser.add_argument("--online", action="store_true",
                        help="Also run Infracost and AWS Config (needs credentials).")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--show-findings", action="store_true",
                        help="Print every individual finding.")
    args = parser.parse_args()

    fixtures = [
        f for f in load_fixtures()
        if args.branch in (None, f.branch) and args.fixture in (None, f.id)
    ]
    drifted: list[str] = []

    header = f"{'fixture':<34}{'branch':<9}{'expected':<10}{'observed':<10}{'score':>6}"
    print(header)
    print("-" * len(header))

    for fixture in fixtures:
        report = _score_fixture(fixture, args.online)
        observed = report.get("decision")
        score = report.get("score")
        ok = observed == fixture.expect_decision
        if not ok:
            drifted.append(fixture.id)
        flag = "" if ok else "   <-- DRIFT"
        print(f"{fixture.id:<34}{fixture.branch:<9}{fixture.expect_decision:<10}"
              f"{str(observed):<10}{str(score):>6}{flag}")

        if args.verbose:
            by_source = collections.Counter(
                (f.get("source"), f.get("severity")) for f in report.get("findings", [])
            )
            for (source, severity), count in sorted(by_source.items()):
                print(f"    {source:<16}{severity:<10}x{count}")
            for component, value in (report.get("components") or {}).items():
                if value:
                    print(f"    component {component}: {value}")
            for label, status in (report.get("scanner_status") or {}).items():
                if status != "ok":
                    print(f"    scanner {label}: {status}")
            if report.get("error"):
                print(f"    error: {report['error']}")

        if args.show_findings:
            for finding in report.get("findings", []):
                print(f"    [{finding.get('severity'):<8}] {finding.get('resource_id')}: "
                      f"{finding.get('message')}")

    print()
    if drifted:
        print(f"{len(drifted)} fixture(s) drifted out of band: {', '.join(drifted)}")
        return 1
    print(f"All {len(fixtures)} fixture(s) scored inside their declared band.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
