from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field, model_validator

_SAMPLE_MALIGNANT = [
    17.99, 10.38, 122.8, 1001.0, 0.1184, 0.2776, 0.3001, 0.1471, 0.2419, 0.07871,
    1.095, 0.9053, 8.589, 153.4, 0.006399, 0.04904, 0.05373, 0.01587, 0.03003, 0.006193,
    25.38, 17.33, 184.6, 2019.0, 0.1622, 0.6656, 0.7119, 0.2654, 0.4601, 0.1189,
]
_SAMPLE_BENIGN = [
    20.57, 17.77, 132.9, 1326.0, 0.08474, 0.07864, 0.0869, 0.07017, 0.1812, 0.05667,
    0.5435, 0.7339, 3.398, 74.08, 0.005225, 0.01308, 0.0186, 0.0134, 0.01389, 0.003532,
    24.99, 23.41, 158.8, 1956.0, 0.1238, 0.1866, 0.2416, 0.186, 0.275, 0.08902,
]


class TrainingRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "features": [_SAMPLE_MALIGNANT, _SAMPLE_BENIGN],
                "labels": [0, 1],
            }
        }
    )

    features: List[List[float]] = Field(
        ...,
        min_length=1,
        description=(
            "Lote de muestras para reentrenamiento. Cada muestra es un vector de "
            "30 features continuas (mismo orden que `/infer/`). "
            "El ejemplo incluye una muestra maligna (0) y una benigna (1)."
        ),
    )
    labels: List[int] = Field(
        ...,
        min_length=1,
        description="Etiquetas correspondientes a cada muestra: **0** = maligno, **1** = benigno.",
    )

    @model_validator(mode="after")
    def _lengths_match(self) -> "TrainingRequest":
        if len(self.features) != len(self.labels):
            raise ValueError("features and labels must have equal length")
        return self


class TrainingResponse(BaseModel):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra={
            "example": {
                "status": "ok",
                "samples_trained": 2,
                "model_version": "v1.0.0",
            }
        },
    )

    status: str = Field(..., description="Resultado de la operación; siempre `\"ok\"` si no hubo error.")
    samples_trained: int = Field(..., description="Número de muestras procesadas por `partial_fit`.")
    model_version: str = Field(..., description="Versión del modelo tras el reentrenamiento.")
