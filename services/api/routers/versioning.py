from fastapi import APIRouter, HTTPException

from core.metrics import pipeline_metrics
from core.model_manager import ModelManager
from schemas.versioning import (
    VersionCurrentResponse,
    VersionEntry,
    VersionListResponse,
    VersionRegisterResponse,
    VersionSwitchRequest,
    VersionSwitchResponse,
)

router = APIRouter(prefix="/version", tags=["versioning"])


@router.get("/list", response_model=VersionListResponse, summary="Listar versiones registradas en MLflow")
async def list_versions() -> VersionListResponse:
    """
    Devuelve todas las versiones registradas en el MLflow Model Registry para el modelo configurado,
    ordenadas de mayor a menor número de versión.

    Responde con lista vacía si MLflow no está disponible o el modelo no tiene versiones registradas.
    """
    from datetime import datetime

    import mlflow
    from mlflow import MlflowClient

    from core.config import settings

    client = MlflowClient(tracking_uri=settings.mlflow_tracking_uri)
    model_name = settings.mlflow_model_name
    try:
        mvs = client.search_model_versions(f"name='{model_name}'")
    except Exception:
        return VersionListResponse(versions=[], model_name=model_name)

    def _sort_key(mv):
        try:
            return int(mv.version)
        except (ValueError, TypeError):
            return 0

    entries = [
        VersionEntry(
            version=str(mv.version),
            aliases=list(getattr(mv, "aliases", [])),
            status=str(mv.current_stage),
            created_at=datetime.fromtimestamp(mv.creation_timestamp / 1000).isoformat(),
            run_id=mv.run_id or None,
            description=mv.description or "",
        )
        for mv in sorted(mvs, key=_sort_key, reverse=True)
    ]
    return VersionListResponse(versions=entries, model_name=model_name)


@router.post("/register", response_model=VersionRegisterResponse, summary="Registrar modelo activo en MLflow")
async def register_version() -> VersionRegisterResponse:
    """
    Registra el modelo actualmente en memoria en el MLflow Model Registry.

    Carga el artefacto desde disco (`model.pkl`), abre un nuevo run en MLflow,
    y registra el modelo como una nueva versión bajo el nombre configurado
    en `MLFLOW_MODEL_NAME`.

    Útil para promover un modelo entrenado incrementalmente a MLflow sin
    reiniciar el servicio.

    **Código de error:**
    - `500` — modelo no persistido aún en disco o MLflow no disponible.
    """
    manager = ModelManager.get_instance()
    try:
        version = await manager.register_to_mlflow()
        return VersionRegisterResponse(status="ok", mlflow_version=version)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Registration failed: {exc}",
        ) from exc


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
