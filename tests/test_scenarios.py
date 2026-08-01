"""Tests for the pre-registered campaign declarations.

The declarations are the evaluation's protocol: if they can be loaded with a
duplicate id, a missing fixture, or a decision label the gate never emits, then
the "pre-registered" claim is hollow.  These tests pin the validation.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from evaluation.scenarios import (  # noqa: E402
    Fixture,
    Scenario,
    load_fixtures,
    load_scenarios,
    parity_pairs,
    total_runs,
)


def _write(path: Path, payload: dict) -> Path:
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


@pytest.fixture()
def fixture_dirs(tmp_path: Path) -> Path:
    for name in ("alpha", "beta"):
        (tmp_path / name).mkdir()
    return tmp_path


def _fixture_entry(fixture_id: str, branch: str, rel_path: str, **extra) -> dict:
    return {
        "id": fixture_id,
        "branch": branch,
        "path": rel_path,
        "band": extra.pop("band", "pass"),
        "expect_decision": extra.pop("expect_decision", "pass"),
        **extra,
    }


# --------------------------------------------------------------------------- #
# The real declarations must stay loadable
# --------------------------------------------------------------------------- #
def test_repository_fixtures_load():
    fixtures = load_fixtures()
    assert fixtures, "expectations.yaml declares no fixtures"
    for fixture in fixtures:
        assert fixture.path.is_dir()
        assert fixture.expect_decision in {"pass", "review", "reject"}


def test_repository_scenarios_load():
    scenarios = load_scenarios()
    assert scenarios
    assert len({s.id for s in scenarios}) == len(scenarios)


def test_every_band_is_covered_on_both_branches():
    """The campaign is only balanced if each branch exercises all three bands."""
    scenarios = load_scenarios()
    for branch in ("cdk", "ansible"):
        bands = {s.fixture.band for s in scenarios if s.branch == branch}
        assert {"pass", "review", "reject"} <= bands, f"{branch} misses a band"


def test_total_runs_sums_replicates():
    scenarios = load_scenarios()
    assert total_runs(scenarios) == sum(s.replicates for s in scenarios)


# --------------------------------------------------------------------------- #
# Fixture validation
# --------------------------------------------------------------------------- #
def test_duplicate_fixture_id_is_rejected(tmp_path, fixture_dirs, monkeypatch):
    monkeypatch.setattr("evaluation.scenarios.ROOT_DIR", fixture_dirs)
    path = _write(tmp_path / "f.yaml", {"fixtures": [
        _fixture_entry("dup", "cdk", "alpha"),
        _fixture_entry("dup", "ansible", "beta"),
    ]})
    with pytest.raises(ValueError, match="duplicate fixture id"):
        load_fixtures(path)


def test_unknown_branch_is_rejected(tmp_path, fixture_dirs, monkeypatch):
    monkeypatch.setattr("evaluation.scenarios.ROOT_DIR", fixture_dirs)
    path = _write(tmp_path / "f.yaml", {"fixtures": [
        _fixture_entry("x", "terraform", "alpha"),
    ]})
    with pytest.raises(ValueError, match="unknown branch"):
        load_fixtures(path)


def test_unknown_decision_is_rejected(tmp_path, fixture_dirs, monkeypatch):
    monkeypatch.setattr("evaluation.scenarios.ROOT_DIR", fixture_dirs)
    path = _write(tmp_path / "f.yaml", {"fixtures": [
        _fixture_entry("x", "cdk", "alpha", expect_decision="maybe"),
    ]})
    with pytest.raises(ValueError, match="unknown expect_decision"):
        load_fixtures(path)


def test_missing_fixture_directory_is_rejected(tmp_path, fixture_dirs, monkeypatch):
    """A fixture that does not exist would otherwise fail silently at run time."""
    monkeypatch.setattr("evaluation.scenarios.ROOT_DIR", fixture_dirs)
    path = _write(tmp_path / "f.yaml", {"fixtures": [
        _fixture_entry("x", "cdk", "does-not-exist"),
    ]})
    with pytest.raises(FileNotFoundError, match="fixture directory missing"):
        load_fixtures(path)


def test_band_defaults_to_expected_decision(tmp_path, fixture_dirs, monkeypatch):
    monkeypatch.setattr("evaluation.scenarios.ROOT_DIR", fixture_dirs)
    entry = {"id": "x", "branch": "cdk", "path": "alpha", "expect_decision": "review"}
    path = _write(tmp_path / "f.yaml", {"fixtures": [entry]})
    assert load_fixtures(path)[0].band == "review"


# --------------------------------------------------------------------------- #
# Scenario validation
# --------------------------------------------------------------------------- #
@pytest.fixture()
def declarations(tmp_path, fixture_dirs, monkeypatch):
    monkeypatch.setattr("evaluation.scenarios.ROOT_DIR", fixture_dirs)
    fixtures_path = _write(tmp_path / "f.yaml", {"fixtures": [
        _fixture_entry("cdk-pass", "cdk", "alpha"),
        _fixture_entry("ans-reject", "ansible", "beta",
                       band="reject", expect_decision="reject"),
    ]})
    return fixtures_path


def test_unknown_fixture_reference_is_rejected(tmp_path, declarations):
    path = _write(tmp_path / "s.yaml", {"scenarios": [
        {"id": "s1", "fixture": "nope", "expect_status": "gated_ok"},
    ]})
    with pytest.raises(KeyError, match="unknown fixture"):
        load_scenarios(path, declarations)


def test_zero_replicates_is_rejected(tmp_path, declarations):
    path = _write(tmp_path / "s.yaml", {"scenarios": [
        {"id": "s1", "fixture": "cdk-pass", "expect_status": "gated_ok", "replicates": 0},
    ]})
    with pytest.raises(ValueError, match="replicates must be"):
        load_scenarios(path, declarations)


def test_duplicate_scenario_id_is_rejected(tmp_path, declarations):
    path = _write(tmp_path / "s.yaml", {"scenarios": [
        {"id": "s1", "fixture": "cdk-pass", "expect_status": "gated_ok"},
        {"id": "s1", "fixture": "ans-reject", "expect_status": "reject"},
    ]})
    with pytest.raises(ValueError, match="duplicate scenario id"):
        load_scenarios(path, declarations)


def test_scenario_inherits_fixture_decision(tmp_path, declarations):
    path = _write(tmp_path / "s.yaml", {"scenarios": [
        {"id": "s1", "fixture": "ans-reject", "expect_status": "reject"},
    ]})
    assert load_scenarios(path, declarations)[0].expect_decision == "reject"


def test_scenario_may_override_decision_for_degraded_runs(tmp_path, declarations):
    """Removing a scanner can legitimately move the band, but must be declared."""
    path = _write(tmp_path / "s.yaml", {"scenarios": [
        {"id": "s1", "fixture": "ans-reject", "expect_status": "review",
         "expect_decision": "review", "degradation": "secret-scan",
         "flags": ["--no-secret-scan"]},
    ]})
    scenario = load_scenarios(path, declarations)[0]
    assert scenario.expect_decision == "review"
    assert scenario.fixture.expect_decision == "reject"
    assert scenario.degradation == "secret-scan"


def test_scenario_override_still_validated(tmp_path, declarations):
    path = _write(tmp_path / "s.yaml", {"scenarios": [
        {"id": "s1", "fixture": "cdk-pass", "expect_status": "gated_ok",
         "expect_decision": "probably-fine"},
    ]})
    with pytest.raises(ValueError, match="unknown expect_decision"):
        load_scenarios(path, declarations)


# --------------------------------------------------------------------------- #
# Command construction
# --------------------------------------------------------------------------- #
def _scenario(branch: str, **kwargs) -> Scenario:
    fixture = Fixture(id="fx", branch=branch, path=Path("/tmp/fx"),
                      band=kwargs.pop("band", "review"),
                      expect_decision=kwargs.pop("expect_decision", "review"))
    return Scenario(id="sc", fixture=fixture,
                    expect_status=kwargs.pop("expect_status", "review"),
                    expect_decision=fixture.expect_decision, **kwargs)


def test_command_args_select_the_right_path_flag():
    assert "--cdk-path" in _scenario("cdk").command_args()
    assert "--ansible-path" in _scenario("ansible").command_args()


def test_command_args_carry_the_declaration_into_the_report():
    """The run's own report must record what was expected of it."""
    args = _scenario("cdk", band="reject", expect_decision="reject",
                     expect_status="reject").command_args()
    for flag, value in (("--scenario", "sc"), ("--scenario-class", "reject"),
                        ("--expect-decision", "reject"), ("--expect-status", "reject")):
        assert args[args.index(flag) + 1] == value


def test_command_args_append_flags_last():
    args = _scenario("ansible", flags=["--no-checkov", "--manual-approve"]).command_args()
    assert args[-2:] == ["--no-checkov", "--manual-approve"]


def test_branch_is_derived_from_the_fixture():
    assert _scenario("ansible").branch == "ansible"


# --------------------------------------------------------------------------- #
# Parity grouping
# --------------------------------------------------------------------------- #
def _parity_fixture(fixture_id: str, branch: str, pair: str | None) -> Fixture:
    return Fixture(id=fixture_id, branch=branch, path=Path("/tmp"), band="reject",
                   expect_decision="reject", parity_pair=pair)


def test_parity_pairs_group_by_branch():
    pairs = parity_pairs([
        _parity_fixture("a-cdk", "cdk", "open-ssh"),
        _parity_fixture("a-ans", "ansible", "open-ssh"),
    ])
    assert set(pairs["open-ssh"]) == {"cdk", "ansible"}


def test_incomplete_parity_pairs_are_dropped():
    """One side alone cannot support a cross-boundary agreement claim."""
    pairs = parity_pairs([
        _parity_fixture("a-cdk", "cdk", "open-ssh"),
        _parity_fixture("b-ans", "ansible", "plaintext-secret"),
    ])
    assert pairs == {}


def test_unpaired_fixtures_are_ignored():
    assert parity_pairs([_parity_fixture("solo", "cdk", None)]) == {}
