"""Fixture and scenario definitions for the evaluation campaign.

Two declarative inputs are loaded here:

``examples/eval-fixtures/expectations.yaml``
    What each fixture should provoke from the gate.  ``expect_decision``
    depends only on the code being scanned, so it lives with the fixture.

``evaluation/scenarios.yaml``
    The campaign matrix: which fixture is run under which conditions, how many
    replicates, and the terminal status expected under those conditions.

Keeping both declarative means the sample is *pre-registered* — the set of runs
and their expected outcomes is fixed before execution, so results cannot be
selected after the fact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
FIXTURES_FILE = ROOT_DIR / "examples" / "eval-fixtures" / "expectations.yaml"
SCENARIOS_FILE = Path(__file__).resolve().parent / "scenarios.yaml"

VALID_DECISIONS = {"pass", "review", "reject"}
VALID_BRANCHES = {"cdk", "ansible"}


@dataclass(frozen=True)
class Fixture:
    id: str
    branch: str
    path: Path
    band: str
    expect_decision: str
    rationale: str = ""
    parity_pair: str | None = None


@dataclass(frozen=True)
class Scenario:
    """One pre-registered cell of the campaign matrix."""

    id: str
    fixture: Fixture
    expect_status: str
    expect_decision: str
    replicates: int = 1
    flags: list[str] = field(default_factory=list)
    degradation: str | None = None
    requires: list[str] = field(default_factory=list)
    purpose: str = ""

    @property
    def branch(self) -> str:
        return self.fixture.branch

    def command_args(self) -> list[str]:
        """Orchestrator arguments for a single run of this scenario."""
        path_flag = "--cdk-path" if self.branch == "cdk" else "--ansible-path"
        return [
            path_flag, str(self.fixture.path),
            "--scenario", self.id,
            "--scenario-class", self.fixture.band,
            "--expect-decision", self.expect_decision,
            "--expect-status", self.expect_status,
            *self.flags,
        ]


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"declaration file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping at the top level")
    return data


def load_fixtures(path: Path = FIXTURES_FILE) -> list[Fixture]:
    """Load and validate the declared fixtures."""
    entries = _read_yaml(path).get("fixtures") or []
    fixtures: list[Fixture] = []
    seen: set[str] = set()

    for entry in entries:
        fixture_id = str(entry["id"])
        if fixture_id in seen:
            raise ValueError(f"duplicate fixture id: {fixture_id}")
        seen.add(fixture_id)

        branch = str(entry["branch"])
        if branch not in VALID_BRANCHES:
            raise ValueError(f"{fixture_id}: unknown branch {branch!r}")

        expect_decision = str(entry["expect_decision"])
        if expect_decision not in VALID_DECISIONS:
            raise ValueError(f"{fixture_id}: unknown expect_decision {expect_decision!r}")

        fixture_path = ROOT_DIR / str(entry["path"])
        if not fixture_path.is_dir():
            raise FileNotFoundError(f"{fixture_id}: fixture directory missing: {fixture_path}")

        fixtures.append(
            Fixture(
                id=fixture_id,
                branch=branch,
                path=fixture_path,
                band=str(entry.get("band", expect_decision)),
                expect_decision=expect_decision,
                rationale=str(entry.get("rationale", "")).strip(),
                parity_pair=entry.get("parity_pair"),
            )
        )

    return fixtures


def load_scenarios(
    path: Path = SCENARIOS_FILE,
    fixtures_path: Path = FIXTURES_FILE,
) -> list[Scenario]:
    """Load and validate the campaign matrix."""
    by_id = {f.id: f for f in load_fixtures(fixtures_path)}
    entries = _read_yaml(path).get("scenarios") or []
    scenarios: list[Scenario] = []
    seen: set[str] = set()

    for entry in entries:
        scenario_id = str(entry["id"])
        if scenario_id in seen:
            raise ValueError(f"duplicate scenario id: {scenario_id}")
        seen.add(scenario_id)

        fixture_id = str(entry["fixture"])
        if fixture_id not in by_id:
            raise KeyError(f"{scenario_id}: unknown fixture {fixture_id!r}")

        replicates = int(entry.get("replicates", 1))
        if replicates < 1:
            raise ValueError(f"{scenario_id}: replicates must be >= 1")

        fixture = by_id[fixture_id]
        # Degrading a scanner can legitimately move the decision, so a scenario
        # may override the fixture's expectation — but it must say so.
        expect_decision = str(entry.get("expect_decision") or fixture.expect_decision)
        if expect_decision not in VALID_DECISIONS:
            raise ValueError(f"{scenario_id}: unknown expect_decision {expect_decision!r}")

        scenarios.append(
            Scenario(
                id=scenario_id,
                fixture=fixture,
                expect_status=str(entry["expect_status"]),
                expect_decision=expect_decision,
                replicates=replicates,
                flags=[str(f) for f in (entry.get("flags") or [])],
                degradation=entry.get("degradation"),
                requires=[str(r) for r in (entry.get("requires") or [])],
                purpose=str(entry.get("purpose", "")).strip(),
            )
        )

    return scenarios


def parity_pairs(fixtures: list[Fixture]) -> dict[str, dict[str, Fixture]]:
    """Group parity fixtures by pair id, keyed by branch.

    Only complete pairs (one fixture per branch) are returned; an incomplete
    pair cannot support a cross-boundary agreement claim.
    """
    grouped: dict[str, dict[str, Fixture]] = {}
    for fixture in fixtures:
        if fixture.parity_pair:
            grouped.setdefault(fixture.parity_pair, {})[fixture.branch] = fixture
    return {pair: sides for pair, sides in grouped.items() if len(sides) == 2}


def total_runs(scenarios: list[Scenario]) -> int:
    return sum(s.replicates for s in scenarios)
