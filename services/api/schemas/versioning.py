from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class VersionSwitchRequest(BaseModel):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra={"example": {"model_ref": "Production"}},
    )

    model_ref: str = Field(
        ...,
        min_length=1,
        description=(
            "Referencia del modelo en MLflow Model Registry: número de versión (`1`, `2`) "
            "o alias (`Production`, `Staging`)."
        ),
        examples=["Production", "Staging", "1", "2"],
    )


class VersionSwitchResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "previous_version": "1",
                "current_version": "Production",
            }
        }
    )

    status: str = Field(..., description="Resultado del cambio de versión; siempre `\"ok\"` si tuvo éxito.")
    previous_version: str = Field(..., description="Versión activa antes del switch.")
    current_version: str = Field(..., description="Versión activa después del switch.")


class VersionRegisterResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"status": "ok", "mlflow_version": "2"}
        }
    )

    status: str = Field(..., description="Siempre `\"ok\"` si el registro tuvo éxito.")
    mlflow_version: str = Field(..., description="Número de versión asignado por MLflow Model Registry.")


class VersionCurrentResponse(BaseModel):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra={
            "example": {
                "version": "Production",
                "model_loaded": True,
            }
        },
    )

    version: str = Field(..., description="Versión MLflow / timestamp del modelo actualmente en memoria.")
    model_loaded: bool = Field(..., description="`true` si hay un modelo cargado y listo para inferir.")
