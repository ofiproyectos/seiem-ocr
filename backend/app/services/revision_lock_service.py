from datetime import datetime, timedelta
from secrets import token_hex

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.models import Solicitud, UsuarioRevision
from backend.app.models.revision_audit import RevisionAudit
from backend.app.models.revision_lock import RevisionLock

LOCK_SECONDS = 600
REVIEWABLE_STATES = {"borrador", "pendiente", "en_revision", "revisada"}


def ensure_reviewable(solicitud) -> None:
    if solicitud.estado not in REVIEWABLE_STATES:
        raise HTTPException(status_code=409, detail="El estado de esta solicitud cambio y ya no permite revisarla. Vuelve al panel.")


def sheet_resource(row_number: int) -> str:
    settings = get_settings()
    return f"sheet:{settings.google_sheets_spreadsheet_id}:{settings.google_sheets_sheet_name}:{row_number}"


def solicitud_resource(solicitud) -> str:
    origin = (solicitud.datos or {}).get("origenGoogleSheet") or {}
    return sheet_resource(origin["rowNumber"]) if origin.get("rowNumber") else f"solicitud:{solicitud.id}"


def conflict(db: Session, resource: str) -> HTTPException:
    lock = db.scalar(select(RevisionLock).where(RevisionLock.resource == resource).with_for_update())
    owner = db.scalar(select(UsuarioRevision.nombre).where(UsuarioRevision.username == lock.username)) if lock else None
    name = owner or (lock.username if lock else "otro revisor")
    return HTTPException(status_code=409, detail=f"Esta solicitud esta siendo revisada por {name}. Podras entrar cuando termine o se libere su bloqueo.")


def acquire_review_lock(db: Session, resource: str, username: str, lease: str | None) -> str:
    if not isinstance(lease, str) or not lease.strip() or len(lease) > 120:
        raise HTTPException(status_code=409, detail="Vuelve a abrir la solicitud desde la tabla para obtener el bloqueo de revision.")
    now = datetime.utcnow()
    expires = now + timedelta(seconds=LOCK_SECONDS)
    try:
        # Crear la fila antes de reservar evita competir por huecos de InnoDB.
        if db.scalar(select(RevisionLock.resource).where(RevisionLock.resource == resource)) is None:
            try:
                with db.begin_nested():
                    db.add(RevisionLock(resource=resource, username="", lease="", expires_at=datetime(1970, 1, 1)))
                    db.flush()
            except IntegrityError:
                pass
        db.commit()
        user = db.scalar(select(UsuarioRevision).where(UsuarioRevision.username == username).with_for_update())
        if user is None:
            raise HTTPException(status_code=401, detail="Sesion de revision requerida.")
        owned = list(db.scalars(select(RevisionLock.resource).where(RevisionLock.username == username)))
        rows = list(db.scalars(select(RevisionLock).where(RevisionLock.resource.in_(set(owned + [resource]))).order_by(RevisionLock.resource).with_for_update()))
        now = datetime.utcnow()
        expires = now + timedelta(seconds=LOCK_SECONDS)
        active = next((lock for lock in rows if lock.username == username and lock.expires_at > now), None)
        if active:
            if active.resource != resource or active.browser_session != lease:
                raise HTTPException(status_code=409, detail="Ya tienes una revision activa. Debes continuar en esa pestaña o liberar la solicitud antes de abrir otra.", headers={"X-Revision-Conflict": "active"})
            active.expires_at = expires
            token = active.lease
            db.commit()
            return token
        for lock in rows:
            if lock.username == username and lock.expires_at <= now and lock.resource != resource:
                db.delete(lock)
        db.flush()
        token = token_hex(16)
        values = dict(username=username, lease=token, expires_at=expires, user_id=user.id, acquired_at=now, browser_session=lease)
        result = db.execute(update(RevisionLock).where(RevisionLock.resource == resource, RevisionLock.expires_at <= now).values(**values))
        if result.rowcount == 1:
            db.commit()
            return token
        raise conflict(db, resource)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ya tienes una revision activa. Debes continuar o liberar esa solicitud antes de abrir otra.", headers={"X-Revision-Conflict": "active"}) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="No se pudo reservar la solicitud en la base de datos. Vuelve a intentarlo.") from exc


def require_review_lock(db: Session, solicitud, username: str, lease: str | None) -> None:
    ensure_reviewable(solicitud)
    db.scalar(select(UsuarioRevision).where(UsuarioRevision.username == username).with_for_update())
    resource = solicitud_resource(solicitud)
    result = db.execute(update(RevisionLock).where(
        RevisionLock.resource == resource, RevisionLock.username == username,
        RevisionLock.lease == lease, RevisionLock.expires_at > datetime.utcnow(),
    ).values(expires_at=datetime.utcnow() + timedelta(seconds=LOCK_SECONDS)))
    if result.rowcount != 1:
        raise HTTPException(status_code=409, detail="El bloqueo expiro o ya no pertenece a esta sesion. Vuelve al panel antes de continuar.")


def finish_review(db: Session, solicitud, username: str, token: str | None, values: dict) -> None:
    guard = select(RevisionLock.resource).where(
        RevisionLock.resource == solicitud_resource(solicitud), RevisionLock.username == username,
        RevisionLock.lease == token, RevisionLock.expires_at > datetime.utcnow(),
    ).exists()
    result = db.execute(update(Solicitud).where(Solicitud.id == solicitud.id, Solicitud.estado.in_(REVIEWABLE_STATES), guard).values(**values), execution_options={"synchronize_session": False})
    if result.rowcount != 1:
        raise HTTPException(status_code=409, detail="El bloqueo expiro, cambio el estado o ya no pertenece a esta sesion. Vuelve al panel.")
    db.execute(delete(RevisionLock).where(RevisionLock.resource == solicitud_resource(solicitud), RevisionLock.username == username, RevisionLock.lease == token))
    db.add(RevisionAudit(solicitud_id=solicitud.id, username=username, accion="guardar_revision", campos=list(values)))


def release_review_lock(db: Session, resource: str, username: str, lease: str | None) -> None:
    result = db.execute(delete(RevisionLock).where(RevisionLock.resource == resource, RevisionLock.username == username, RevisionLock.lease == lease))
    db.commit()
    if result.rowcount == 0:
        lock = db.get(RevisionLock, resource, populate_existing=True)
        if lock and lock.expires_at > datetime.utcnow():
            raise HTTPException(status_code=409, detail="No se puede liberar: el bloqueo no pertenece a esta sesion.")


def release_user_locks(db: Session, username: str) -> None:
    db.execute(delete(RevisionLock).where(RevisionLock.username == username))


def cleanup_expired_locks(db: Session, username: str) -> None:
    db.execute(delete(RevisionLock).where(RevisionLock.username == username, RevisionLock.expires_at <= datetime.utcnow()))
    db.commit()


def page_review_locks(db: Session, items: list[dict], username: str) -> None:
    resources = {sheet_resource(item["sheet_row_number"]): item for item in items}
    if not resources:
        return
    rows = db.execute(select(RevisionLock, UsuarioRevision.nombre).outerjoin(
        UsuarioRevision, UsuarioRevision.username == RevisionLock.username,
    ).where(RevisionLock.resource.in_(resources), RevisionLock.expires_at > datetime.utcnow())).all()
    for lock, name in rows:
        resources[lock.resource]["bloqueo"] = {
            "usuario": lock.username, "nombre": name or lock.username, "propio": lock.username == username,
            "desde": lock.acquired_at.isoformat() if lock.acquired_at else None,
            "expira_en": lock.expires_at.isoformat(),
        }
