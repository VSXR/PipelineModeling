"""
Debug / chaos-engineering router.
Only mounted when ENABLE_DEBUG_ENDPOINTS=true.
Never deploy this with ENABLE_DEBUG_ENDPOINTS=true in production.
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.model_manager import chaos_state

router = APIRouter(prefix="/debug", tags=["debug"])


class ChaosConfig(BaseModel):
    inference_error_rate: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Fracción de inferencias que fallarán con RuntimeError (0.0 = desactivado, 1.0 = 100% de errores).",
    )

    model_config = {
        "json_schema_extra": {"example": {"inference_error_rate": 0.20}}
    }


@router.post(
    "/chaos",
    summary="[DEV] Activar chaos engineering",
    description=(
        "Inyecta errores aleatorios en el endpoint de inferencia para simular la alerta "
        "`HighInferenceErrorRate`. Solo disponible cuando `ENABLE_DEBUG_ENDPOINTS=true`."
    ),
)
async def set_chaos(config: ChaosConfig) -> dict:
    chaos_state["inference_error_rate"] = config.inference_error_rate
    return {"status": "ok", "chaos_state": dict(chaos_state)}


@router.post(
    "/chaos/reset",
    summary="[DEV] Resetear chaos engineering",
    description="Desactiva todos los fallos inyectados y restaura el comportamiento normal.",
)
async def reset_chaos() -> dict:
    chaos_state["inference_error_rate"] = 0.0
    return {"status": "ok", "chaos_state": dict(chaos_state)}


@router.get(
    "/chaos",
    summary="[DEV] Estado actual del chaos engineering",
)
async def get_chaos() -> dict:
    return {"chaos_state": dict(chaos_state)}
