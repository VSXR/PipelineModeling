import asyncio
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
from sklearn.linear_model import SGDClassifier

from .config import settings
from .metrics import MODEL_LOADED


class ModelManager:
    """
    Thread-safe singleton managing model lifecycle.

    Hot-swap via DVC is serialised through _swap_lock so concurrent
    version-switch requests queue rather than corrupting model state.
    Inference runs under _infer_lock (reader pattern) and is never
    blocked by training; partial_fit and version-switch share _swap_lock.
    """

    _instance: Optional["ModelManager"] = None

    def __new__(cls) -> "ModelManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialised = False
        return cls._instance

    @classmethod
    def get_instance(cls) -> "ModelManager":
        return cls()

    def _init_locks(self) -> None:
        if not self._initialised:
            self._infer_lock: asyncio.Lock = asyncio.Lock()
            self._swap_lock: asyncio.Lock = asyncio.Lock()
            self._model: Optional[SGDClassifier] = None
            self._version: str = "unloaded"
            self._initialised = True

    async def load(self, model_path: Optional[str] = None) -> None:
        self._init_locks()
        path = Path(model_path or settings.model_path)

        async with self._swap_lock:
            loop = asyncio.get_running_loop()
            if path.exists():
                self._model = await loop.run_in_executor(
                    None, joblib.load, str(path)
                )
            else:
                self._model = SGDClassifier(loss="log_loss", random_state=42)

            self._version = datetime.now(timezone.utc).isoformat()
            MODEL_LOADED.set(1)

    async def predict(self, features: list) -> dict:
        self._init_locks()
        async with self._infer_lock:
            if self._model is None:
                raise RuntimeError("Model not loaded")

            X = np.array(features, dtype=np.float64).reshape(1, -1)
            loop = asyncio.get_running_loop()

            pred = await loop.run_in_executor(None, self._model.predict, X)
            try:
                proba = await loop.run_in_executor(
                    None, self._model.predict_proba, X
                )
                probability = proba[0].tolist()
            except Exception:
                probability = [1.0, 0.0] if pred[0] == 0 else [0.0, 1.0]

            return {"prediction": int(pred[0]), "probability": probability}

    async def partial_fit(self, features: list, labels: list) -> None:
        self._init_locks()
        async with self._swap_lock:
            if self._model is None:
                raise RuntimeError("Model not loaded")

            X = np.array(features, dtype=np.float64)
            y = np.array(labels, dtype=np.int64)
            loop = asyncio.get_running_loop()

            await loop.run_in_executor(
                None,
                lambda: self._model.partial_fit(X, y, classes=[0, 1]),
            )
            await loop.run_in_executor(
                None, joblib.dump, self._model, settings.model_path
            )
            self._version = datetime.now(timezone.utc).isoformat()

    async def switch_version(self, git_ref: str) -> str:
        self._init_locks()
        previous = self._version
        MODEL_LOADED.set(0)

        async with self._swap_lock:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._run_dvc_pull, git_ref)
            await self.load()

        return previous

    def _run_dvc_pull(self, git_ref: str) -> None:
        subprocess.run(
            ["git", "checkout", git_ref, "--", ".dvc"],
            cwd=settings.git_repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["dvc", "pull", "--force", "--remote", "local"],
            cwd=settings.git_repo_path,
            check=True,
            capture_output=True,
            text=True,
        )

    @property
    def version(self) -> str:
        return self._version

    @property
    def is_loaded(self) -> bool:
        return self._model is not None
