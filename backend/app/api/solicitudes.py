from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.auth import get_current_operator
from backend.app.db.session import get_db
from backend.app.models import Solicitud
from backend.app.schemas.solicitud import SolicitudCreate, SolicitudRead, SolicitudUpdate
from backend.app.services.excel_service import exportar_filiacion_excel
from backend.app.services.revision_lock_service import (
    acquire_review_lock, cleanup_expired_locks, ensure_reviewable, finish_review, page_review_locks,
    release_review_lock, require_review_lock, sheet_resource, solicitud_resource,
)
from backend.app.services.spreadsheet_service import SpreadsheetConfigError, list_sheet_requests, list_sheet_requests_page, restore_complete_sheet_addresses, update_sheet_request_from_solicitud

router = APIRouter(prefix="/solicitudes", tags=["solicitudes"])


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


@router.get("/google-sheet")
def listar_solicitudes_google_sheet(
    operator: str = Depends(get_current_operator),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    query: str = Query("", max_length=200),
    refresh: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    try:
        cleanup_expired_locks(db, operator)
        result = list_sheet_requests_page(page, page_size, query, refresh)
        page_review_locks(db, result["items"], operator)
        return result
    except SpreadsheetConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"No se pudo leer Google Sheets: {exc}") from exc


@router.get("/google-sheet/bloqueos")
def listar_bloqueos(
    rows: list[int] = Query(default=[]), db: Session = Depends(get_db), operator: str = Depends(get_current_operator),
) -> dict:
    if len(rows) > 100 or any(row < 2 for row in rows):
        raise HTTPException(status_code=400, detail="Lista de filas no valida.")
    items = [{"sheet_row_number": row} for row in rows]
    page_review_locks(db, items, operator)
    return {str(item["sheet_row_number"]): item.get("bloqueo") for item in items}


@router.post("/google-sheet/{row_number}/importar", response_model=SolicitudRead)
def importar_solicitud_google_sheet(
    row_number: int,
    db: Session = Depends(get_db),
    operator: str = Depends(get_current_operator),
    lease: str | None = Header(default=None, alias="X-Revision-Lease"),
) -> Solicitud:
    try:
        sheet_requests = list_sheet_requests()
    except SpreadsheetConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"No se pudo leer Google Sheets: {exc}") from exc

    sheet_request = next((item for item in sheet_requests if item.get("sheet_row_number") == row_number), None)
    if sheet_request is None:
        raise HTTPException(status_code=404, detail="Fila de Google Sheets no encontrada.")
    lock_token = acquire_review_lock(db, sheet_resource(row_number), operator, lease)

    try:
        existing_requests = db.scalars(select(Solicitud).order_by(Solicitud.created_at.desc())).all()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="MySQL no esta disponible o la configuracion es incorrecta.") from exc
    for existing in existing_requests:
        origin = (existing.datos or {}).get("origenGoogleSheet") or {}
        if origin.get("rowNumber") == row_number:
            try:
                ensure_reviewable(existing)
            except HTTPException:
                release_review_lock(db, sheet_resource(row_number), operator, lock_token)
                raise
            existing.datos = restore_complete_sheet_addresses(existing.datos or {}, sheet_request.get("datos") or {})
            existing.revision_token = lock_token
            return existing

    solicitud = Solicitud(
        estado="en_revision",
        nombre_completo=sheet_request.get("nombre_completo"),
        correo_electronico=sheet_request.get("correo_electronico"),
        datos=sheet_request.get("datos") or {},
        extracciones=[],
        revisado_por=operator,
        revisado_at=datetime.utcnow(),
    )
    db.add(solicitud)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="MySQL no esta disponible o la configuracion es incorrecta.") from exc
    db.refresh(solicitud)
    solicitud.revision_token = lock_token
    return solicitud


@router.get("/{solicitud_id}", response_model=SolicitudRead)
def obtener_solicitud(
    solicitud_id: str, db: Session = Depends(get_db), operator: str = Depends(get_current_operator),
    lease: str | None = Header(default=None, alias="X-Revision-Lease"),
) -> Solicitud:
    try:
        solicitud = db.get(Solicitud, solicitud_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="MySQL no esta disponible o la configuracion es incorrecta.") from exc
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada.")
    ensure_reviewable(solicitud)
    lock_token = acquire_review_lock(db, solicitud_resource(solicitud), operator, lease)
    db.refresh(solicitud)
    datos = solicitud.datos or {}
    row_number = (datos.get("origenGoogleSheet") or {}).get("rowNumber")
    addresses = [datos.get("domicilio")] + [r.get("domicilio") for r in datos.get("referencias") or []]
    if row_number and any(isinstance(address, dict) and "completo" not in address for address in addresses):
        try:
            source = next((item for item in list_sheet_requests() if item.get("sheet_row_number") == row_number), None)
            if source:
                solicitud.datos = restore_complete_sheet_addresses(datos, source.get("datos") or {})
        except Exception as exc:
            raise HTTPException(status_code=503, detail="No se pudo recuperar el domicilio completo de Google Sheets. Vuelve a abrir la solicitud.") from exc
    solicitud.revision_token = lock_token
    return solicitud


@router.post("/{solicitud_id}/bloqueo")
def renovar_bloqueo(
    solicitud_id: str, db: Session = Depends(get_db), operator: str = Depends(get_current_operator),
    lease: str | None = Header(default=None, alias="X-Revision-Token"),
) -> dict:
    solicitud = db.get(Solicitud, solicitud_id)
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada.")
    require_review_lock(db, solicitud, operator, lease)
    db.commit()
    return {"renovado": True}


@router.delete("/{solicitud_id}/bloqueo", status_code=204)
def liberar_bloqueo(
    solicitud_id: str, db: Session = Depends(get_db), operator: str = Depends(get_current_operator),
    lease: str | None = Header(default=None, alias="X-Revision-Token"),
) -> Response:
    solicitud = db.get(Solicitud, solicitud_id)
    if solicitud:
        release_review_lock(db, solicitud_resource(solicitud), operator, lease)
    return Response(status_code=204)


@router.get("/{solicitud_id}/excel")
def descargar_excel(
    solicitud_id: str,
    db: Session = Depends(get_db),
    operator: str = Depends(get_current_operator),
    lease: str | None = Header(default=None, alias="X-Revision-Token"),
) -> FileResponse:
    solicitud = db.get(Solicitud, solicitud_id)
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada.")
    require_review_lock(db, solicitud, operator, lease)
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


@router.post("/{solicitud_id}/excel")
def descargar_excel_con_datos_actuales(
    solicitud_id: str,
    payload: SolicitudUpdate,
    db: Session = Depends(get_db),
    operator: str = Depends(get_current_operator),
    lease: str | None = Header(default=None, alias="X-Revision-Token"),
) -> FileResponse:
    solicitud = db.get(Solicitud, solicitud_id)
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada.")
    require_review_lock(db, solicitud, operator, lease)
    datos = payload.datos if payload.datos is not None else solicitud.datos or {}
    try:
        path = exportar_filiacion_excel(solicitud.id, datos)
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
    lease: str | None = Header(default=None, alias="X-Revision-Token"),
) -> Solicitud:
    solicitud = db.get(Solicitud, solicitud_id)
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada.")
    require_review_lock(db, solicitud, operator, lease)

    origin = (solicitud.datos or {}).get("origenGoogleSheet")
    values = payload.model_dump(exclude_unset=True)
    if "datos" in values and origin:
        values["datos"] = {**(values["datos"] or {}), "origenGoogleSheet": origin}
    if values.get("estado") not in (None, "revisada"):
        raise HTTPException(status_code=400, detail="El estado de guardado de revision no es valido.")
    values.update(estado="revisada", revisado_por=operator, revisado_at=datetime.utcnow())

    try:
        finish_review(db, solicitud, operator, lease, values)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="MySQL no esta disponible o la configuracion es incorrecta.") from exc
    db.refresh(solicitud)
    try:
        update_sheet_request_from_solicitud(solicitud)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="La revision se guardo en la base de datos, pero no se pudo actualizar Google Sheets. "
                   "Tus cambios estan conservados. Vuelve al panel, abre la solicitud y guarda de nuevo para reenviarlos.",
            headers={"X-Revision-Released": "true"},
        ) from exc
    return solicitud
