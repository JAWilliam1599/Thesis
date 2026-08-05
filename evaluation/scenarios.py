"""Fixture and scenario definitions for the evaluation campaign.

Two declarative inputs are loaded here:

``examples/eval-fixtures/expectations.yaml``
    What each fixture should provoke from the gate.  ``expect_decision``
    depends only on the code being scanned, so it lives with the fixture.

``evaluation/scenarios.yaml``
    The campaign matrix: which fixture is run under which conditions, how many
    replicates, and the terminal status expected under those conditions.

``evaluation/coverage_catalogue.yaml``
    The weakness classes detection coverage is measured over, derived from
    MITRE CWE-1008 rather than chosen by the author, together with the matcher
    that decides whether a report names each class.

Keeping both declarative means the sample is *pre-registered* — the set of runs
and their expected outcomes is fixed before execution, so results cannot be
selected after the fact.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
FIXTURES_FILE = ROOT_DIR / "examples" / "eval-fixtures" / "expectations.yaml"
SCENARIOS_FILE = Path(__file__).resolve().parent / "scenarios.yaml"
CATALOGUE_FILE = Path(__file__).resolve().parent / "coverage_catalogue.yaml"

VALID_DECISIONS = {"pass", "review", "reject"}
VALID_BRANCHES = {"cdk", "ansible"}

# Finding fields the permissive matcher reads.  Deliberately includes the free
# text message: a scanner that names the weakness in vocabulary this catalogue
# did not anticipate should still be credited.
MATCH_FIELDS = ("category", "check_id", "message")


@dataclass(frozen=True)
class Fixture:
    id: str
    branch: str
    path: Path
    band: str
    expect_decision: str
    rationale: str = ""
    parity_pair: str | None = None
    weakness_class: str | None = None


@dataclass(frozen=True)
class WeaknessClass:
    """One catalogued weakness class, with the matcher that credits detection.

    Both the class list and these matchers were fixed before any fixture was
    authored and before any detection rule was written in response, so a class
    reported as undetected is a measurement of the gate rather than an artefact
    of how the question was asked.
    """

    id: str
    cwe: int
    cwe_name: str
    category: str
    categories: tuple[str, ...]
    pattern: re.Pattern[str]
    cloud_expression: str = ""
    onprem_expression: str = ""

    @property
    def label(self) -> str:
        return f"CWE-{self.cwe}"

    def matches(self, finding: dict[str, Any]) -> bool:
        """True when this finding names the weakness class."""
        if str(finding.get("category") or "") in self.categories:
            return True
        haystack = " ".join(str(finding.get(f) or "") for f in MATCH_FIELDS)
        return bool(self.pattern.search(haystack))

    def matching(self, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [f for f in findings if self.matches(f)]


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
                weakness_class=entry.get("weakness_class"),
            )
        )

    return fixtures


def load_coverage_catalogue(path: Path = CATALOGUE_FILE) -> list[WeaknessClass]:
    """Load the CWE-derived weakness classes coverage is measured over."""
    data = _read_yaml(path)
    entries = data.get("classes") or []
    classes: list[WeaknessClass] = []
    seen: set[str] = set()

    for entry in entries:
        class_id = str(entry["id"])
        if class_id in seen:
            raise ValueError(f"duplicate weakness class id: {class_id}")
        seen.add(class_id)

        detects = entry.get("detects") or {}
        try:
            pattern = re.compile(str(detects.get("pattern") or r"(?!)"), re.IGNORECASE)
        except re.error as exc:
            raise ValueError(f"{class_id}: invalid detects.pattern: {exc}") from exc

        classes.append(
            WeaknessClass(
                id=class_id,
                cwe=int(entry["cwe"]),
                cwe_name=str(entry["cwe_name"]),
                category=str(entry["category"]),
                categories=tuple(str(c) for c in (detects.get("categories") or [])),
                pattern=pattern,
                cloud_expression=str(entry.get("cloud_expression", "")).strip(),
                onprem_expression=str(entry.get("onprem_expression", "")).strip(),
            )
        )

    if not classes:
        raise ValueError(f"{path} declares no weakness classes")
    return classes


def load_controls(path: Path = CATALOGUE_FILE) -> dict[str, str]:
    """Branch -> fixture id of the clean fixture each matcher must stay silent on."""
    controls = _read_yaml(path).get("controls") or {}
    missing = VALID_BRANCHES - set(controls)
    if missing:
        raise ValueError(f"{path}: no control fixture declared for {sorted(missing)}")
    return {str(branch): str(fixture) for branch, fixture in controls.items()}


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


def coverage_pairs(
    fixtures: list[Fixture], classes: list[WeaknessClass]
) -> dict[str, dict[str, Fixture]]:
    """Group coverage fixtures by catalogue class id, keyed by branch.

    A class with a fixture on only one branch is returned as-is rather than
    dropped: a missing fixture and an undetected weakness are different facts,
    and silently discarding the former would misreport the latter.
    """
    known = {c.id for c in classes}
    grouped: dict[str, dict[str, Fixture]] = {c.id: {} for c in classes}
    for fixture in fixtures:
        if not fixture.weakness_class:
            continue
        if fixture.weakness_class not in known:
            raise KeyError(
                f"{fixture.id}: weakness_class {fixture.weakness_class!r} "
                f"is not in {CATALOGUE_FILE.name}"
            )
        grouped[fixture.weakness_class][fixture.branch] = fixture
    return grouped


def total_runs(scenarios: list[Scenario]) -> int:
    return sum(s.replicates for s in scenarios)
