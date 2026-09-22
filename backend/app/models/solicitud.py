from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.session import Base


class Solicitud(Base):
    __tablename__ = "solicitudes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    folio: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True)
    estado: Mapped[str] = mapped_column(String(30), default="borrador", index=True)
    curp: Mapped[str | None] = mapped_column(String(18), index=True, nullable=True)
    nombre_completo: Mapped[str | None] = mapped_column(String(220), nullable=True)
    correo_electronico: Mapped[str | None] = mapped_column(String(180), nullable=True)
    datos: Mapped[dict] = mapped_column(JSON, default=dict)
    extracciones: Mapped[list] = mapped_column(JSON, default=list)
    notas_operador: Mapped[str | None] = mapped_column(Text, nullable=True)
    revisado_por: Mapped[str | None] = mapped_column(String(80), nullable=True)
    revisado_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
