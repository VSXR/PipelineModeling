import asyncio
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import settings
from .metrics import MODEL_LOAD_DURATION, MODEL_LOADED
from .predictor import BasePredictor, SKLearnPredictor


class ModelManager:
    """
    Thread-safe singleton managing the active predictor lifecycle.

    Locking strategy:
      _infer_lock — reader lock; multiple concurrent inference calls allowed.
      _swap_lock  — writer lock; serialises partial_fit and version switches.

    Predictor abstraction: ModelManager depends only on BasePredictor.
    To swap in a different model type (XGBoost, HuggingFace…) it is enough
    to pass a different BasePredictor subclass — no router changes needed.
    """

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

    def _init_locks(self) -> None:
        if not self._initialised:
            self._infer_lock: asyncio.Lock    = asyncio.Lock()
            self._swap_lock:  asyncio.Lock    = asyncio.Lock()
            self._predictor:  Optional[BasePredictor] = None
            self._version:    str             = "unloaded"
            self._initialised = True

    async def _load_weights(self, model_path: Optional[str] = None) -> None:
        path = Path(model_path or settings.model_path)
        loop = asyncio.get_running_loop()
        if path.exists():
            self._predictor = await loop.run_in_executor(
                None, SKLearnPredictor.load, str(path)
            )
        else:
            self._predictor = SKLearnPredictor.create_default()
        self._version = datetime.now(timezone.utc).isoformat()
        MODEL_LOADED.set(1)

    async def load(self, model_path: Optional[str] = None) -> None:
        self._init_locks()
        async with self._swap_lock:
            await self._load_weights(model_path)

    async def predict(self, features: list) -> dict:
        self._init_locks()
        async with self._infer_lock:
            if self._predictor is None:
                raise RuntimeError("Model not loaded")

            import numpy as np
            X    = np.array(features, dtype=np.float64).reshape(1, -1)
            loop = asyncio.get_running_loop()
            prediction, probability = await loop.run_in_executor(
                None, self._predictor.predict, X
            )
            return {"prediction": prediction, "probability": probability}

    async def partial_fit(self, features: list, labels: list) -> None:
        self._init_locks()
        async with self._swap_lock:
            if self._predictor is None:
                raise RuntimeError("Model not loaded")

            import numpy as np
            X    = np.array(features, dtype=np.float64)
            y    = np.array(labels,   dtype=np.int64)
            loop = asyncio.get_running_loop()

            await loop.run_in_executor(None, self._predictor.partial_fit, X, y)
            await loop.run_in_executor(
                None, self._predictor.save, settings.model_path
            )
            self._version = datetime.now(timezone.utc).isoformat()

    async def switch_version(self, git_ref: str) -> str:
        self._init_locks()
        previous = self._version

        async with self._swap_lock:
            MODEL_LOADED.set(0)
            loop = asyncio.get_running_loop()
            t0   = time.perf_counter()
            try:
                await loop.run_in_executor(None, self._run_dvc_pull, git_ref)
                await self._load_weights()
                MODEL_LOAD_DURATION.observe(time.perf_counter() - t0)
            except Exception:
                if self._predictor is not None:
                    MODEL_LOADED.set(1)
                raise

        return previous

    def _run_dvc_pull(self, git_ref: str) -> None:
        subprocess.run(
            ["git", "checkout", git_ref, "--", ".dvc"],
            cwd=settings.git_repo_path, check=True,
            capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "checkout", git_ref, "--", "dvc.lock"],
            cwd=settings.git_repo_path, check=False,
            capture_output=True, text=True,
        )
        subprocess.run(
            ["dvc", "pull", "--force", "--remote", "local"],
            cwd=settings.git_repo_path, check=True,
            capture_output=True, text=True,
        )

    @property
    def version(self) -> str:
        return self._version

    @property
    def is_loaded(self) -> bool:
        return self._predictor is not None
