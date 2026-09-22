"""Entrada unificada: selecciona INE o acta y entrega una imagen o PDF."""

import argparse
import json
from pathlib import Path
import sys

import cv2
import pymupdf

from acta_nacimiento import extraer_acta
from prueba import configurar_tesseract, extraer_datos


def procesar_documento(tipo, archivo, pagina=1, tesseract=None, incluir_ocr=False):
    if tipo == "ine":
        configurar_tesseract(tesseract)
        resultado = extraer_datos(archivo, pagina=pagina)
        if not incluir_ocr:
            resultado.pop("texto_ocr", None)
            resultado.pop("detalle_ocr", None)
        return resultado
    if tipo == "acta":
        if pagina != 1:
            raise ValueError("Para el acta se procesan todas las páginas automáticamente.")
        return extraer_acta(archivo, tesseract=tesseract)
    raise ValueError("Selecciona ine o acta.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tipo", choices=("ine", "acta"))
    parser.add_argument("archivo", type=Path, help="Imagen JPG/PNG o PDF, digital o escaneado.")
    parser.add_argument("--pagina", type=int, default=1, help="Página con el anverso, solo para INE en PDF.")
    parser.add_argument("--salida", type=Path)
    parser.add_argument("--tesseract")
    parser.add_argument("--incluir-ocr", action="store_true")
    args = parser.parse_args()
    if args.salida and args.salida.resolve() == args.archivo.resolve():
        parser.error("El resultado no puede sobrescribir el archivo de entrada.")
    try:
        resultado = procesar_documento(args.tipo, args.archivo, args.pagina, args.tesseract, args.incluir_ocr)
        texto = json.dumps(resultado, ensure_ascii=False, indent=2)
        if args.salida:
            args.salida.write_text(texto + "\n", encoding="utf-8")
        print(texto)
        return 0
    except (OSError, ValueError, RuntimeError, cv2.error, pymupdf.FileDataError) as exc:
        print(f"Error al procesar: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
