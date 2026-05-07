from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class InferenceRequest(BaseModel):
    features: List[float] = Field(..., min_length=1)
    request_id: Optional[str] = None


class InferenceResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    prediction: int
    probability: List[float]
    model_version: str
    request_id: Optional[str] = None
