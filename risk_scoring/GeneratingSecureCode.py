import csv
import json
import os
import subprocess
from pathlib import Path
import sys

import re


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
        "id",
        "label",

        # Bandit
        "bandit_high",
        "bandit_medium",
        "bandit_low",

        "bandit_conf_high",
        "bandit_conf_medium",
        "bandit_conf_low",

        # Semgrep
        "semgrep_high",
        "semgrep_medium",
        "semgrep_low",

        # Total
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

            #if (i >= 40):
                #break # Stop after 40 files

            print(f"{i}: Scanning:", file)

            bandit = run_bandit(file)
            semgrep = run_semgrep(file)

            row = {
                "id": file.relative_to(folder).as_posix(),
                "label": label,

                **bandit,
                **semgrep
            }

            writer.writerow(row)

    print("Done!")


def generateDataset(file, label, output_csv):
    with open(file, "r", encoding="utf-8") as f:
        data = [json.loads(line) for line in f]

    
    SUPPORTED_CWES = {
    20,22,23,73,77,78,79,80,89,90,94,95,
    116,117,134,190,200,209,259,295,297,
    306,307,311,312,319,326,327,330,338,
    352,377,400,434,502,601,611,614,703,
    732,798,862,863,918
    }


    fieldnames = [
        "id",
        "label",

        # Bandit
        "bandit_high",
        "bandit_medium",
        "bandit_low",

        "bandit_conf_high",
        "bandit_conf_medium",
        "bandit_conf_low",

        # Semgrep
        "semgrep_high",
        "semgrep_medium",
        "semgrep_low",

        # Total
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

            id = item.get("ID", "")
            print(f"{i}: Scanning ID: {id}")
            code = item.get("Insecure_code", "")

            cwe_numbers = [int(x) for x in re.findall(r"\d+", str(id))]

            if not any(cwe in SUPPORTED_CWES for cwe in cwe_numbers):
                print(f"Skipping {id} due to unsupported CWE")
                continue

            # Save code to a temporary file
            temp_file_path = Path(f"temp_{i}.py")
            temp_file_path.write_text(code, encoding="utf-8")

            bandit = run_bandit(temp_file_path)
            semgrep = run_semgrep(temp_file_path)

            # Remove the temporary file
            temp_file_path.unlink()

            row = {
                "id": id,
                "label": label,

                **bandit,
                **semgrep
            }

            writer.writerow(row)

    print("Done!")

def generateDatasetFromPyCode(file, label, output_csv_safe, output_csv_unsafe):
    SUPPORTED_CWES = {
    20,22,23,73,77,78,79,80,89,90,94,95,
    116,117,134,190,200,209,259,295,297,
    306,307,311,312,319,326,327,330,338,
    352,377,400,434,502,601,611,614,703,
    732,798,862,863,918
    }


    fieldnames = [
        "id",
        "label",

        # Bandit
        "bandit_high",
        "bandit_medium",
        "bandit_low",

        "bandit_conf_high",
        "bandit_conf_medium",
        "bandit_conf_low",

        # Semgrep
        "semgrep_high",
        "semgrep_medium",
        "semgrep_low",

        # Total
        "total_bandit",
        "total_semgrep"
    ]

    total_rows = 0
    with open(file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        with open(
            output_csv_safe,
            "w",
            newline="",
            encoding="utf-8"
        ) as csvfile:

            writer = csv.DictWriter(
                csvfile,
                fieldnames=fieldnames
            )

            writer.writeheader()

            with open(
                output_csv_unsafe,
                "w",
                newline="",
                encoding="utf-8"
            ) as csvfile_unsafe:

                writer_unsafe = csv.DictWriter(
                    csvfile_unsafe,
                    fieldnames=fieldnames
                )

                writer_unsafe.writeheader()

                for i, row in enumerate(reader):
                    if i <= -1: # Skip the first 608 rows since already run
                        continue

                    id = row["predicted_cwe_ids"]
                    # unsafe_code = row["vulnerable_function_source"]
                    safe_code = row["patched_function_source"]
                    # cwe = [int(x) for x in re.findall(r"\d+", str(id))]
                    label = row["label"] # it is 0 or 1

                    # if (id == "None" or unsafe_code == "None" or safe_code == "None" or not any(c in SUPPORTED_CWES for c in cwe)):
                    #     print(f"Skipping {id} due to unsupported CWE or missing code")
                    #     continue

                    if (id == "None" or safe_code == "None" or label == "1"):
                        print(f"Skipping {id} due to missing code or label is 1")
                        continue

                    print(f"{i}: Scanning ID: {id}")

                    # # Save code to a temporary file, unsafe one
                    # try:
                    #     temp_file_path = Path(f"temp_{i}.py")
                    #     temp_file_path.write_text(unsafe_code, encoding="utf-8")

                    #     bandit = run_bandit(temp_file_path)
                    #     semgrep = run_semgrep(temp_file_path)

                    # # Remove the temporary file
                    # finally:
                    #     temp_file_path.unlink()

                    # unsafe_row = {
                    #     "id": id,
                    #     "label": label,

                    #     **bandit,
                    #     **semgrep
                    # }

                    # print(f"Writing unsafe row for ID: {id}")
                    # writer_unsafe.writerow(unsafe_row)

                    # Save code to a temporary file, safe one
                    try:
                        temp_file_path = Path(f"temp_{i}.py")
                        temp_file_path.write_text(safe_code, encoding="utf-8")
                        bandit = run_bandit(temp_file_path)
                        semgrep = run_semgrep(temp_file_path)

                    # Remove the temporary file
                    finally:
                        temp_file_path.unlink()

                    safe_row = {
                        "id": id,
                        "label": 0,  # Safe code label

                        **bandit,
                        **semgrep
                    }

                    print(f"Writing safe row for ID: {id}")
                    writer.writerow(safe_row)

                    total_rows += 1  # Count both safe and unsafe rows
                    if (total_rows >= 614):  # Limit to 800 rows
                        print("Reached limit of 800 rows, stopping.")
                        break

            print("Done!")

# ==========================
# Example
# ==========================
if __name__ == "__main__":

    sys.path.append(os.getcwd())

    # Secure dataset
    # scan_folder(
    #     folder=r".\typer-master",
    #     label=0,
    #     output_csv="secure_dataset3.csv"
    # )

    # Insecure dataset
    # generateDataset(
    #     file=r"dataset.jsonl",
    #     label=1,
    #     output_csv="insecure.csv"
    # )

    # Insecure dataset from PyCode_Vul
    generateDatasetFromPyCode(
        file=r"PyCode_Vul train-set.csv",
        label=1,
        output_csv_safe="safe_dataset.csv",
        output_csv_unsafe="unsafe_dataset.csv"
    )

