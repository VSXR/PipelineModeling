import time

from fastapi import APIRouter, HTTPException

from core.metrics import INFERENCE_LATENCY, INFERENCE_REQUESTS
from core.model_manager import ModelManager
from schemas.inference import InferenceRequest, InferenceResponse

router = APIRouter(prefix="/infer", tags=["inference"])


@router.post("/", response_model=InferenceResponse)
async def infer(request: InferenceRequest) -> InferenceResponse:
    manager = ModelManager.get_instance()
    t0 = time.perf_counter()
    try:
        result = await manager.predict(request.features)
        INFERENCE_REQUESTS.labels(status="ok").inc()
        INFERENCE_LATENCY.observe(time.perf_counter() - t0)
        return InferenceResponse(
            **result,
            model_version=manager.version,
            request_id=request.request_id,
        )
    except RuntimeError as exc:
        INFERENCE_REQUESTS.labels(status="error").inc()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        INFERENCE_REQUESTS.labels(status="error").inc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
