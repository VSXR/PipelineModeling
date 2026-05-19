"""
Thread-safe singleton managing the active predictor lifecycle.

Locking strategy:
  _infer_lock — reader lock; multiple concurrent inference calls allowed.
  _swap_lock  — writer lock; serialises partial_fit and version switches.

Version backend: MLflow Model Registry.
  - On startup:  loads from local model.pkl (no server dependency).
  - switch_version(): loads a registered version from MLflow by version
    number or alias (e.g. "Production", "Staging", "1", "2").
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import settings
from .metrics import pipeline_metrics
from .predictor import BasePredictor, SKLearnPredictor

chaos_state: dict = {"inference_error_rate": 0.0}


class ModelManager:
    _instance: Optional["ModelManager"] = None
    _initialised: bool = False

    def __new__(cls) -> "ModelManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialised = False
        return cls._instance

    @classmethod
    def get_instance(cls) -> "ModelManager":
        return cls()

    @staticmethod
    def _read_metrics_file(model_path: Path) -> dict[str, float]:
        metrics_path = model_path.parent.parent / "metrics.json"
        try:
            return json.loads(metrics_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _init_locks(self) -> None:
        if not self._initialised:
            self._infer_lock: asyncio.Lock = asyncio.Lock()
            self._swap_lock: asyncio.Lock = asyncio.Lock()
            self._predictor: Optional[BasePredictor] = None
            self._version: str = "unloaded"
            self._initialised = True

    # ── startup load (local file, no MLflow dependency) ───────────────────────

    async def _load_weights(self, model_path: Optional[str] = None) -> None:
        path = Path(model_path or settings.model_path)
        loop = asyncio.get_running_loop()
        if path.exists():
            self._predictor = await loop.run_in_executor(
                None, SKLearnPredictor.load, str(path)
            )
        else:
            self._predictor = SKLearnPredictor.create_default()
            await loop.run_in_executor(None, self._predictor.save, str(path))
        self._version = datetime.now(timezone.utc).isoformat()
        pipeline_metrics.set_model_loaded(True)
        pipeline_metrics.set_model_quality(
            self._read_metrics_file(Path(model_path or settings.model_path))
        )

    async def load(self, model_path: Optional[str] = None) -> None:
        self._init_locks()
        async with self._swap_lock:
            await self._load_weights(model_path)

    # ── inference ─────────────────────────────────────────────────────────────

    async def predict(self, features: list) -> dict:
        self._init_locks()
        async with self._infer_lock:
            if self._predictor is None:
                raise RuntimeError("Model not loaded")
            if (
                chaos_state["inference_error_rate"] > 0
                and random.random() < chaos_state["inference_error_rate"]
            ):
                raise RuntimeError("Simulated inference error [chaos engineering]")

            import numpy as np
            X = np.array(features, dtype=np.float64).reshape(1, -1)
            loop = asyncio.get_running_loop()
            prediction, probability = await loop.run_in_executor(
                None, self._predictor.predict, X
            )
            return {"prediction": prediction, "probability": probability}

    # ── incremental training ──────────────────────────────────────────────────

    async def partial_fit(self, features: list, labels: list) -> None:
        self._init_locks()
        async with self._swap_lock:
            if self._predictor is None:
                raise RuntimeError("Model not loaded")

            import numpy as np
            X = np.array(features, dtype=np.float64)
            y = np.array(labels, dtype=np.int64)
            loop = asyncio.get_running_loop()

            await loop.run_in_executor(None, self._predictor.partial_fit, X, y)
            await loop.run_in_executor(None, self._predictor.save, settings.model_path)
            self._version = datetime.now(timezone.utc).isoformat()

    # ── hot-swap via MLflow Model Registry ───────────────────────────────────

    async def switch_version(self, model_ref: str) -> str:
        """
        Load a specific model version from MLflow Model Registry.

        model_ref: version number ("1", "2") or alias ("Production", "Staging").
        """
        self._init_locks()
        previous = self._version

        async with self._swap_lock:
            pipeline_metrics.set_model_loaded(False)
            loop = asyncio.get_running_loop()
            t0 = time.perf_counter()
            try:
                await loop.run_in_executor(None, self._pull_from_registry, model_ref)
                duration = time.perf_counter() - t0
                pipeline_metrics.set_model_loaded(True)
                pipeline_metrics.record_version_switch(status="ok", duration_s=duration)
                pipeline_metrics.set_model_quality(
                    self._read_metrics_file(Path(settings.model_path))
                )
            except Exception:
                if self._predictor is not None:
                    pipeline_metrics.set_model_loaded(True)
                raise

        return previous

    # ── register current model to MLflow ─────────────────────────────────────

    async def register_to_mlflow(self) -> str:
        self._init_locks()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._push_to_registry)

    def _push_to_registry(self) -> str:
        import joblib
        import mlflow
        import mlflow.sklearn
        from mlflow import MlflowClient

        path = Path(settings.model_path)
        if not path.exists():
            raise RuntimeError(
                "No model artifact on disk. Call POST /train/ at least once before registering."
            )

        sk_model = joblib.load(path)
        tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
        model_name = os.getenv("MLFLOW_MODEL_NAME", "pipeline-model")
        experiment_name = os.getenv("MLFLOW_EXPERIMENT", "pipeline-breast-cancer")
        mlflow.set_tracking_uri(tracking_uri)

        client = MlflowClient()
        exp = client.get_experiment_by_name(experiment_name)
        if exp is not None and not exp.artifact_location.startswith("mlflow-artifacts:"):
            client.delete_experiment(exp.experiment_id)

        mlflow.set_experiment(experiment_name)

        with mlflow.start_run() as run:
            mlflow.sklearn.log_model(
                sk_model=sk_model,
                artifact_path="model",
                registered_model_name=model_name,
            )
            run_id = run.info.run_id

        versions = client.search_model_versions(
            f"name='{model_name}' and run_id='{run_id}'"
        )
        return str(versions[0].version) if versions else "registered"

    def _pull_from_registry(self, model_ref: str) -> None:
        import mlflow.sklearn  # type: ignore[import]
        tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
        model_name = os.getenv("MLFLOW_MODEL_NAME", "pipeline-model")
        mlflow.set_tracking_uri(tracking_uri)
        sk_model = mlflow.sklearn.load_model(f"models:/{model_name}/{model_ref}")
        self._predictor = SKLearnPredictor(sk_model)
        self._version = model_ref

    # ── properties ────────────────────────────────────────────────────────────

    @property
    def version(self) -> str:
        return self._version

    @property
    def is_loaded(self) -> bool:
        return self._predictor is not None
