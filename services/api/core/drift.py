"""
Shared drift tracker used by both /infer/ and /train/ routers.

Strategy:
  - /train/ calls update_batch()  → immediate EMA update on labeled batches.
  - /infer/ calls update_single() → accumulates samples in a rolling window;
    emits drift scores every INFER_WINDOW calls to avoid per-request overhead.

The EMA formula per feature i:
    score_i  = |batch_mean_i - ref_mean_i| / (|ref_mean_i| + eps)
    ref_mean = 0.95 * ref_mean + 0.05 * batch_mean
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np

from .metrics import pipeline_metrics

# Short names used as OTel attribute values (must be stable across restarts)
FEATURE_NAMES: List[str] = [
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

_EMA_ALPHA    = 0.05   # weight of new batch in the EMA update
_INFER_WINDOW = 50     # emit inference drift every N single-sample calls
_EPS          = 1e-9


class DriftTracker:
    """
    Singleton that maintains the per-feature EMA reference and emits
    pipeline.data.drift_score metrics via OTel.
    """

    _instance: Optional["DriftTracker"] = None

    def __new__(cls) -> "DriftTracker":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._ref_means: List[float] = []
            cls._instance._infer_buffer: List[List[float]] = []
        return cls._instance

    def update_batch(self, features: List[List[float]]) -> None:
        """Called by /train/: update EMA immediately from a labeled batch."""
        if not features:
            return
        self._update_ema(np.array(features, dtype=np.float64))

    def update_single(self, feature_vector: List[float]) -> None:
        """Called by /infer/: buffer single samples, emit every INFER_WINDOW."""
        self._infer_buffer.append(feature_vector)
        if len(self._infer_buffer) >= _INFER_WINDOW:
            batch = np.array(self._infer_buffer, dtype=np.float64)
            self._infer_buffer.clear()
            self._update_ema(batch)

    def _update_ema(self, batch: np.ndarray) -> None:
        batch_means = batch.mean(axis=0)
        n = len(batch_means)

        if not self._ref_means:
            self._ref_means = batch_means.tolist()
            return

        ref = np.array(self._ref_means[:n])
        scores = np.abs(batch_means - ref) / (np.abs(ref) + _EPS)

        feat_labels = FEATURE_NAMES if len(FEATURE_NAMES) >= n else [f"f{i}" for i in range(n)]
        for i, score in enumerate(scores):
            pipeline_metrics.set_drift_score(feat_labels[i], float(score))

        self._ref_means = (
            (1 - _EMA_ALPHA) * ref + _EMA_ALPHA * batch_means
        ).tolist()
