from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

import mlflow
import mlflow.sklearn
import numpy as np
from mlflow.tracking import MlflowClient
from sklearn.datasets import load_breast_cancer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class TrainResult:
    version: str
    run_id: str
    metrics: dict[str, float]
    registered_name: str


class ModelTrainer:
    def __init__(
        self,
        tracking_uri: str,
        experiment: str,
        model_name: str,
    ) -> None:
        self._tracking_uri = tracking_uri
        self._experiment = experiment
        self._model_name = model_name
        self._fitted_pipeline: Pipeline | None = None

    def train(self, git_commit: str, git_ref: str) -> TrainResult:
        mlflow.set_tracking_uri(self._tracking_uri)
        mlflow.set_experiment(self._experiment)

        X, y = self._load_data()
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        pipeline = self._build_pipeline()
        pipeline.fit(X_train, y_train)
        self._fitted_pipeline = pipeline

        y_pred = pipeline.predict(X_test)
        y_prob = pipeline.predict_proba(X_test)[:, 1]
        metrics = self._compute_metrics(y_test, y_pred, y_prob)

        with mlflow.start_run() as run:
            self._log_run(run, pipeline, metrics, git_commit, git_ref)
            version = self._register(run.info.run_id, metrics)

        return TrainResult(
            version=version,
            run_id=run.info.run_id,
            metrics=metrics,
            registered_name=self._model_name,
        )

    @property
    def fitted_pipeline(self) -> Pipeline:
        if self._fitted_pipeline is None:
            raise RuntimeError("train() must be called before accessing fitted_pipeline")
        return self._fitted_pipeline

    def _load_data(self) -> tuple[np.ndarray, np.ndarray]:
        ds = load_breast_cancer()
        return ds.data, ds.target

    def _build_pipeline(self) -> Pipeline:
        return Pipeline([
            ("scaler", StandardScaler()),
            ("clf", SGDClassifier(loss="log_loss", max_iter=1000, random_state=42)),
        ])

    def _compute_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_prob: np.ndarray,
    ) -> dict[str, float]:
        return {
            "accuracy":  float(accuracy_score(y_true, y_pred)),
            "f1":        float(f1_score(y_true, y_pred)),
            "precision": float(precision_score(y_true, y_pred)),
            "recall":    float(recall_score(y_true, y_pred)),
            "roc_auc":   float(roc_auc_score(y_true, y_prob)),
        }

    def _log_run(
        self,
        run: mlflow.ActiveRun,
        pipeline: Pipeline,
        metrics: dict[str, float],
        git_commit: str,
        git_ref: str,
    ) -> None:
        clf: SGDClassifier = pipeline.named_steps["clf"]
        mlflow.log_params({
            "model_class":  type(clf).__name__,
            "loss":         clf.loss,
            "max_iter":     clf.max_iter,
            "random_state": clf.random_state,
            "dataset":      "breast_cancer",
            "n_features":   30,
        })
        mlflow.log_metrics(metrics)
        mlflow.set_tags({
            "git.commit_hash":  git_commit,
            "git.ref":          git_ref,
            "environment":      os.getenv("ENVIRONMENT", "ci"),
            "pipeline.version": "1.0",
        })
        mlflow.sklearn.log_model(
            sk_model=pipeline,
            artifact_path="model",
            registered_model_name=self._model_name,
            input_example=np.zeros((1, 30)),
        )

    def _register(self, run_id: str, metrics: dict[str, float]) -> str:
        client = MlflowClient(self._tracking_uri)
        versions = client.search_model_versions(f"run_id='{run_id}'")
        if not versions:
            raise RuntimeError(f"No model version found for run_id={run_id}")
        version = versions[0].version
        client.set_registered_model_alias(self._model_name, "Staging", version)
        now = datetime.now(timezone.utc).isoformat()
        metrics_summary = " | ".join(f"{k}={v:.4f}" for k, v in sorted(metrics.items()))
        client.update_model_version(
            name=self._model_name,
            version=version,
            description=(
                f"SGDClassifier · StandardScaler pipeline trained on Breast Cancer Wisconsin "
                f"(569 samples, 30 features).\n"
                f"Run ID: {run_id}\n"
                f"Registered: {now}\n"
                f"Metrics: {metrics_summary}"
            ),
        )
        client.set_model_version_tag(self._model_name, version, "run_id", run_id)
        client.set_model_version_tag(self._model_name, version, "registered_at", now)
        client.set_model_version_tag(self._model_name, version, "model_name", self._model_name)
        client.set_model_version_tag(self._model_name, version, "alias", "Staging")
        return version
