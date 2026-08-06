import pandas as pd
from pathlib import Path
import sys
import os

sys.path.append(os.getcwd())

# Folder containing all csv files
CSV_FOLDER = Path("dataset")

# Name of the insecure csv
INSECURE_FILE = "insecure.csv"

# Output file
OUTPUT_FILE = "dataset.csv"

# -----------------------------
# Read insecure dataset
# -----------------------------
dfs = []

insecure_path = CSV_FOLDER / INSECURE_FILE

dfs.append(pd.read_csv(insecure_path))

print(f"Loaded {INSECURE_FILE}")


# -----------------------------
# Read every safe csv
# -----------------------------
for csv_file in CSV_FOLDER.glob("*.csv"):

    if csv_file.name == INSECURE_FILE:
        continue

    print(f"Loaded {csv_file.name}")

    dfs.append(pd.read_csv(csv_file))


# -----------------------------
# Merge
# -----------------------------
dataset = pd.concat(
    dfs,
    ignore_index=True
)

# Optional: shuffle
dataset = dataset.sample(
    frac=1,
    random_state=42
).reset_index(drop=True)


# Save
dataset.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8"
)

print("=" * 40)
print(f"Total samples : {len(dataset)}")
print(f"Secure        : {(dataset['label']==0).sum()}")
print(f"Insecure      : {(dataset['label']==1).sum()}")
print(f"Saved to {OUTPUT_FILE}")