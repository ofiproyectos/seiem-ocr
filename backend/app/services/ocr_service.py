from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO
import logging

from fastapi import HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool
from pytesseract import TesseractNotFoundError

from backend.app.config import get_settings
from extraer_documento import procesar_documento
from prueba import TesseractConfigurationError

logger = logging.getLogger(__name__)


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".pdf"}


async def save_upload_temporarily(upload: UploadFile) -> Path:
    settings = get_settings()
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Formato no soportado. Usa imagen o PDF.")

    tmp = NamedTemporaryFile(delete=False, suffix=suffix, dir=settings.upload_dir)
    try:
        with tmp as fh:
            await _copy_limited(upload, fh, settings.max_upload_bytes)
    except Exception:
        Path(tmp.name).unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
    return Path(tmp.name)


async def _copy_limited(upload: UploadFile, destination: BinaryIO, max_bytes: int) -> None:
    copied = 0
    while chunk := await upload.read(1024 * 1024):
        copied += len(chunk)
        if copied > max_bytes:
            raise HTTPException(status_code=413, detail="El archivo supera el tamano permitido.")
        destination.write(chunk)


async def extract_document(tipo: str, upload: UploadFile, pagina: int = 1) -> dict:
    if tipo not in {"ine", "acta", "qr_acta"}:
        raise HTTPException(status_code=400, detail="Tipo de documento invalido.")

    path = await save_upload_temporarily(upload)
    settings = get_settings()
    try:
        return await run_in_threadpool(
            procesar_documento,
            tipo,
            str(path),
            pagina,
            settings.tesseract_cmd,
            False,
        )
    except (TesseractNotFoundError, TesseractConfigurationError) as exc:
        logger.exception("El servidor no pudo iniciar Tesseract")
        raise HTTPException(
            status_code=503,
            detail="El motor de lectura no esta disponible en el servidor. "
                   "Vuelve a intentar el analisis; si persiste, revisa la instalacion de Tesseract y el idioma espanol en el servidor.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"No se pudo extraer informacion: {exc}") from exc
    finally:
        path.unlink(missing_ok=True)
