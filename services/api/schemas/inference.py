from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

_SAMPLE_MALIGNANT = [
    17.99, 10.38, 122.8, 1001.0, 0.1184, 0.2776, 0.3001, 0.1471, 0.2419, 0.07871,
    1.095, 0.9053, 8.589, 153.4, 0.006399, 0.04904, 0.05373, 0.01587, 0.03003, 0.006193,
    25.38, 17.33, 184.6, 2019.0, 0.1622, 0.6656, 0.7119, 0.2654, 0.4601, 0.1189,
]


class InferenceRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "features": _SAMPLE_MALIGNANT,
                "request_id": "req-001",
            }
        }
    )

    features: List[float] = Field(
        ...,
        min_length=30,
        max_length=30,
        description=(
            "Vector de 30 features continuas del dataset Breast Cancer Wisconsin "
            "(radius_mean, texture_mean, …, fractal_dimension_worst). "
            "El ejemplo corresponde a la muestra #0 del dataset (maligno, clase 0)."
        ),
    )
    request_id: Optional[str] = Field(
        None,
        description="Identificador opcional del cliente; se devuelve sin modificar en la respuesta.",
        examples=["req-001"],
    )


class InferenceResponse(BaseModel):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra={
            "example": {
                "prediction": 0,
                "probability": [1.0, 0.0],
                "model_version": "v1.0.0",
                "request_id": "req-001",
            }
        },
    )

    prediction: int = Field(
        ...,
        description="Clase predicha: **0** = maligno, **1** = benigno.",
    )
    probability: List[float] = Field(
        ...,
        description="Probabilidades [P(maligno), P(benigno)] sumando 1.0.",
    )
    model_version: str = Field(
        ...,
        description="Versión del modelo que generó la predicción.",
    )
    request_id: Optional[str] = Field(
        None,
        description="Identificador del cliente tal como fue recibido.",
    )
