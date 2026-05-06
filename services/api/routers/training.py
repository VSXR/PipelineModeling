import numpy as np
from fastapi import APIRouter, HTTPException

from core.metrics import DATA_DRIFT_SCORE, TRAINING_REQUESTS, TRAINING_SAMPLES
from core.model_manager import ModelManager
from shemas.payloads import TrainingRequest, TrainingResponse

router = APIRouter(prefix="/train", tags=["training"])

_reference_means: list[float] = []


def _emit_drift(features: list[list[float]]) -> None:
    """
    Tracks per-feature drift using an EMA of the reference distribution mean.
    Score is normalised absolute shift: |batch_mean - ref_mean| / (|ref_mean| + eps).
    First batch establishes the reference; no score is emitted on bootstrap.
    """
    global _reference_means
    batch = np.array(features, dtype=np.float64)
    batch_means = batch.mean(axis=0)
    if not _reference_means:
        _reference_means = batch_means.tolist()
        return
    ref = np.array(_reference_means)
    scores = np.abs(batch_means - ref) / (np.abs(ref) + 1e-9)
    for i, score in enumerate(scores):
        DATA_DRIFT_SCORE.labels(feature=f"f{i}").set(float(score))
    _reference_means = (0.95 * ref + 0.05 * batch_means).tolist()


@router.post("/", response_model=TrainingResponse)
async def train(request: TrainingRequest) -> TrainingResponse:
    manager = ModelManager.get_instance()
    try:
        _emit_drift(request.features)
        await manager.partial_fit(request.features, request.labels)
        TRAINING_REQUESTS.labels(status="ok").inc()
        TRAINING_SAMPLES.inc(len(request.labels))
        return TrainingResponse(
            status="ok",
            samples_trained=len(request.labels),
            model_version=manager.version,
        )
    except RuntimeError as exc:
        TRAINING_REQUESTS.labels(status="error").inc()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        TRAINING_REQUESTS.labels(status="error").inc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
