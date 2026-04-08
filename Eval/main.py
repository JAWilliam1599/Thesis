import quickVal

if __name__ == "__main__":
    # Will accept code from the AI through API and validate it using quickVal
    simpleVal = quickVal.QuickVal()

    result = simpleVal.validate()

    if not result["approval"]:
        print("Rejected")
        for issue in result["issues"]:
            print(f"- {issue}")

        # Optionally, we can ask the model to fix the issues and revalidate

    # Continue for the next checking