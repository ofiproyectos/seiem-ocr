from datetime import datetime
from logging import getLogger

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.auth import get_current_operator
from backend.app.db.session import get_db
from backend.app.models import Solicitud
from backend.app.schemas.solicitud import SolicitudCreate, SolicitudRead, SolicitudUpdate
from backend.app.services.excel_service import exportar_filiacion_excel
from backend.app.services.spreadsheet_service import append_review_to_spreadsheet

router = APIRouter(prefix="/solicitudes", tags=["solicitudes"])
logger = getLogger(__name__)


@router.post("", response_model=SolicitudRead)
def crear_solicitud(payload: SolicitudCreate, db: Session = Depends(get_db)) -> Solicitud:
    solicitud = Solicitud(**payload.model_dump())
    db.add(solicitud)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="MySQL no esta disponible o la configuracion es incorrecta.") from exc
    db.refresh(solicitud)
    return solicitud


@router.get("", response_model=list[SolicitudRead])
def listar_solicitudes(
    db: Session = Depends(get_db), operator: str = Depends(get_current_operator)
) -> list[Solicitud]:
    try:
        return list(db.scalars(select(Solicitud).order_by(Solicitud.created_at.desc()).limit(50)))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="MySQL no esta disponible o la configuracion es incorrecta.") from exc


@router.get("/{solicitud_id}", response_model=SolicitudRead)
def obtener_solicitud(
    solicitud_id: str, db: Session = Depends(get_db), operator: str = Depends(get_current_operator)
) -> Solicitud:
    try:
        solicitud = db.get(Solicitud, solicitud_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="MySQL no esta disponible o la configuracion es incorrecta.") from exc
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada.")
    return solicitud


@router.get("/{solicitud_id}/excel")
def descargar_excel(
    solicitud_id: str,
    db: Session = Depends(get_db),
    operator: str = Depends(get_current_operator),
) -> FileResponse:
    solicitud = db.get(Solicitud, solicitud_id)
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada.")
    try:
        path = exportar_filiacion_excel(solicitud.id, solicitud.datos or {})
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo generar el Excel: {exc}") from exc
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.put("/{solicitud_id}", response_model=SolicitudRead)
def actualizar_solicitud(
    solicitud_id: str,
    payload: SolicitudUpdate,
    db: Session = Depends(get_db),
    operator: str = Depends(get_current_operator),
) -> Solicitud:
    solicitud = db.get(Solicitud, solicitud_id)
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(solicitud, field, value)
    solicitud.revisado_por = operator
    solicitud.revisado_at = datetime.utcnow()

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="MySQL no esta disponible o la configuracion es incorrecta.") from exc
    db.refresh(solicitud)
    if solicitud.estado == "revisada":
        try:
            append_review_to_spreadsheet(solicitud)
        except Exception as exc:
            logger.warning("No se pudo enviar la revision a Google Sheets: %s", exc)
    return solicitud
