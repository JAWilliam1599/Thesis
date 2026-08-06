import pandas as pd
import matplotlib.pyplot as plt

# Load dataset
def insecure_dataset_analysis():
    path_dataset = "./dataset/insecure.csv"  # Update this path to your dataset
    df = pd.read_csv(path_dataset)

    # Extract only the CWE number
    df["CWE_Number"] = df["id"].str.extract(r"CWE-(\d+)")

    # Count occurrences
    cwe_counts = df["CWE_Number"].value_counts().sort_values(ascending=False)

    # Plot
    plt.figure(figsize=(12, 6))
    bars = plt.bar(cwe_counts.index, cwe_counts.values)

    plt.title("Distribution of CWE Categories")
    plt.xlabel("CWE Number")
    plt.ylabel("Number of Samples")
    plt.xticks(rotation=90)

    # Add value labels
    for bar in bars:
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            str(int(bar.get_height())),
            ha="center",
            va="bottom",
            fontsize=8,
        )

    plt.tight_layout()
    plt.show()

def secure_dataset_analysis():
    path_dataset = "./dataset/secure_dataset"  # Update this path to your dataset
    for i in range(1, 3):
        df = pd.read_csv(f"{path_dataset}_{i}.csv")

        # Extract only the CWE number
        df["number"] = df["id"].str.extract(r"CWE-(\d+)")

        # Count occurrences
        cwe_counts = df["number"].value_counts().sort_values(ascending=False)

        # Plot
        plt.figure(figsize=(12, 6))
        bars = plt.bar(cwe_counts.index, cwe_counts.values)

        plt.title("Distribution of CWE Categories")
        plt.xlabel("CWE Number")
        plt.ylabel("Number of Samples")
        plt.xticks(rotation=90)

        # Add value labels
        for bar in bars:
            plt.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                str(int(bar.get_height())),
                ha="center",
                va="bottom",
                fontsize=8,
            )

        plt.tight_layout()
        plt.show()

if __name__ == "__main__":
    insecure_dataset_analysis()