"""Turn a campaign's persisted runs into the tables reported in the thesis.

Reads only ``logs/experiments/<campaign_id>/runs.jsonl`` and the report copies
beside it, so every number in the evaluation chapter is reproducible from
artefacts without re-running the pipeline.

    python -m evaluation.analyze_campaign --campaign-id rq12_...
    python -m evaluation.analyze_campaign --latest --latex

Outputs (written under the campaign directory, in ``analysis/``):
    rq1_conformance.csv      per-scenario decision/status conformance
    rq1_confusion.csv        expected x observed decision matrix
    rq1_enforcement.csv      enforcement-correctness checks
    rq1_degradation.csv      behaviour with each assurance component removed
    rq1_latency.csv          per-stage duration distribution
    rq2_checkpoints.csv      on-prem checkpoint attainment
    rq2_coverage.csv         detection coverage over the CWE-1008 catalogue
    rq2_discordance.csv      cross-branch agreement on seeing each class
    tables.tex               the same tables as LaTeX (with --latex)
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

EXPERIMENTS_DIR = ROOT_DIR / "logs" / "experiments"

from evaluation.scenarios import (  # noqa: E402
    load_controls,
    load_coverage_catalogue,
    load_fixtures,
)

DECISIONS = ("pass", "review", "reject")


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #
def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Used instead of the normal approximation because the campaign's per-cell
    sample sizes are small and several cells are expected to be at 0 or 1,
    where the normal interval is degenerate.
    """
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denominator = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denominator
    margin = (z / denominator) * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2))
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def _proportion_row(label: str, successes: int, total: int, **extra) -> dict:
    # An unattempted checkpoint has no measured rate; reporting 0/0 with a
    # [0.0, 0.0] interval would read as a measured certainty rather than an
    # absence of evidence.
    if total == 0:
        return {"item": label, "n": 0, "successes": 0, "proportion": None,
                "ci_low": None, "ci_high": None, **extra}
    low, high = wilson_interval(successes, total)
    return {
        "item": label,
        "n": total,
        "successes": successes,
        "proportion": round(successes / total, 4),
        "ci_low": round(low, 4),
        "ci_high": round(high, 4),
        **extra,
    }


def _summarise(values: list[float]) -> dict:
    """Median and interquartile range, reported without assuming normality."""
    if not values:
        return {"n": 0, "median": None, "p25": None, "p75": None,
                "min": None, "max": None}
    ordered = sorted(values)
    quartiles = (
        statistics.quantiles(ordered, n=4) if len(ordered) > 1 else [ordered[0]] * 3
    )
    return {
        "n": len(ordered),
        "median": round(statistics.median(ordered), 3),
        "p25": round(quartiles[0], 3),
        "p75": round(quartiles[2], 3),
        "min": round(ordered[0], 3),
        "max": round(ordered[-1], 3),
    }


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def load_rows(campaign_dir: Path) -> list[dict]:
    rows_path = campaign_dir / "runs.jsonl"
    if not rows_path.is_file():
        raise FileNotFoundError(f"no runs.jsonl in {campaign_dir}")
    return [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def latest_campaign() -> Path:
    candidates = [d for d in EXPERIMENTS_DIR.iterdir() if (d / "runs.jsonl").is_file()]
    if not candidates:
        raise FileNotFoundError(f"no campaigns under {EXPERIMENTS_DIR}")
    return max(candidates, key=lambda d: (d / "runs.jsonl").stat().st_mtime)


# --------------------------------------------------------------------------- #
# RQ1
# --------------------------------------------------------------------------- #
def rq1_conformance(rows: list[dict]) -> list[dict]:
    """Per-scenario decision and status conformance against the declaration."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["scenario"]].append(row)

    out: list[dict] = []
    for scenario, runs in grouped.items():
        total = len(runs)
        decision_ok = sum(1 for r in runs if r.get("decision_conformant"))
        status_ok = sum(1 for r in runs if r.get("status_conformant"))
        both_ok = sum(1 for r in runs if r.get("decision_conformant") and r.get("status_conformant"))
        low, high = wilson_interval(both_ok, total)
        scores = [r["score"] for r in runs if isinstance(r.get("score"), int)]
        out.append({
            "scenario": scenario,
            "branch": runs[0]["branch"],
            "band": runs[0]["band"],
            "degradation": runs[0].get("degradation") or "",
            "expect_decision": runs[0]["expect_decision"],
            "expect_status": runs[0]["expect_status"],
            "n": total,
            "decision_conformant": decision_ok,
            "status_conformant": status_ok,
            "fully_conformant": both_ok,
            "conformance": round(both_ok / total, 4),
            "ci_low": round(low, 4),
            "ci_high": round(high, 4),
            "score_min": min(scores) if scores else None,
            "score_max": max(scores) if scores else None,
            "score_stable": len(set(scores)) <= 1 if scores else None,
        })
    return sorted(out, key=lambda r: (r["branch"], r["scenario"]))


def rq1_confusion(rows: list[dict]) -> list[dict]:
    """Expected x observed decision matrix, per branch."""
    counts: Counter = Counter()
    for row in rows:
        counts[(row["branch"], row["expect_decision"], row.get("observed_decision") or "none")] += 1

    out: list[dict] = []
    for branch in sorted({r["branch"] for r in rows}):
        for expected in DECISIONS:
            observed_labels = sorted(
                {o for (b, e, o) in counts if b == branch and e == expected}
            )
            if not observed_labels:
                continue
            entry = {"branch": branch, "expected": expected}
            total = 0
            for observed in (*DECISIONS, "none"):
                count = counts[(branch, expected, observed)]
                entry[f"observed_{observed}"] = count
                total += count
            entry["n"] = total
            out.append(entry)
    return out


def rq1_enforcement(rows: list[dict]) -> list[dict]:
    """Did the decision actually control what happened next?

    Conformance says the gate produced the right verdict.  Enforcement asks the
    stricter question: was the verdict acted on?  A reject that still deploys is
    a far worse defect than a reject scored one point off.
    """
    checks: dict[str, list[bool]] = defaultdict(list)

    for row in rows:
        decision = row.get("observed_decision")
        status = row.get("observed_status")
        stages = {s.get("stage") for s in (row.get("stages") or [])}
        deployed = any(s.endswith(".deploy") for s in stages)

        if decision == "reject":
            checks["reject blocks deployment"].append(not deployed)
            checks["reject writes a rejection record"].append(bool(row.get("rejection_record")))
        elif decision == "review" and "--manual-approve" not in (row.get("flags") or []):
            checks["unapproved review halts"].append(status == "review" and not deployed)
        elif decision == "review":
            checks["approved review writes an approval record"].append(
                bool(row.get("approval_record"))
            )

        checks["run produces a persisted summary"].append(not row.get("report_missing", False))
        checks["gate reports a status for every scanner"].append(
            bool(row.get("scanner_status"))
        )

    return [
        _proportion_row(label, sum(results), len(results))
        for label, results in checks.items()
    ]


def rq1_degradation(rows: list[dict]) -> list[dict]:
    """What the decision looks like once an assurance component is removed."""
    baseline: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if not row.get("degradation"):
            baseline[row["fixture"]].append(row)

    out: list[dict] = []
    for row in rows:
        if not row.get("degradation"):
            continue
        reference = baseline.get(row["fixture"]) or []
        reference_scores = [r["score"] for r in reference if isinstance(r.get("score"), int)]
        full_score = reference_scores[0] if reference_scores else None
        degraded_score = row.get("score")
        out.append({
            "scenario": row["scenario"],
            "branch": row["branch"],
            "fixture": row["fixture"],
            "removed": row["degradation"],
            "replicate": row["replicate"],
            "full_score": full_score,
            "degraded_score": degraded_score,
            "score_delta": (full_score - degraded_score)
            if isinstance(full_score, int) and isinstance(degraded_score, int) else None,
            "full_decision": reference[0].get("observed_decision") if reference else None,
            "degraded_decision": row.get("observed_decision"),
            "expected_degraded_decision": row["expect_decision"],
            "conformant": bool(row.get("decision_conformant") and row.get("status_conformant")),
            "reached_terminal": row.get("observed_status") not in (None, "error"),
        })
    return out


def rq1_latency(rows: list[dict]) -> list[dict]:
    """Stage duration distribution, and the gate's share of total run time."""
    per_stage: dict[tuple[str, str], list[float]] = defaultdict(list)
    gate_share: dict[str, list[float]] = defaultdict(list)

    for row in rows:
        branch = row["branch"]
        total = row.get("duration_s")
        for stage in row.get("stages") or []:
            name, duration = stage.get("stage"), stage.get("duration_s")
            if isinstance(duration, (int, float)):
                per_stage[(branch, name)].append(float(duration))
                if name.endswith(".gate") and isinstance(total, (int, float)) and total > 0:
                    gate_share[branch].append(100.0 * duration / total)

    out = [
        {"branch": branch, "stage": stage, "unit": "s", **_summarise(values)}
        for (branch, stage), values in sorted(per_stage.items())
    ]
    for branch, shares in sorted(gate_share.items()):
        out.append({
            "branch": branch, "stage": "gate share of run", "unit": "%",
            **_summarise(shares),
        })
    return out


# --------------------------------------------------------------------------- #
# RQ2
# --------------------------------------------------------------------------- #
CHECKPOINTS = (
    ("reachability", lambda r: (r.get("connectivity") or {}).get("reachable")),
    ("syntax validation", lambda r: _stage_ok(r, "ansible.syntax")),
    ("security gate", lambda r: _stage_present(r, "ansible.gate")),
    ("dry run", lambda r: _stage_present(r, "ansible.check")),
    ("apply", lambda r: _stage_ok(r, "ansible.deploy")),
    ("post-apply verification", lambda r: (r.get("verification") or {}).get("verified")),
    ("repeated-run idempotency", lambda r: (r.get("idempotence") or {}).get("idempotent")),
)


def _stage(row: dict, name: str) -> dict | None:
    for stage in row.get("stages") or []:
        if stage.get("stage") == name:
            return stage
    return None


def _stage_present(row: dict, name: str) -> bool | None:
    return True if _stage(row, name) else None


def _stage_ok(row: dict, name: str) -> bool | None:
    stage = _stage(row, name)
    if stage is None:
        return None
    return stage.get("return_code", 0) == 0


def rq2_checkpoints(rows: list[dict]) -> list[dict]:
    """Attainment of each on-prem checkpoint.

    A checkpoint that was never attempted is excluded from its denominator
    rather than counted as a failure, so the reported rate is over runs that
    actually reached that checkpoint.
    """
    ansible_rows = [r for r in rows if r["branch"] == "ansible"]
    out: list[dict] = []
    for label, probe in CHECKPOINTS:
        observed = [probe(r) for r in ansible_rows]
        attempted = [v for v in observed if v is not None]
        out.append(_proportion_row(
            label, sum(1 for v in attempted if v), len(attempted),
            not_attempted=len(observed) - len(attempted),
        ))
    return out


def rq2_failure_classes(rows: list[dict]) -> list[dict]:
    """Attribution of on-prem failures, so none remains unexplained."""
    counts = Counter(
        r.get("failure_class") or "none"
        for r in rows if r["branch"] == "ansible"
    )
    total = sum(counts.values())
    return [
        {"failure_class": name, "count": count,
         "share": round(count / total, 4) if total else None}
        for name, count in counts.most_common()
    ]


# On-premises runs carrying this degradation reproduce the gate as it behaved
# before the semantic configuration rules were added.
BASELINE_DEGRADATION = "ansible_rules_unavailable"


def rq2_parity(rows: list[dict], *, arm: str = "rules enabled") -> list[dict]:
    """Cross-boundary agreement: does one weakness get one verdict?

    Each parity pair encodes a single weakness class on both sides of the hybrid
    boundary.  Agreement is measured, not engineered: the fixtures were written
    to express the same weakness faithfully and whatever bands they land in are
    reported, including disagreements.

    *arm* selects which on-premises configuration to report.  ``"baseline"``
    uses the runs with the semantic rules disabled; any other value uses the
    default configuration.  The cloud side is identical in both arms.
    """
    try:
        pair_of = {f.id: f.parity_pair for f in load_fixtures() if f.parity_pair}
    except Exception:
        return []

    baseline = arm == "baseline"

    # fixture id -> observed decisions and scores across replicates
    observed: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["fixture"] not in pair_of:
            continue
        degraded = row.get("degradation") == BASELINE_DEGRADATION
        if row.get("branch") == "ansible" and degraded != baseline:
            continue
        if row.get("branch") != "ansible" and degraded:
            continue
        observed[row["fixture"]].append(row)

    grouped: dict[str, dict[str, list[dict]]] = defaultdict(dict)
    for fixture_id, runs in observed.items():
        grouped[pair_of[fixture_id]][runs[0]["branch"]] = runs

    out: list[dict] = []
    for pair in sorted(grouped):
        sides = grouped[pair]
        if len(sides) < 2:
            continue
        cloud, onprem = sides.get("cdk", []), sides.get("ansible", [])
        if not cloud or not onprem:
            continue

        cloud_decision = Counter(r.get("observed_decision") for r in cloud).most_common(1)[0][0]
        onprem_decision = Counter(r.get("observed_decision") for r in onprem).most_common(1)[0][0]
        cloud_scores = [r["score"] for r in cloud if isinstance(r.get("score"), int)]
        onprem_scores = [r["score"] for r in onprem if isinstance(r.get("score"), int)]
        cloud_score = statistics.median(cloud_scores) if cloud_scores else None
        onprem_score = statistics.median(onprem_scores) if onprem_scores else None

        out.append({
            "arm": arm,
            "weakness": pair,
            "cloud_decision": cloud_decision,
            "onprem_decision": onprem_decision,
            "agree": cloud_decision == onprem_decision,
            "cloud_score": cloud_score,
            "onprem_score": onprem_score,
            "score_gap": (cloud_score - onprem_score)
            if cloud_score is not None and onprem_score is not None else None,
            "n_cloud": len(cloud),
            "n_onprem": len(onprem),
        })

    if out:
        agreed = sum(1 for r in out if r["agree"])
        low, high = wilson_interval(agreed, len(out))
        out.append({
            "arm": arm,
            "weakness": "ALL PAIRS",
            "cloud_decision": "", "onprem_decision": "",
            "agree": f"{agreed}/{len(out)}",
            "cloud_score": "", "onprem_score": "",
            "score_gap": f"[{round(low, 3)}, {round(high, 3)}]",
            "n_cloud": "", "n_onprem": "",
        })
    return out


# --------------------------------------------------------------------------- #
# RQ2 — detection coverage
# --------------------------------------------------------------------------- #
def _findings(row: dict) -> list[dict] | None:
    """Findings from a run's copied gate report, or None if unavailable.

    An unreadable report is not the same as a report containing no matching
    finding, so it is propagated as None rather than as an empty list.
    """
    path = row.get("gate_report_path")
    if not path:
        return None
    full = ROOT_DIR / path
    if not full.is_file():
        return None
    try:
        return json.loads(full.read_text(encoding="utf-8")).get("findings") or []
    except (json.JSONDecodeError, OSError):
        return None


def _detected_in(runs: list[dict], klass) -> tuple[int, int, set, set]:
    """Runs in which the class was named, plus the categories and sources doing so."""
    considered = matched = 0
    categories: set[str] = set()
    sources: set[str] = set()
    for row in runs:
        findings = _findings(row)
        if findings is None:
            continue
        considered += 1
        hits = klass.matching(findings)
        if hits:
            matched += 1
            categories.update(str(h.get("category") or "?") for h in hits)
            sources.update(str(h.get("source") or "?") for h in hits)
    return considered, matched, categories, sources


def rq2_coverage(rows: list[dict]) -> list[dict]:
    """Is each catalogued weakness class named by the gate, on each branch?

    Coverage rather than decision agreement is the measured quantity.  Two
    artifacts on opposite sides of the boundary are not equivalent — a host
    firewall rule and a security group differ in blast radius and in how many
    controls they can violate — so requiring identical bands would assert an
    equivalence that does not hold, and could be satisfied by reweighting
    rather than by detecting anything new.  A weakness that produces no finding
    at all, by contrast, cannot be scored, reviewed or audited at any
    threshold.

    Detection is credited only when the class matcher fires on the weakness
    fixture *and* stays silent on that branch's control fixture; a rule that
    fires unconditionally therefore earns nothing.
    """
    try:
        classes = load_coverage_catalogue()
        controls = load_controls()
        fixtures = {f.id: f for f in load_fixtures()}
    except (FileNotFoundError, ValueError, KeyError):
        return []

    by_fixture: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        # Degraded-scanner cells deliberately remove a component, so including
        # them would understate the coverage of the configuration under test.
        if not row.get("degradation"):
            by_fixture[row["fixture"]].append(row)

    wired: dict[str, dict[str, str]] = defaultdict(dict)
    for fixture in fixtures.values():
        if fixture.weakness_class:
            wired[fixture.weakness_class][fixture.branch] = fixture.id

    out: list[dict] = []
    tally: dict[str, list[bool]] = defaultdict(list)

    for klass in classes:
        for branch in ("cdk", "ansible"):
            fixture_id = wired.get(klass.id, {}).get(branch)
            runs = by_fixture.get(fixture_id or "", [])
            control_runs = by_fixture.get(controls.get(branch, ""), [])

            considered, matched, categories, sources = _detected_in(runs, klass)
            control_seen, control_hits, control_categories, _ = _detected_in(control_runs, klass)

            measured = bool(fixture_id) and considered > 0 and control_seen > 0
            fired = matched > 0 if fixture_id and considered else None
            # An unexamined control cannot testify to silence, so specificity
            # is unknown rather than satisfied.
            control_silent = control_hits == 0 if control_seen else None
            detected = bool(fired and control_silent) if measured else None
            if measured:
                tally[branch].append(detected)

            out.append({
                "weakness_class": klass.id,
                "cwe": klass.label,
                "cwe_name": klass.cwe_name,
                "cwe_category": klass.category,
                "branch": branch,
                "fixture": fixture_id or "",
                "n_runs": considered,
                "runs_naming_class": matched,
                "fired": fired,
                "control_silent": control_silent,
                "detected": detected,
                "categories": "; ".join(sorted(categories)),
                "sources": "; ".join(sorted(sources)),
                "control_categories": "; ".join(sorted(control_categories)),
            })

    for branch, results in sorted(tally.items()):
        low, high = wilson_interval(sum(results), len(results))
        out.append({
            "weakness_class": "COVERAGE",
            "cwe": "", "cwe_name": "", "cwe_category": "",
            "branch": branch,
            "fixture": "",
            "n_runs": len(results),
            "runs_naming_class": sum(results),
            "fired": "", "control_silent": "",
            "detected": f"{sum(results)}/{len(results)}",
            "categories": f"[{round(low, 3)}, {round(high, 3)}]",
            "sources": "", "control_categories": "",
        })
    return out


def rq2_discordance(rows: list[dict]) -> list[dict]:
    """Where the two branches disagree about seeing the same weakness class.

    Reported as a contingency over classes rather than as two ratios: with a
    catalogue this size the individual discordant classes carry the finding,
    and a pair of proportions invites a reader to treat the class count as a
    sample size.
    """
    coverage = [r for r in rq2_coverage(rows) if r["weakness_class"] != "COVERAGE"]
    if not coverage:
        return []

    seen: dict[str, dict[str, bool | None]] = defaultdict(dict)
    label: dict[str, str] = {}
    for row in coverage:
        seen[row["weakness_class"]][row["branch"]] = row["detected"]
        label[row["weakness_class"]] = f'{row["cwe"]} {row["cwe_name"]}'

    cells: Counter = Counter()
    detail: list[dict] = []
    for class_id, sides in seen.items():
        cloud, onprem = sides.get("cdk"), sides.get("ansible")
        if cloud is None or onprem is None:
            cell = "not measured"
        elif cloud and onprem:
            cell = "both branches"
        elif cloud:
            cell = "cloud only"
        elif onprem:
            cell = "on-premises only"
        else:
            cell = "neither branch"
        cells[cell] += 1
        detail.append({"cell": cell, "weakness_class": class_id, "cwe": label[class_id]})

    total = sum(cells.values())
    summary = [
        {"cell": cell, "classes": count,
         "share": round(count / total, 4) if total else None,
         "members": "; ".join(
             d["cwe"] for d in detail if d["cell"] == cell
         )}
        for cell, count in cells.most_common()
    ]
    return summary


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _escape(value) -> str:
    text = "" if value is None else str(value)
    for char, replacement in (("\\", r"\textbackslash{}"), ("_", r"\_"),
                              ("%", r"\%"), ("&", r"\&"), ("#", r"\#")):
        text = text.replace(char, replacement)
    return text


def latex_table(rows: list[dict], caption: str, label: str,
                columns: list[str] | None = None) -> str:
    if not rows:
        return ""
    columns = columns or list(rows[0].keys())
    spec = "l" * 1 + "r" * (len(columns) - 1)
    lines = [
        r"\begin{table}[htbp]", r"\centering", rf"\caption{{{caption}}}",
        rf"\label{{{label}}}", rf"\begin{{tabular}}{{{spec}}}", r"\hline",
        " & ".join(_escape(c.replace("_", " ")) for c in columns) + r" \\", r"\hline",
    ]
    for row in rows:
        lines.append(" & ".join(_escape(row.get(c)) for c in columns) + r" \\")
    lines += [r"\hline", r"\end{tabular}", r"\end{table}", ""]
    return "\n".join(lines)


def _print_table(title: str, rows: list[dict], columns: list[str]) -> None:
    print(f"\n{title}")
    if not rows:
        print("  (no data)")
        return
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in columns}
    print("  " + "  ".join(c.ljust(widths[c]) for c in columns))
    print("  " + "  ".join("-" * widths[c] for c in columns))
    for row in rows:
        print("  " + "  ".join(str(row.get(c, "")).ljust(widths[c]) for c in columns))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", default=None)
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--latex", action="store_true", help="Also emit tables.tex.")
    args = parser.parse_args()

    if args.campaign_id:
        campaign_dir = EXPERIMENTS_DIR / args.campaign_id
    elif args.latest:
        campaign_dir = latest_campaign()
    else:
        parser.error("pass --campaign-id or --latest")

    rows = load_rows(campaign_dir)
    out_dir = campaign_dir / "analysis"

    tables = {
        "rq1_conformance": (
            rq1_conformance(rows),
            "RQ1: decision conformance per scenario",
            ["scenario", "branch", "expect_decision", "expect_status", "n",
             "fully_conformant", "conformance", "ci_low", "ci_high", "score_min", "score_max"],
        ),
        "rq1_confusion": (
            rq1_confusion(rows),
            "RQ1: expected against observed gate decision",
            ["branch", "expected", "observed_pass", "observed_review",
             "observed_reject", "observed_none", "n"],
        ),
        "rq1_enforcement": (
            rq1_enforcement(rows),
            "RQ1: enforcement correctness",
            ["item", "n", "successes", "proportion", "ci_low", "ci_high"],
        ),
        "rq1_degradation": (
            rq1_degradation(rows),
            "RQ1: gate behaviour under degraded assurance",
            ["scenario", "removed", "full_score", "degraded_score", "score_delta",
             "full_decision", "degraded_decision", "conformant"],
        ),
        "rq1_latency": (
            rq1_latency(rows),
            "RQ1: stage duration distribution",
            ["branch", "stage", "unit", "n", "median", "p25", "p75", "min", "max"],
        ),
        "rq2_checkpoints": (
            rq2_checkpoints(rows),
            "RQ2: on-premises checkpoint attainment",
            ["item", "n", "successes", "proportion", "ci_low", "ci_high", "not_attempted"],
        ),
        "rq2_failure_classes": (
            rq2_failure_classes(rows),
            "RQ2: attribution of on-premises failures",
            ["failure_class", "count", "share"],
        ),
        "rq2_parity": (
            rq2_parity(rows, arm="baseline") + rq2_parity(rows, arm="rules enabled"),
            "RQ2: cross-boundary treatment of the same weakness",
            ["arm", "weakness", "cloud_decision", "onprem_decision", "agree",
             "cloud_score", "onprem_score", "score_gap"],
        ),
        "rq2_coverage": (
            rq2_coverage(rows),
            "RQ2: detection coverage over the CWE-1008 weakness catalogue",
            ["cwe", "cwe_name", "branch", "n_runs", "fired", "control_silent",
             "detected", "categories", "sources"],
        ),
        "rq2_discordance": (
            rq2_discordance(rows),
            "RQ2: agreement between branches on seeing each weakness class",
            ["cell", "classes", "share", "members"],
        ),
    }

    print(f"campaign: {campaign_dir.name}   runs: {len(rows)}")
    latex_parts: list[str] = []
    for name, (data, caption, columns) in tables.items():
        write_csv(out_dir / f"{name}.csv", data)
        _print_table(caption, data, columns)
        if args.latex:
            latex_parts.append(latex_table(data, caption, f"tab:{name}", columns))

    if args.latex:
        (out_dir / "tables.tex").write_text("\n".join(latex_parts), encoding="utf-8")

    print(f"\nwritten to {out_dir.relative_to(ROOT_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
