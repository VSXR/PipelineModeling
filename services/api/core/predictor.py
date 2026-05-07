"""
Abstraction layer for ML predictors.

Adding a new model type (XGBoost, HuggingFace, ONNX…) only requires
implementing BasePredictor — ModelManager and all routers stay unchanged.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Tuple

import joblib
import numpy as np
from sklearn.linear_model import SGDClassifier


class BasePredictor(ABC):
    """Contract that every predictor implementation must satisfy."""

    @abstractmethod
    def predict(self, X: np.ndarray) -> Tuple[int, List[float]]:
        """Return (class_label, probability_list) for a single sample."""
        ...

    @abstractmethod
    def partial_fit(self, X: np.ndarray, y: np.ndarray) -> None:
        """Incremental training on a new batch."""
        ...

    @abstractmethod
    def save(self, path: str) -> None:
        """Persist the model to disk."""
        ...

    @classmethod
    @abstractmethod
    def load(cls, path: str) -> "BasePredictor":
        """Restore a saved model from disk."""
        ...

    @classmethod
    @abstractmethod
    def create_default(cls) -> "BasePredictor":
        """Return a new, untrained instance with sensible defaults."""
        ...


class SKLearnPredictor(BasePredictor):
    """
    Wraps a scikit-learn classifier that supports predict_proba and partial_fit.
    Default: SGDClassifier with log-loss (logistic regression via SGD).
    """

    def __init__(self, clf: SGDClassifier) -> None:
        self._clf = clf

    def predict(self, X: np.ndarray) -> Tuple[int, List[float]]:
        pred = self._clf.predict(X)
        try:
            proba = self._clf.predict_proba(X)
            probability = proba[0].tolist()
        except Exception:
            probability = [1.0, 0.0] if pred[0] == 0 else [0.0, 1.0]
        return int(pred[0]), probability

    def partial_fit(self, X: np.ndarray, y: np.ndarray) -> None:
        self._clf.partial_fit(X, y, classes=[0, 1])

    def save(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._clf, path)

    @classmethod
    def load(cls, path: str) -> "SKLearnPredictor":
        return cls(joblib.load(path))

    @classmethod
    def create_default(cls) -> "SKLearnPredictor":
        return cls(SGDClassifier(loss="log_loss", random_state=42))
