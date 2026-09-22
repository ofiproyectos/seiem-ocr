from datetime import datetime
from hashlib import pbkdf2_hmac
from hmac import compare_digest
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models import UsuarioRevision

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginPayload(BaseModel):
    username: str
    password: str


def get_current_operator(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sesion de revision requerida.")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Sesion de revision requerida.")
    try:
        usuario = db.scalar(
            select(UsuarioRevision).where(
                UsuarioRevision.session_token == token,
                UsuarioRevision.activo.is_(True),
            )
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="MySQL no esta disponible o la configuracion es incorrecta.") from exc
    if usuario is None:
        raise HTTPException(status_code=401, detail="Sesion de revision requerida.")
    return usuario.username


@router.post("/login")
def login(payload: LoginPayload, db: Session = Depends(get_db)) -> dict:
    try:
        usuario = db.scalar(
            select(UsuarioRevision).where(
                UsuarioRevision.username == payload.username,
                UsuarioRevision.activo.is_(True),
            )
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="MySQL no esta disponible o la configuracion es incorrecta.") from exc

    if usuario is None or not verify_password(payload.password, usuario.password_hash):
        raise HTTPException(status_code=401, detail="Usuario o contrasena incorrectos.")

    usuario.session_token = token_urlsafe(32)
    usuario.ultimo_acceso = datetime.utcnow()
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="MySQL no esta disponible o la configuracion es incorrecta.") from exc
    return {"token": usuario.session_token, "username": usuario.username, "nombre": usuario.nombre, "rol": usuario.rol}


@router.get("/me")
def me(operator: str = Depends(get_current_operator)) -> dict:
    return {"username": operator}


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, stored_hash = password_hash.split("$", 3)
        iterations = int(iterations_text)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    calculated = pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations).hex()
    return compare_digest(calculated, stored_hash)
