from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SolicitudBase(BaseModel):
    estado: str = "borrador"
    curp: str | None = None
    nombre_completo: str | None = None
    correo_electronico: str | None = None
    datos: dict[str, Any] = Field(default_factory=dict)
    extracciones: list[dict[str, Any]] = Field(default_factory=list)
    notas_operador: str | None = None
    revisado_por: str | None = None
    revisado_at: datetime | None = None


class SolicitudCreate(SolicitudBase):
    pass


class SolicitudUpdate(BaseModel):
    estado: str | None = None
    curp: str | None = None
    nombre_completo: str | None = None
    correo_electronico: str | None = None
    datos: dict[str, Any] | None = None
    extracciones: list[dict[str, Any]] | None = None
    notas_operador: str | None = None


class SolicitudRead(SolicitudBase):
    id: str
    folio: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
