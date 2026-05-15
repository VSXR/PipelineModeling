from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import joblib

from trainer import ModelTrainer
from promote import ModelPromoter

BASE         = Path(__file__).parent
WEIGHTS_PATH = BASE / "weights" / "model.pkl"
METRICS_PATH = BASE / "metrics.json"

THRESHOLDS: dict[str, float] = {
    "accuracy": 0.85,
    "f1":       0.82,
    "roc_auc":  0.90,
}


def _git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()


def _git_ref() -> str:
    return os.getenv(
        "GITHUB_REF_NAME",
        subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"]
        ).decode().strip(),
    )


def _save_local_artifacts(metrics: dict[str, float], clf) -> None:
    """Persist the raw SGDClassifier so the API local pickle remains partial_fit-compatible."""
    WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, WEIGHTS_PATH)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))


def main() -> None:
    tracking_uri = os.environ["MLFLOW_TRACKING_URI"]
    model_name   = os.getenv("MLFLOW_MODEL_NAME", "pipeline-model")
    experiment   = os.getenv("MLFLOW_EXPERIMENT", "pipeline-breast-cancer")

    trainer = ModelTrainer(tracking_uri, experiment, model_name)
    result  = trainer.train(git_commit=_git_commit(), git_ref=_git_ref())

    clf = trainer.fitted_pipeline.named_steps["clf"]
    _save_local_artifacts(result.metrics, clf)

    promo = ModelPromoter(tracking_uri, model_name, THRESHOLDS).promote(result.version)

    print(f"version={result.version} run_id={result.run_id}")
    print(f"promoted={promo.promoted} reason={promo.reason}")
    for k, v in result.metrics.items():
        print(f"metric.{k}={v:.4f}")

    if not promo.promoted:
        sys.exit(1)


if __name__ == "__main__":
    main()
