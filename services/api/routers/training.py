from fastapi import APIRouter, HTTPException

from core.drift import DriftTracker
from core.metrics import TRAINING_REQUESTS, TRAINING_SAMPLES
from core.model_manager import ModelManager
from schemas.training import TrainingRequest, TrainingResponse

router = APIRouter(prefix="/train", tags=["training"])


@router.post("/", response_model=TrainingResponse)
async def train(request: TrainingRequest) -> TrainingResponse:
    manager = ModelManager.get_instance()
    try:
        DriftTracker().update_batch(request.features)
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
