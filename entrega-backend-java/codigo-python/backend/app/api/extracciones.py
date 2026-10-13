from fastapi import APIRouter, File, Form, UploadFile

from backend.app.services.ocr_service import extract_document

router = APIRouter(prefix="/extracciones", tags=["extracciones"])


@router.post("")
async def crear_extraccion(
    tipo: str = Form(...),
    pagina: int = Form(1),
    archivo: UploadFile = File(...),
) -> dict:
    resultado = await extract_document(tipo=tipo, upload=archivo, pagina=pagina)
    return {"tipo": tipo, "resultado": resultado}
