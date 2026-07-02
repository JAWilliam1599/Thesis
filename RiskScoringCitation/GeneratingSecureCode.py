import csv
import json
import os
import subprocess
from pathlib import Path
import sys


# ==========================
# Bandit
# ==========================
def run_bandit(file_path: Path):

    result = subprocess.run(
        [
            "bandit",
            "-f",
            "json",
            str(file_path)
        ],
        capture_output=True,
        text=True,
        encoding="utf-8"
    )

    features = {
        "bandit_high": 0,
        "bandit_medium": 0,
        "bandit_low": 0,

        "bandit_conf_high": 0,
        "bandit_conf_medium": 0,
        "bandit_conf_low": 0,

        "total_bandit": 0
    }

    if result.returncode not in [0, 1]:
        return features

    try:
        data = json.loads(result.stdout)
    except Exception:
        return features

    for finding in data.get("results", []):

        sev = finding.get(
            "issue_severity",
            ""
        ).upper()

        conf = finding.get(
            "issue_confidence",
            ""
        ).upper()

        features["total_bandit"] += 1

        if sev == "HIGH":
            features["bandit_high"] += 1
        elif sev == "MEDIUM":
            features["bandit_medium"] += 1
        elif sev == "LOW":
            features["bandit_low"] += 1

        if conf == "HIGH":
            features["bandit_conf_high"] += 1
        elif conf == "MEDIUM":
            features["bandit_conf_medium"] += 1
        elif conf == "LOW":
            features["bandit_conf_low"] += 1

    return features


# ==========================
# Semgrep
# ==========================
def run_semgrep(file_path: Path):

    result = subprocess.run(
        [
            "semgrep",
            "scan",
            "--config=auto",
            "--json",
            str(file_path)
        ],
        capture_output=True,
        text=True,
        encoding="utf-8"
    )

    features = {
        "semgrep_high": 0,
        "semgrep_medium": 0,
        "semgrep_low": 0,

        "total_semgrep": 0
    }

    if result.returncode not in [0, 1]:
        return features

    try:
        data = json.loads(result.stdout)
    except Exception:
        return features

    for finding in data.get("results", []):

        sev = (
            finding
            .get("extra", {})
            .get("severity", "")
            .upper()
        )

        features["total_semgrep"] += 1

        if sev in ["ERROR", "HIGH"]:
            features["semgrep_high"] += 1

        elif sev in ["WARNING", "MEDIUM"]:
            features["semgrep_medium"] += 1

        elif sev in ["INFO", "LOW"]:
            features["semgrep_low"] += 1

    return features

#==========================
# Should Scan
#==========================

def should_scan(file: Path):

    # Ignore package files
    if file.name == "__init__.py":
        return False

    # Ignore tests
    if "test" in file.parts:
        return False

    if file.name.startswith("test_"):
        return False

    # Read source
    try:
        code = file.read_text(
            encoding="utf-8",
            errors="ignore"
        )
    except Exception:
        return False

    lines = code.splitlines()

    # Remove blank/comment lines
    code_lines = [
        line for line in lines
        if line.strip()
        and not line.strip().startswith("#")
    ]

    # Too small
    if len(code_lines) < 20:
        return False

    # Too large
    if len(code_lines) > 700:
        return False

    return True


# ==========================
# Scan Folder
# ==========================
def scan_folder(folder, label, output_csv):

    folder = Path(folder)

    py_files = [
        f for f in sorted(folder.rglob("*.py"))
        if should_scan(f)
    ]

    print(f"Scanning {len(py_files)} filtered files")

    fieldnames = [
        "sample_id",
        "label",

        "bandit_high",
        "bandit_medium",
        "bandit_low",

        "bandit_conf_high",
        "bandit_conf_medium",
        "bandit_conf_low",

        "semgrep_high",
        "semgrep_medium",
        "semgrep_low",

        "total_bandit",
        "total_semgrep"
    ]

    with open(
        output_csv,
        "w",
        newline="",
        encoding="utf-8"
    ) as csvfile:

        writer = csv.DictWriter(
            csvfile,
            fieldnames=fieldnames
        )

        writer.writeheader()

        for i, file in enumerate(py_files):

            if (i >= 40):
                break # Stop after 40 files

            print(f"{i}: Scanning:", file)

            bandit = run_bandit(file)
            semgrep = run_semgrep(file)

            row = {
                "sample_id": file.relative_to(folder).as_posix(),
                "label": label,

                **bandit,
                **semgrep
            }

            writer.writerow(row)

    print("Done!")

def generateDataset(file, label, output_csv):
    with open(file, "r", encoding="utf-8") as f:
        data = [json.loads(line) for line in f]

    fieldnames = [
        "sample_id",
        "label",

        "bandit_high",
        "bandit_medium",
        "bandit_low",

        "bandit_conf_high",
        "bandit_conf_medium",
        "bandit_conf_low",

        "semgrep_high",
        "semgrep_medium",
        "semgrep_low",

        "total_bandit",
        "total_semgrep"
    ]

    with open(
        output_csv,
        "w",
        newline="",
        encoding="utf-8"
    ) as csvfile:

        writer = csv.DictWriter(
            csvfile,
            fieldnames=fieldnames
        )

        writer.writeheader()

        for i, item in enumerate(data):

            sample_id = item.get("sample_id", f"sample_{i}")
            code = item.get("Insecure_code", "")

            # Save code to a temporary file
            temp_file_path = Path(f"temp_{i}.py")
            temp_file_path.write_text(code, encoding="utf-8")

            bandit = run_bandit(temp_file_path)
            semgrep = run_semgrep(temp_file_path)

            # Remove the temporary file
            temp_file_path.unlink()

            row = {
                "sample_id": sample_id,
                "label": label,

                **bandit,
                **semgrep
            }

            writer.writerow(row)

    print("Done!")

# ==========================
# Example
# ==========================
if __name__ == "__main__":

    sys.path.append(os.getcwd())

    # Secure dataset
    scan_folder(
        folder=r".\rich-main",
        label=0,
        output_csv="secure_dataset3.csv"
    )

    # Insecure dataset
    # generateDataset(
    #     file=r"dataset.jsonl",
    #     label=1,
    #     output_csv="insecure.csv"
    # )