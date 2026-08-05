"""Derive the candidate weakness classes for the detection-coverage catalogue.

The parity fixtures used in the earlier campaign were chosen by the author, and
therefore could not distinguish "the gate covers this class" from "this class
was chosen because the gate covers it".  This script removes that freedom: the
candidate set is derived mechanically from MITRE's published CWE-1008
(Architectural Concepts) view, using filters that refer only to fields MITRE
publishes and never to the gate's rule set.

Selection filters (fixed before any fixture was authored):
    F1  the weakness is a member of one of the twelve CWE-1008 categories
    F2  its abstraction is Base or Class -- Variant entries are tied to a single
        language or technology and so cannot have a faithful expression on both
        sides of the boundary; Pillar and Compound entries are too abstract to
        author as a single fixture
    F3  at least one published Mode of Introduction is a deployment-time phase
        (Operation, System Configuration, Installation, Bundling), which is the
        set of phases an infrastructure-as-code change can act in

What remains after F1-F3 is a candidate pool, not the final list.  Choosing one
representative per category requires judgement about whether a faithful
expression exists in both AWS CDK and Ansible; that step is recorded, with its
reasons, in coverage_catalogue.yaml.

    python -m evaluation.build_coverage_catalogue
    python -m evaluation.build_coverage_catalogue --category 1013
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
CATALOGUE_DIR = Path(__file__).resolve().parent / "catalogue"
VIEW_XML = CATALOGUE_DIR / "1008.xml"
VIEW_ZIP = CATALOGUE_DIR / "1008.xml.zip"
CANDIDATES_JSON = CATALOGUE_DIR / "candidates.json"

VIEW_URL = "https://cwe.mitre.org/data/xml/views/1008.xml.zip"

KEEP_ABSTRACTIONS = {"Base", "Class"}
DEPLOYMENT_PHASES = {"Operation", "System Configuration", "Installation", "Bundling"}


def _ns(root: ET.Element) -> dict[str, str]:
    return {"c": root.tag.split("}")[0].strip("{")}


def _text(element: ET.Element | None) -> str:
    return " ".join((element.text or "").split()) if element is not None else ""


def load_view(path: Path = VIEW_XML) -> tuple[ET.Element, dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} not found. Download it with:\n"
            f"  curl -sSL -o {VIEW_ZIP} {VIEW_URL} && unzip -o {VIEW_ZIP} -d {CATALOGUE_DIR}"
        )
    root = ET.parse(path).getroot()
    return root, _ns(root)


def provenance() -> dict:
    """Identify exactly which published revision the catalogue was drawn from."""
    root, _ = load_view()
    digest = hashlib.sha256(VIEW_ZIP.read_bytes()).hexdigest() if VIEW_ZIP.is_file() else None
    return {
        "source": VIEW_URL,
        "view": "CWE-1008 Architectural Concepts",
        "cwe_version": root.get("Version"),
        "cwe_date": root.get("Date"),
        "archive_sha256": digest,
    }


def collect(root: ET.Element, ns: dict[str, str]) -> list[dict]:
    """Apply F1-F3 and return the surviving candidates, grouped by category."""
    weaknesses = {w.get("ID"): w for w in root.findall(".//c:Weakness", ns)}

    candidates: list[dict] = []
    for category in root.findall(".//c:Category", ns):
        for member in category.findall(".//c:Has_Member", ns):
            weakness = weaknesses.get(member.get("CWE_ID"))
            if weakness is None:
                continue

            abstraction = weakness.get("Abstraction")
            phases = sorted({
                _text(p)
                for p in weakness.findall(".//c:Modes_Of_Introduction/c:Introduction/c:Phase", ns)
            })
            deployment_phases = sorted(set(phases) & DEPLOYMENT_PHASES)

            if abstraction not in KEEP_ABSTRACTIONS or not deployment_phases:
                continue

            candidates.append({
                "category_id": category.get("ID"),
                "category": category.get("Name"),
                "cwe_id": weakness.get("ID"),
                "name": weakness.get("Name"),
                "abstraction": abstraction,
                "status": weakness.get("Status"),
                "phases": phases,
                "deployment_phases": deployment_phases,
                "description": _text(weakness.find("c:Description", ns))[:400],
            })
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--category", help="Show only this CWE-1008 category id, e.g. 1013.")
    parser.add_argument("--describe", action="store_true", help="Include CWE descriptions.")
    parser.add_argument("--json", action="store_true", help="Write candidates.json and exit.")
    args = parser.parse_args()

    root, ns = load_view()
    candidates = collect(root, ns)
    meta = provenance()

    if args.json:
        CANDIDATES_JSON.write_text(
            json.dumps({"provenance": meta, "candidates": candidates}, indent=2),
            encoding="utf-8",
        )
        print(f"wrote {CANDIDATES_JSON.relative_to(ROOT_DIR)}: {len(candidates)} candidates")
        return 0

    print(f"CWE {meta['cwe_version']} ({meta['cwe_date']})  view {meta['view']}")
    print(f"filters: abstraction in {sorted(KEEP_ABSTRACTIONS)}, "
          f"introduced in {sorted(DEPLOYMENT_PHASES)}\n")

    shown = [c for c in candidates if args.category in (None, c["category_id"])]
    current = None
    for candidate in shown:
        if candidate["category_id"] != current:
            current = candidate["category_id"]
            print(f"\nCWE-{current} {candidate['category']}")
            print("-" * 72)
        print(f"  CWE-{candidate['cwe_id']:<5} {candidate['name'][:52]:<54}"
              f"{candidate['abstraction']}")
        if args.describe:
            print(f"        {candidate['description'][:160]}")

    print(f"\n{len(shown)} candidates across "
          f"{len({c['category_id'] for c in shown})} categories.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
