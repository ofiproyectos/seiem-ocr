from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from sqlalchemy import text

from backend.app.api import auth, codigos_postales, extracciones, health, solicitudes
from backend.app.db.session import Base, engine
from backend.app.models import Solicitud

app = FastAPI(title="SEIEM Filiacion OCR")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(extracciones.router, prefix="/api")
app.include_router(solicitudes.router, prefix="/api")
app.include_router(codigos_postales.router, prefix="/api")


@app.on_event("startup")
def init_database() -> None:
    try:
        Base.metadata.create_all(bind=engine)
        ensure_runtime_columns()
    except SQLAlchemyError as exc:
        print(f"No se pudo inicializar MySQL: {exc}")


def ensure_runtime_columns() -> None:
    statements = [
        "ALTER TABLE solicitudes ADD COLUMN revisado_por VARCHAR(80) NULL",
        "ALTER TABLE solicitudes ADD COLUMN revisado_at DATETIME NULL",
        "ALTER TABLE bloqueos_revision ADD COLUMN bloqueado_por INT NULL",
        "ALTER TABLE bloqueos_revision ADD COLUMN bloqueado_desde DATETIME NULL",
        "ALTER TABLE bloqueos_revision ADD COLUMN browser_session VARCHAR(120) NULL",
        "ALTER TABLE bloqueos_revision CHANGE COLUMN lease bloqueo_token VARCHAR(120) NOT NULL",
        "ALTER TABLE bloqueos_revision CHANGE COLUMN expires_at bloqueo_expira_en DATETIME NOT NULL",
        "CREATE UNIQUE INDEX ux_bloqueo_usuario ON bloqueos_revision (bloqueado_por)",
        "ALTER TABLE bloqueos_revision ADD CONSTRAINT fk_bloqueo_usuario FOREIGN KEY (bloqueado_por) REFERENCES usuarios_revision(id) ON DELETE CASCADE",
    ]
    with engine.begin() as connection:
        for statement in statements:
            try:
                connection.execute(text(statement))
            except SQLAlchemyError:
                pass
