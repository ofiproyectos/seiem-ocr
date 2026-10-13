from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models import CodigoPostal

router = APIRouter(prefix="/codigos-postales", tags=["codigos-postales"])


@router.get("/{cp}")
def buscar_codigo_postal(cp: str, db: Session = Depends(get_db)) -> dict:
    if not cp.isdigit() or len(cp) != 5:
        raise HTTPException(status_code=400, detail="El codigo postal debe tener 5 digitos.")

    try:
        rows = list(
            db.scalars(
                select(CodigoPostal)
                .where(CodigoPostal.cp == cp)
                .order_by(CodigoPostal.asentamiento.asc())
            )
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Catalogo de codigos postales no disponible.") from exc

    return {
        "cp": cp,
        "opciones": [
            {
                "asentamiento": row.asentamiento,
                "municipio": row.municipio,
                "estado": row.estado,
                "ciudad": row.ciudad,
            }
            for row in rows
        ],
    }
