from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from core.config import settings
from core.model_manager import ModelManager
from routers import inference, training, versioning


@asynccontextmanager
async def lifespan(app: FastAPI):
    manager = ModelManager.get_instance()
    await manager.load()
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
)

Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    should_respect_env_var=False,
    should_instrument_requests_inprogress=True,
    excluded_handlers=["/metrics", "/health"],
    inprogress_name="http_requests_inprogress",
    inprogress_labels=True,
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

app.include_router(inference.router)
app.include_router(training.router)
app.include_router(versioning.router)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    manager = ModelManager.get_instance()
    return {
        "status": "ok",
        "model_loaded": manager.is_loaded,
        "model_version": manager.version,
    }
