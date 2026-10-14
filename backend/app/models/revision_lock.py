from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.session import Base


class RevisionLock(Base):
    __tablename__ = "bloqueos_revision"

    resource: Mapped[str] = mapped_column(String(512), primary_key=True)
    username: Mapped[str] = mapped_column(String(80), nullable=False)
    lease: Mapped[str] = mapped_column("bloqueo_token", String(120), nullable=False)
    expires_at: Mapped[datetime] = mapped_column("bloqueo_expira_en", DateTime, nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column("bloqueado_por", ForeignKey("usuarios_revision.id", ondelete="CASCADE"), nullable=True, unique=True)
    acquired_at: Mapped[datetime | None] = mapped_column("bloqueado_desde", DateTime, nullable=True)
    browser_session: Mapped[str | None] = mapped_column(String(120), nullable=True)
