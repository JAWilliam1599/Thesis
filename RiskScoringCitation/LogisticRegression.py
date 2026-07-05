import pandas as pd
import joblib

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression

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

X = df.drop(columns=["sample_id", "label"])
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
# Feature Scaling
# =====================================

scaler = StandardScaler()

X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# =====================================
# Logistic Regression
# =====================================

model = LogisticRegression(
    max_iter=1000,
    class_weight="balanced",
    random_state=42
)

model.fit(
    X_train_scaled,
    y_train
)

# =====================================
# Prediction
# =====================================

y_pred = model.predict(X_test_scaled)

# probability of being insecure (label=1)

y_prob = model.predict_proba(X_test_scaled)[:, 1]

# =====================================
# Evaluation
# =====================================

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

# =====================================
# Learned coefficients
# =====================================

importance = pd.DataFrame({

    "Feature": X.columns,

    "Coefficient": model.coef_[0]

})

importance = importance.sort_values(
    by="Coefficient",
    ascending=False
)

print("=" * 60)
print("Feature Importance")
print(importance)

importance.to_csv(
    "feature_importance.csv",
    index=False
)

# =====================================
# Predict entire dataset
# =====================================

all_scaled = scaler.transform(X)

risk = model.predict_proba(all_scaled)[:, 1] * 100

df["risk_score"] = risk

df.to_csv(
    "dataset_with_risk.csv",
    index=False
)

# =====================================
# Save model
# =====================================

joblib.dump(
    model,
    "logistic_regression.pkl"
)

joblib.dump(
    scaler,
    "scaler.pkl"
)

print("=" * 60)
print("Model saved.")
print("Risk score saved.")