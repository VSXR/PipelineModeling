from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InferenceRequest(BaseModel):
    features: List[float] = Field(..., min_length=1)
    request_id: Optional[str] = None


class InferenceResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    prediction: int
    probability: List[float]
    model_version: str
    request_id: Optional[str] = None


class TrainingRequest(BaseModel):
    features: List[List[float]] = Field(..., min_length=1)
    labels: List[int] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _lengths_match(self) -> "TrainingRequest":
        if len(self.features) != len(self.labels):
            raise ValueError("features and labels must have equal length")
        return self


class TrainingResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    status: str
    samples_trained: int
    model_version: str


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
