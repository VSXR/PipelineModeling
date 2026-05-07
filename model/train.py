"""
Bootstrap: entrena un SGDClassifier con el dataset Breast Cancer Wisconsin
y genera los artefactos que DVC espera según dvc.yaml.

Salidas:
  model/weights/model.pkl         (outs)
  model/metrics.json              (metrics)
  model/plots/confusion_matrix.csv (plots)
"""

import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.datasets import load_breast_cancer
from sklearn.linear_model import SGDClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    confusion_matrix,
)

# ── Parámetros rastreados por DVC ────────────────────────────────────────────
DATASET      = "breast_cancer"   # sklearn built-in, binario, 30 features
N_FEATURES   = 30                # fijado por el dataset
RANDOM_STATE = 42                # controla train/test split y SGD

# ── Rutas de salida ──────────────────────────────────────────────────────────
BASE         = Path(__file__).parent
WEIGHTS_PATH = BASE / "weights" / "model.pkl"
METRICS_PATH = BASE / "metrics.json"
PLOTS_DIR    = BASE / "plots"
CM_PATH      = PLOTS_DIR / "confusion_matrix.csv"

# Nombres de features exportados para que otros módulos los consuman
FEATURE_NAMES = [
    "radius_mean",      "texture_mean",     "perimeter_mean",  "area_mean",
    "smoothness_mean",  "compactness_mean",  "concavity_mean",  "concpts_mean",
    "symmetry_mean",    "fracdim_mean",
    "radius_se",        "texture_se",        "perimeter_se",    "area_se",
    "smoothness_se",    "compactness_se",    "concavity_se",    "concpts_se",
    "symmetry_se",      "fracdim_se",
    "radius_worst",     "texture_worst",     "perimeter_worst", "area_worst",
    "smoothness_worst", "compactness_worst", "concavity_worst", "concpts_worst",
    "symmetry_worst",   "fracdim_worst",
]


def load_dataset():
    data = load_breast_cancer()
    return data.data, data.target


def save_metrics(y_true, y_pred, path: Path) -> dict:
    metrics = {
        "accuracy":  round(float(accuracy_score(y_true, y_pred)),  5),
        "f1":        round(float(f1_score(y_true, y_pred)),        5),
        "precision": round(float(precision_score(y_true, y_pred)), 5),
        "recall":    round(float(recall_score(y_true, y_pred)),    5),
        "n_samples": int(len(y_true)),
        "dataset":   DATASET,
    }
    path.write_text(json.dumps(metrics, indent=2))
    return metrics


def save_confusion_matrix(y_true, y_pred, path: Path) -> None:
    cm = confusion_matrix(y_true, y_pred)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["actual,predicted,count"]
    for i, row in enumerate(cm):
        for j, val in enumerate(row):
            lines.append(f"{i},{j},{val}")
    path.write_text("\n".join(lines))


def train() -> None:
    X, y = load_dataset()

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y,
    )

    model = SGDClassifier(loss="log_loss", max_iter=1000, random_state=RANDOM_STATE)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, WEIGHTS_PATH)

    metrics = save_metrics(y_test, y_pred, METRICS_PATH)
    save_confusion_matrix(y_test, y_pred, CM_PATH)

    print(f"Dataset  -> {DATASET} ({len(X)} samples, {N_FEATURES} features)")
    print(f"Model    -> {WEIGHTS_PATH}")
    print(f"Metrics  -> {METRICS_PATH}")
    print(f"  accuracy : {metrics['accuracy']}")
    print(f"  f1       : {metrics['f1']}")
    print(f"  classes  : {model.classes_}")


if __name__ == "__main__":
    train()
