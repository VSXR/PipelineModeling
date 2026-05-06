from fastapi import APIRouter, HTTPException

from core.metrics import VERSION_SWITCHES
from core.model_manager import ModelManager
from shemas.payloads import (
    VersionCurrentResponse,
    VersionSwitchRequest,
    VersionSwitchResponse,
)

router = APIRouter(prefix="/version", tags=["versioning"])


@router.get("/current", response_model=VersionCurrentResponse)
async def current_version() -> VersionCurrentResponse:
    manager = ModelManager.get_instance()
    return VersionCurrentResponse(
        version=manager.version,
        model_loaded=manager.is_loaded,
    )


@router.post("/switch", response_model=VersionSwitchResponse)
async def switch_version(request: VersionSwitchRequest) -> VersionSwitchResponse:
    manager = ModelManager.get_instance()
    try:
        previous = await manager.switch_version(request.git_ref)
        VERSION_SWITCHES.labels(status="ok").inc()
        return VersionSwitchResponse(
            status="ok",
            previous_version=previous,
            current_version=manager.version,
        )
    except Exception as exc:
        VERSION_SWITCHES.labels(status="error").inc()
        raise HTTPException(
            status_code=500,
            detail=f"Version switch failed: {exc}",
        ) from exc
