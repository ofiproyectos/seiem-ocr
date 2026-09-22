from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO

from fastapi import HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from backend.app.config import get_settings
from extraer_documento import procesar_documento


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".pdf"}


async def save_upload_temporarily(upload: UploadFile) -> Path:
    settings = get_settings()
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Formato no soportado. Usa imagen o PDF.")

    tmp = NamedTemporaryFile(delete=False, suffix=suffix, dir=settings.upload_dir)
    total = 0
    try:
        with tmp as fh:
            await _copy_limited(upload, fh, settings.max_upload_bytes)
    except Exception:
        Path(tmp.name).unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    if total > settings.max_upload_bytes:
        Path(tmp.name).unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail="El archivo supera el tamano permitido.")
    return Path(tmp.name)


async def _copy_limited(upload: UploadFile, destination: BinaryIO, max_bytes: int) -> None:
    copied = 0
    while chunk := await upload.read(1024 * 1024):
        copied += len(chunk)
        if copied > max_bytes:
            raise HTTPException(status_code=413, detail="El archivo supera el tamano permitido.")
        destination.write(chunk)


async def extract_document(tipo: str, upload: UploadFile, pagina: int = 1) -> dict:
    if tipo not in {"ine", "acta"}:
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"No se pudo extraer informacion: {exc}") from exc
    finally:
        path.unlink(missing_ok=True)
