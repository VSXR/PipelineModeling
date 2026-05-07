from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class VersionSwitchRequest(BaseModel):
    git_ref: str = Field(..., min_length=1)


class VersionSwitchResponse(BaseModel):
    status: str
    previous_version: str
    current_version: str


class VersionCurrentResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    version: str
    model_loaded: bool
