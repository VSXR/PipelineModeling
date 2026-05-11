import time

from fastapi import APIRouter, HTTPException

from core.drift import DriftTracker
from core.metrics import pipeline_metrics
from core.model_manager import ModelManager
from schemas.inference import InferenceRequest, InferenceResponse

router = APIRouter(prefix="/infer", tags=["inference"])


@router.post("/", response_model=InferenceResponse, summary="Clasificar un tumor")
async def infer(request: InferenceRequest) -> InferenceResponse:
    """
    Clasifica un tumor como **maligno (0)** o **benigno (1)** usando el modelo activo.

    - Requiere un vector de **exactamente 30 features** en el orden del dataset
      Breast Cancer Wisconsin (radius_mean → fractal_dimension_worst).
    - Devuelve la clase predicha, las probabilidades por clase y la versión del modelo.
    - Cada llamada actualiza el buffer del `DriftTracker`; las métricas de drift
      se emiten por OTel cada 50 inferencias acumuladas.

    **Códigos de error:**
    - `503` — modelo no cargado en memoria.
    - `500` — error interno de predicción.
    """
    manager = ModelManager.get_instance()
    t0 = time.perf_counter()
    try:
        result = await manager.predict(request.features)
        latency = time.perf_counter() - t0
        pipeline_metrics.record_inference(status="ok", latency_s=latency)
        DriftTracker().update_single(request.features)
        return InferenceResponse(
            **result,
            model_version=manager.version,
            request_id=request.request_id,
        )
    except RuntimeError as exc:
        pipeline_metrics.record_inference(status="error", latency_s=time.perf_counter() - t0)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        pipeline_metrics.record_inference(status="error", latency_s=time.perf_counter() - t0)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
