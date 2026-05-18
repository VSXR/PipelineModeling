from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore[import]
from pydantic import BaseModel, ConfigDict

from core.config import settings
from core.model_manager import ModelManager
from routers import debug, inference, training, versioning

_DESCRIPTION = """
Pipeline de ML continuo sobre el dataset **Breast Cancer Wisconsin (Diagnostic)**.

## Endpoints

| Tag | Ruta | Descripción |
|---|---|---|
| **inference** | `POST /infer/` | Clasifica un tumor: 0 = maligno, 1 = benigno |
| **training** | `POST /train/` | Reentrenamiento incremental (`partial_fit`) |
| **versioning** | `GET /version/current` | Versión activa del modelo |
| **versioning** | `POST /version/switch` | Hot-swap sin reiniciar el servicio |
| **ops** | `GET /health` | Estado del servicio y modelo |

## Dataset

- **569 muestras** · **30 features continuas** · target binario (0 = maligno, 1 = benigno)
- Features: `radius_mean`, `texture_mean`, …, `fractal_dimension_worst`
- Modelo: `SGDClassifier(loss="log_loss")` con soporte `partial_fit`

## Drift

Cada inferencia actualiza el `DriftTracker` (EMA α=0.05).
Las métricas `pipeline.data.drift_score` se emiten por OTel cada 50 muestras.
"""

_TAGS = [
    {
        "name": "inference",
        "description": "Predicción sobre el modelo activo. Devuelve clase (0/1) y probabilidades.",
    },
    {
        "name": "training",
        "description": (
            "Reentrenamiento incremental. Acepta lotes de muestras etiquetadas y llama "
            "`partial_fit` sobre el modelo en memoria sin reiniciar el servicio."
        ),
    },
    {
        "name": "versioning",
        "description": (
            "Gestión de versiones vía MLflow Model Registry. Permite inspeccionar la versión activa "
            "o cambiarla en caliente via `model_ref` (número de versión o alias: Production, Staging)."
        ),
    },
    {
        "name": "ops",
        "description": "Health check y estado operacional del servicio.",
    },
]


class HealthResponse(BaseModel):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra={
            "example": {
                "status": "ok",
                "model_loaded": True,
                "model_version": "v1.0.0",
            }
        },
    )

    status: str
    model_loaded: bool
    model_version: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    manager = ModelManager.get_instance()
    await manager.load()
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=_DESCRIPTION,
    openapi_tags=_TAGS,
    lifespan=lifespan,
)

FastAPIInstrumentor.instrument_app(app, excluded_urls="/health")

app.include_router(inference.router)
app.include_router(training.router)
app.include_router(versioning.router)
app.include_router(debug.router)


@app.get(
    "/health",
    tags=["ops"],
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse}},
    summary="Estado del servicio",
)
async def health() -> JSONResponse:
    manager = ModelManager.get_instance()
    loaded = manager.is_loaded
    return JSONResponse(
        content=HealthResponse(
            status="ok" if loaded else "unavailable",
            model_loaded=loaded,
            model_version=manager.version,
        ).model_dump(),
        status_code=200 if loaded else 503,
    )

