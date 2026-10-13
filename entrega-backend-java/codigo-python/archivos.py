"""Entrada común para imágenes y páginas de PDF, incluidos escaneos sin texto."""

from pathlib import Path

import cv2
import numpy as np
import pymupdf


def es_pdf(ruta):
    # Inspecciona el contenido: no depende de la extensión elegida al subirlo.
    with Path(ruta).open("rb") as archivo:
        return b"%PDF-" in archivo.read(1024)


def validar_pdf(documento):
    if documento.needs_pass:
        raise ValueError("El PDF está protegido con contraseña.")
    if not len(documento):
        raise ValueError("El PDF no contiene páginas.")


def renderizar_pagina(pagina):
    # 216 dpi; limita también páginas con dimensiones inusualmente grandes.
    escala = min(3.0, 4000 / max(pagina.rect.width, pagina.rect.height))
    pix = pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala), colorspace=pymupdf.csRGB, alpha=False)
    return cv2.cvtColor(np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3), cv2.COLOR_RGB2BGR)


def leer_imagen(ruta):
    contenido = Path(ruta).read_bytes()
    if not contenido:
        raise ValueError("El archivo está vacío.")
    imagen = cv2.imdecode(np.frombuffer(contenido, dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagen is None:
        raise ValueError("Archivo no compatible. Selecciona una imagen JPG/PNG o un PDF válido.")
    return imagen


def cargar_pagina(ruta, pagina=1):
    if pagina < 1:
        raise ValueError("El número de página debe empezar en 1.")
    if es_pdf(ruta):
        with pymupdf.open(ruta) as documento:
            validar_pdf(documento)
            if pagina > len(documento):
                raise ValueError(f"El PDF tiene {len(documento)} página(s); no existe la página {pagina}.")
            return renderizar_pagina(documento[pagina - 1]), {
                "formato": "pdf", "pagina": pagina, "total_paginas": len(documento), "metodo": "ocr",
            }
    if pagina != 1:
        raise ValueError("Solo puedes elegir otra página cuando el archivo es PDF.")
    return leer_imagen(ruta), {"formato": "imagen", "pagina": 1, "total_paginas": 1, "metodo": "ocr"}
