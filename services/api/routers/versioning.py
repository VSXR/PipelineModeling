from fastapi import APIRouter, HTTPException

from core.metrics import pipeline_metrics
from core.model_manager import ModelManager
from schemas.versioning import (
    VersionCurrentResponse,
    VersionSwitchRequest,
    VersionSwitchResponse,
)

router = APIRouter(prefix="/version", tags=["versioning"])


@router.get("/current", response_model=VersionCurrentResponse, summary="Versión activa del modelo")
async def current_version() -> VersionCurrentResponse:
    """
    Devuelve la versión del modelo actualmente cargado en memoria.

    - **version** — número de versión MLflow o timestamp si el modelo fue cargado localmente.
    - **model_loaded** — `false` si el servicio arrancó pero aún no cargó el modelo.
    """
    manager = ModelManager.get_instance()
    return VersionCurrentResponse(
        version=manager.version,
        model_loaded=manager.is_loaded,
    )


@router.post("/switch", response_model=VersionSwitchResponse, summary="Hot-swap de versión de modelo")
async def switch_version(request: VersionSwitchRequest) -> VersionSwitchResponse:
    """
    Cambia el modelo activo en caliente sin reiniciar el servicio.

    Flujo interno:
    1. Descarga el artefacto del MLflow Model Registry usando `model_ref`.
    2. Recarga el modelo en memoria con `joblib`.

    El tiempo de carga se registra en la métrica `pipeline.model.load_duration_seconds`.

    **Valores válidos para `model_ref`:** número de versión (`1`, `2`), alias (`Production`, `Staging`).

    **Código de error:**
    - `500` — versión no encontrada en el registro MLflow.
    """
    manager = ModelManager.get_instance()
    try:
        previous = await manager.switch_version(request.model_ref)
        return VersionSwitchResponse(
            status="ok",
            previous_version=previous,
            current_version=manager.version,
        )
    except Exception as exc:
        pipeline_metrics.record_version_switch(status="error")
        raise HTTPException(
            status_code=500,
            detail=f"Version switch failed: {exc}",
        ) from exc
