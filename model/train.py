"""
Bootstrap: entrena un SGDClassifier inicial y genera los artefactos
que DVC espera según dvc.yaml:

  - model/weights/model.pkl    (outs)
  - model/metrics.json         (metrics)
  - model/plots/confusion_matrix.csv  (plots)

Uso:
    python model/train.py
    dvc add model/weights/model.pkl
    git add model/weights/model.pkl.dvc model/metrics.json model/plots/
    git commit -m "feat: initial model v1"
    git tag v1.0.0
    dvc push
"""

import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import SGDClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    confusion_matrix,
)

# ── Parámetros rastreados por DVC (params) ───────────────────────────
N_SAMPLES = 6000
N_FEATURES = 10
RANDOM_STATE = 42

# ── Rutas de salida ──────────────────────────────────────────────────
BASE = Path(__file__).parent
WEIGHTS_PATH = BASE / "weights" / "model.pkl"
METRICS_PATH = BASE / "metrics.json"
PLOTS_DIR = BASE / "plots"
CM_PATH = PLOTS_DIR / "confusion_matrix.csv"


def generate_dataset(n: int, n_features: int, rng: np.random.Generator):
    X = rng.standard_normal((n, n_features))
    y = (X[:, 0] + 0.5 * X[:, 1] + 0.25 * X[:, 2] > 0.5).astype(int)
    return X, y


def save_metrics(y_true, y_pred, path: Path) -> dict:
    metrics = {
        "accuracy": round(accuracy_score(y_true, y_pred), 5),
        "f1": round(f1_score(y_true, y_pred), 5),
        "precision": round(precision_score(y_true, y_pred), 5),
        "recall": round(recall_score(y_true, y_pred), 5),
        "n_samples": len(y_true),
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
    rng = np.random.default_rng(RANDOM_STATE)
    X, y = generate_dataset(N_SAMPLES, N_FEATURES, rng)

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

    print(f"Model   -> {WEIGHTS_PATH}")
    print(f"Metrics -> {METRICS_PATH}")
    print(f"Plots   -> {CM_PATH}")
    print(f"  accuracy : {metrics['accuracy']}")
    print(f"  f1       : {metrics['f1']}")
    print(f"  classes  : {model.classes_}")


if __name__ == "__main__":
    train()
