from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
