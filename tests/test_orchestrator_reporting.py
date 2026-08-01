"""Tests for the hybrid orchestrator's run-report contract.

The evaluation depends on every invocation leaving a machine-readable summary,
including invocations that crash: a run that produces no summary cannot be
classified, which is precisely the anomaly this instrumentation removes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.run_hybrid_pipeline as orch  # noqa: E402


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SYSSECOPS_LOG_DIR", str(tmp_path))
    return tmp_path


def _reports(log_dir: Path) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(log_dir.glob("hybrid_*.json"))]


def test_crash_still_writes_a_report_with_traceback(log_dir, monkeypatch, capsys):
    def boom(*_a, **_kw):
        raise RuntimeError("synth exploded")

    monkeypatch.setattr(orch, "run_ansible_branch", boom)
    monkeypatch.setattr(sys, "argv", ["run_hybrid_pipeline.py", "--ansible-path", str(ROOT)])

    assert orch.main() == 3

    reports = _reports(log_dir)
    assert len(reports) == 1
    report = reports[0]
    assert report["status"] == "aborted"
    assert report["abort"]["exception"] == "RuntimeError"
    assert report["abort"]["message"] == "synth exploded"
    assert "RuntimeError" in report["abort"]["traceback"]


def test_crash_report_keeps_branches_that_already_finished(log_dir, monkeypatch):
    monkeypatch.setattr(orch, "run_cdk_branch",
                        lambda *_a, **_kw: {"target": "cdk", "status": "gated_ok"})

    def boom(*_a, **_kw):
        raise KeyboardInterrupt

    monkeypatch.setattr(orch, "run_ansible_branch", boom)
    monkeypatch.setattr(sys, "argv", [
        "run_hybrid_pipeline.py", "--cdk-path", str(ROOT), "--ansible-path", str(ROOT),
    ])

    assert orch.main() == 3
    report = _reports(log_dir)[0]
    assert report["abort"]["exception"] == "KeyboardInterrupt"
    assert [b["target"] for b in report["branches"]] == ["cdk"]


def test_completed_report_carries_experiment_and_provenance(log_dir, monkeypatch):
    monkeypatch.setattr(orch, "run_ansible_branch",
                        lambda *_a, **_kw: {"target": "ansible", "status": "gated_ok",
                                            "decision": "pass", "score": 0})
    monkeypatch.setattr(sys, "argv", [
        "run_hybrid_pipeline.py", "--ansible-path", str(ROOT),
        "--scenario", "ans-reject-01", "--scenario-class", "reject",
        "--expect-decision", "reject", "--expect-status", "reject",
        "--campaign-id", "c1", "--replicate", "3",
        "--no-infracost", "--no-checkov",
    ])

    assert orch.main() == 0
    report = _reports(log_dir)[0]

    assert report["status"] == "completed"
    assert report["experiment"] == {
        "scenario": "ans-reject-01",
        "scenario_class": "reject",
        "expect_decision": "reject",
        "expect_status": "reject",
        "campaign_id": "c1",
        "replicate": 3,
    }
    assert report["conditions"]["disabled"] == ["checkov", "infracost"]
    assert report["conditions"]["thresholds"] == {"pass_max": 20, "review_max": 80}
    assert isinstance(report["duration_s"], float)
    assert "git" in report["provenance"]


@pytest.mark.parametrize("status,expected_exit", [
    ("gated_ok", 0), ("deployed", 0), ("review", 0),
    ("reject", 1), ("error", 1), ("deploy_failed", 1),
])
def test_exit_code_reflects_branch_outcome(log_dir, monkeypatch, status, expected_exit):
    monkeypatch.setattr(orch, "run_ansible_branch",
                        lambda *_a, **_kw: {"target": "ansible", "status": status})
    monkeypatch.setattr(sys, "argv", ["run_hybrid_pipeline.py", "--ansible-path", str(ROOT)])
    assert orch.main() == expected_exit


def test_no_target_is_a_usage_error(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_hybrid_pipeline.py"])
    assert orch.main() == 2


# --------------------------------------------------------------------------- #
# Stage instrumentation
# --------------------------------------------------------------------------- #
def test_record_stage_times_and_labels():
    stages: list[dict] = []
    entry = orch._record_stage(stages, "cdk.synth", 0.0, {"return_code": 0})
    assert stages == [entry]
    assert entry["stage"] == "cdk.synth"
    assert entry["return_code"] == 0
    assert entry["duration_s"] >= 0
    assert "output_tail" not in entry


def test_record_stage_keeps_output_only_for_failures():
    stages: list[dict] = []
    ok = orch._record_stage(stages, "s", 0.0, {"return_code": 0, "output": "x" * 50},
                            keep_output=True)
    bad = orch._record_stage(stages, "s", 0.0, {"return_code": 2, "output": "y" * 50},
                             keep_output=True)
    assert "output_tail" not in ok
    assert bad["output_tail"] == "y" * 50


def test_record_stage_truncates_long_output():
    stages: list[dict] = []
    entry = orch._record_stage(
        stages, "s", 0.0,
        {"return_code": 1, "output": "z" * (orch._OUTPUT_TAIL_CHARS + 500)},
        keep_output=True,
    )
    assert len(entry["output_tail"]) == orch._OUTPUT_TAIL_CHARS


def test_record_stage_accepts_extra_labels():
    stages: list[dict] = []
    entry = orch._record_stage(stages, "ansible.deploy", 0.0, {"return_code": 4},
                               classification="connectivity")
    assert entry["classification"] == "connectivity"


def test_gate_evidence_extracts_the_fields_the_evaluation_needs():
    evidence = orch._gate_evidence({
        "scanner_status": {"checkov": "ok", "infracost": "unavailable"},
        "components": {"severity": 30, "ml_risk": 12},
        "findings": [{"severity": "high"}, {"severity": "low"}],
    })
    assert evidence == {
        "scanner_status": {"checkov": "ok", "infracost": "unavailable"},
        "components": {"severity": 30, "ml_risk": 12},
        "finding_count": 2,
    }


def test_gate_evidence_tolerates_a_sparse_report():
    assert orch._gate_evidence({}) == {
        "scanner_status": {}, "components": {}, "finding_count": 0,
    }
