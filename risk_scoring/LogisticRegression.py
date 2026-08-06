import pandas as pd
import joblib

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
    classification_report
)

# =====================================
# Load dataset
# =====================================

df = pd.read_csv("dataset.csv")

print(df.head())
print()

# =====================================
# Features / Labels
# =====================================

X = df.drop(columns=["id", "label"])
y = df["label"]

# =====================================
# Train / Test Split
# =====================================

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42,
    stratify=y
)

# =====================================
# Feature Scaling (Only for Logistic Regression)
# =====================================

scaler = StandardScaler()

X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)


# =====================================
# Evaluation Function
# =====================================

def evaluate_model(model, X_test, y_test, feature_names, model_name):
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    print("=" * 60)
    print(model_name)
    print("=" * 60)

    print("Accuracy :", accuracy_score(y_test, y_pred))
    print("Precision:", precision_score(y_test, y_pred))
    print("Recall   :", recall_score(y_test, y_pred))
    print("F1 Score :", f1_score(y_test, y_pred))
    print("ROC AUC  :", roc_auc_score(y_test, y_prob))
    print()

    print("Confusion Matrix")
    print(confusion_matrix(y_test, y_pred))
    print()

    print(classification_report(y_test, y_pred))

    # Feature Importance
    if hasattr(model, "coef_"):
        importance = pd.DataFrame({
            "Feature": feature_names,
            "Importance": model.coef_[0]
        })

    elif hasattr(model, "feature_importances_"):
        importance = pd.DataFrame({
            "Feature": feature_names,
            "Importance": model.feature_importances_
        })

    else:
        importance = None

    if importance is not None:
        importance = importance.sort_values(
            by="Importance",
            ascending=False
        )

        print("Feature Importance")
        print(importance)

        filename = model_name.lower().replace(" ", "_") + "_importance.csv"
        importance.to_csv(filename, index=False)


# =====================================
# Logistic Regression
# =====================================

def train_logistic_regression():
    model = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        random_state=42
    )

    model.fit(X_train_scaled, y_train)

    evaluate_model(
        model,
        X_test_scaled,
        y_test,
        X.columns,
        "Logistic Regression"
    )

    # Predict entire dataset
    all_scaled = scaler.transform(X)
    risk = model.predict_proba(all_scaled)[:, 1] * 100

    df_lr = df.copy()
    df_lr["risk_score"] = risk
    df_lr.to_csv("dataset_with_risk_lr.csv", index=False)

    joblib.dump(model, "logistic_regression.pkl")
    joblib.dump(scaler, "scaler.pkl")

    print("Logistic Regression model saved.\n")

    return model


# =====================================
# Random Forest
# =====================================

def train_random_forest():
    model = RandomForestClassifier(
        n_estimators=200,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1
    )

    # No scaling
    model.fit(X_train, y_train)

    evaluate_model(
        model,
        X_test,
        y_test,
        X.columns,
        "Random Forest"
    )

    risk = model.predict_proba(X)[:, 1] * 100

    df_rf = df.copy()
    df_rf["risk_score"] = risk
    df_rf.to_csv("dataset_with_risk_rf.csv", index=False)

    joblib.dump(model, "random_forest.pkl")

    print("Random Forest model saved.\n")

    return model


# =====================================
# Train Models
# =====================================

lr_model = train_logistic_regression()

#rf_model = train_random_forest()

print