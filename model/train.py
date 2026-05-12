"""
Bootstrap: entrena un SGDClassifier con el dataset Breast Cancer Wisconsin
y registra el artefacto en MLflow Model Registry.

Salidas locales (compatibilidad con la API en modo sin servidor MLflow):
  model/weights/model.pkl
  model/metrics.json
  model/plots/confusion_matrix.csv

MLflow (cuando MLFLOW_TRACKING_URI está configurado):
  - Experimento: pipeline-breast-cancer
  - Parámetros, métricas y artefactos registrados por run
  - Modelo registrado como "pipeline-model" en el Model Registry
"""

import json
import os
from pathlib import Path

import joblib
import mlflow  # type: ignore[import]
import mlflow.sklearn  # type: ignore[import]
from sklearn.datasets import load_breast_cancer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split

# ── Parámetros ────────────────────────────────────────────────────────────────
DATASET      = "breast_cancer"
N_FEATURES   = 30
RANDOM_STATE = 42

# ── Rutas de salida ───────────────────────────────────────────────────────────
BASE         = Path(__file__).parent
WEIGHTS_PATH = BASE / "weights" / "model.pkl"
METRICS_PATH = BASE / "metrics.json"
PLOTS_DIR    = BASE / "plots"
CM_PATH      = PLOTS_DIR / "confusion_matrix.csv"


# Nombres de features exportados para consumo en otros módulos
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


def _compute_metrics(y_true, y_pred) -> dict:
    return {
        "accuracy":  round(float(accuracy_score(y_true, y_pred)),  5),
        "f1":        round(float(f1_score(y_true, y_pred)),        5),
        "precision": round(float(precision_score(y_true, y_pred)), 5),
        "recall":    round(float(recall_score(y_true, y_pred)),    5),
        "n_samples": int(len(y_true)),
        "dataset":   DATASET,
    }


def _save_local_artifacts(model, metrics: dict, y_true, y_pred) -> None:
    WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, WEIGHTS_PATH)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))

    cm = confusion_matrix(y_true, y_pred)
    CM_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = ["actual,predicted,count"]
    for i, row in enumerate(cm):
        for j, val in enumerate(row):
            lines.append(f"{i},{j},{val}")
    CM_PATH.write_text("\n".join(lines))


def train() -> None:
    X, y = load_dataset()
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y,
    )

    model = SGDClassifier(loss="log_loss", max_iter=1000, random_state=RANDOM_STATE)
    model.fit(X_train, y_train)
    y_pred  = model.predict(X_test)
    metrics = _compute_metrics(y_test, y_pred)

    _save_local_artifacts(model, metrics, y_test, y_pred)

    # ── MLflow tracking + registry ────────────────────────────────────────────
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    model_name   = os.getenv("MLFLOW_MODEL_NAME",   "pipeline-model")
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("pipeline-breast-cancer")

    with mlflow.start_run():
        mlflow.log_params({
            "dataset":      DATASET,
            "n_features":   N_FEATURES,
            "random_state": RANDOM_STATE,
            "model_class":  "SGDClassifier",
            "loss":         "log_loss",
        })
        mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, float)})
        mlflow.log_artifact(str(METRICS_PATH), artifact_path="reports")
        mlflow.log_artifact(str(CM_PATH),      artifact_path="reports")

        model_info = mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path="model",
            registered_model_name=model_name,
            input_example=X_test[:1],
        )
        print(f"MLflow run  -> {mlflow.active_run().info.run_id}")
        print(f"Model URI   -> {model_info.model_uri}")

    print(f"Dataset  -> {DATASET} ({len(X)} samples, {N_FEATURES} features)")
    print(f"Model    -> {WEIGHTS_PATH}")
    print(f"Metrics  -> accuracy={metrics['accuracy']}  f1={metrics['f1']}")


if __name__ == "__main__":
    train()
