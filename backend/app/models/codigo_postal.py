from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.session import Base


class CodigoPostal(Base):
    __tablename__ = "codigos_postales"
    __table_args__ = (
        Index("idx_codigos_postales_cp", "cp"),
        Index("idx_codigos_postales_cp_asentamiento", "cp", "asentamiento"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cp: Mapped[str] = mapped_column(String(5), nullable=False)
    asentamiento: Mapped[str] = mapped_column(String(160), nullable=False)
    tipo_asentamiento: Mapped[str | None] = mapped_column(String(80), nullable=True)
    municipio: Mapped[str] = mapped_column(String(120), nullable=False)
    estado: Mapped[str] = mapped_column(String(120), nullable=False)
    ciudad: Mapped[str | None] = mapped_column(String(120), nullable=True)
