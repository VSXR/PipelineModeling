from fastapi import APIRouter, HTTPException

from core.drift import DriftTracker
from core.metrics import pipeline_metrics
from core.model_manager import ModelManager
from schemas.training import TrainingRequest, TrainingResponse

router = APIRouter(prefix="/train", tags=["training"])


@router.post("/", response_model=TrainingResponse, summary="Reentrenamiento incremental")
async def train(request: TrainingRequest) -> TrainingResponse:
    """
    Actualiza el modelo activo con nuevas muestras etiquetadas usando `partial_fit`.

    - Acepta **uno o más** vectores de 30 features con sus etiquetas correspondientes.
    - El modelo se actualiza **en memoria** y se persiste en disco (`model.pkl`).
    - También actualiza la referencia EMA del `DriftTracker` con el lote recibido.
    - El servicio no se interrumpe: las inferencias siguen disponibles durante el entrenamiento.

    **Códigos de error:**
    - `503` — modelo no cargado en memoria.
    - `500` — error durante `partial_fit`.
    """
    manager = ModelManager.get_instance()
    try:
        DriftTracker().update_batch(request.features)
        await manager.partial_fit(request.features, request.labels)
        pipeline_metrics.record_training(status="ok", n_samples=len(request.labels))
        return TrainingResponse(
            status="ok",
            samples_trained=len(request.labels),
            model_version=manager.version,
        )
    except RuntimeError as exc:
        pipeline_metrics.record_training(status="error")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        pipeline_metrics.record_training(status="error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
