"""Extracción local del anverso de credenciales INE con Tesseract."""

import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import sys

import cv2
import numpy as np
import pytesseract

from archivos import cargar_pagina, leer_imagen


# Coordenadas relativas a la tarjeta, no a la fotografía. Distribución del
# anverso con nombre/domicilio al centro y sexo arriba a la derecha.
REGIONES = {
    "nombre": (0.32, 0.34, 0.74, 0.48),
    "domicilio": (0.32, 0.565, 0.77, 0.70),
    "clave_elector": (0.52, 0.708, 0.80, 0.762),
    "curp": (0.32, 0.795, 0.60, 0.85),
    "sexo": (0.86, 0.29, 0.965, 0.35),
    "fecha_nacimiento": (0.325, 0.895, 0.455, 0.95),
    "seccion": (0.575, 0.895, 0.64, 0.95),
    "registro": (0.695, 0.79, 0.805, 0.85),
    "vigencia": (0.695, 0.895, 0.83, 0.95),
}


def configurar_tesseract(ejecutable=None):
    candidatos = [
        ejecutable or os.environ.get("TESSERACT_CMD"),
        shutil.which("tesseract"),
        str(Path.home() / "AppData/Local/Tesseract-OCR/tesseract.exe"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    ]
    if candidatos[0]:
        candidatos = candidatos[:1]
    for candidato in candidatos:
        if candidato and (Path(candidato).is_file() or shutil.which(candidato)):
            pytesseract.pytesseract.tesseract_cmd = candidato
            break
    else:
        raise RuntimeError("No se encontró Tesseract. Indica su ruta con --tesseract.")
    if "spa" not in pytesseract.get_languages(config=""):
        raise RuntimeError("Tesseract necesita el idioma español (spa.traineddata).")


def cargar_imagen(ruta):
    return leer_imagen(ruta)


def ordenar_puntos(puntos):
    puntos = puntos.astype(np.float32)
    suma = puntos.sum(axis=1)
    diferencia = np.diff(puntos, axis=1).ravel()
    return puntos[[suma.argmin(), diferencia.argmin(), suma.argmax(), diferencia.argmax()]]


def rectificar_cuadrilatero(imagen, puntos):
    orden = ordenar_puntos(puntos)
    if len(np.unique(orden, axis=0)) != 4:
        return None
    tl, tr, br, bl = orden
    ancho = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    alto = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    if ancho < 40 or alto < 40:
        return None
    destino = np.float32([[0, 0], [ancho - 1, 0], [ancho - 1, alto - 1], [0, alto - 1]])
    return cv2.warpPerspective(imagen, cv2.getPerspectiveTransform(orden, destino), (round(ancho), round(alto)), borderValue=(255, 255, 255))


def detectar_documento_rectangular(imagen, aspecto_min, aspecto_max, area_min=0.025):
    """Localiza el rectangulo dominante y lo rectifica si su aspecto coincide."""
    alto, ancho = imagen.shape[:2]
    escala = min(1.0, 1600 / max(alto, ancho))
    pequena = cv2.resize(imagen, None, fx=escala, fy=escala)
    gris = cv2.cvtColor(pequena, cv2.COLOR_BGR2GRAY)
    candidatos_mascara = []
    for mascara in (
        cv2.Canny(cv2.GaussianBlur(gris, (5, 5), 0), 30, 90),
        cv2.threshold(cv2.GaussianBlur(gris, (5, 5), 0), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
    ):
        mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidatos_mascara.extend(contornos)
    candidatos = []
    for contorno in candidatos_mascara:
        area = cv2.contourArea(cv2.convexHull(contorno))
        if area < gris.size * area_min:
            continue
        perimetro = cv2.arcLength(contorno, True)
        poligono = cv2.approxPolyDP(contorno, .025 * perimetro, True)
        if len(poligono) != 4 or not cv2.isContourConvex(poligono):
            x, y, w, h = cv2.boundingRect(contorno)
            relleno = area / max(1, w * h)
            if relleno < .72:
                continue
            poligono = np.array([[[x, y]], [[x + w, y]], [[x + w, y + h]], [[x, y + h]]], dtype=np.float32)
        puntos = poligono[:, 0].astype(np.float32) / escala
        orden = ordenar_puntos(puntos)
        w = max(np.linalg.norm(orden[1] - orden[0]), np.linalg.norm(orden[2] - orden[3]))
        h = max(np.linalg.norm(orden[3] - orden[0]), np.linalg.norm(orden[2] - orden[1]))
        aspecto = w / h
        if aspecto_min <= aspecto <= aspecto_max:
            candidatos.append((area, puntos))
    if not candidatos:
        return None
    _, puntos = max(candidatos, key=lambda item: item[0])
    return rectificar_cuadrilatero(imagen, puntos)


def detectar_credencial(imagen):
    """Busca un contorno de tarjeta horizontal y elimina el fondo exterior."""
    rectificada = detectar_documento_rectangular(imagen, 1.35, 1.9, area_min=0.025)
    if rectificada is not None:
        return rectificada, []
    alto, ancho = imagen.shape[:2]
    escala = min(1.0, 1600 / max(alto, ancho))
    pequena = cv2.resize(imagen, None, fx=escala, fy=escala)
    gris = cv2.cvtColor(pequena, cv2.COLOR_BGR2GRAY)
    bordes = cv2.Canny(cv2.GaussianBlur(gris, (5, 5), 0), 30, 90)
    bordes = cv2.morphologyEx(bordes, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contornos, _ = cv2.findContours(bordes, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidatos = []
    for contorno in contornos:
        x, y, w, h = cv2.boundingRect(contorno)
        area = cv2.contourArea(cv2.convexHull(contorno))
        if 1.35 < w / h < 1.85 and area > gris.size * 0.025 and w > 120 and area / (w * h) > 0.75:
            candidatos.append((area, x, y, w, h))
    if candidatos:
        _, x, y, w, h = max(candidatos)
        x, y, w, h = [int(round(v / escala)) for v in (x, y, w, h)]
        return imagen[y:y + h, x:x + w], []
    if 1.35 < ancho / alto < 1.85:
        return imagen, ["No se detectaron bordes: se asumió que la imagen ya está recortada a la credencial."]
    raise ValueError("No se detectó una credencial horizontal. Recorta la tarjeta y colócala derecha.")


def preprocesar_segmento(roi, variante="normalizada"):
    gris = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gris = cv2.resize(gris, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    if variante in ("normalizada", "normalizada_suave", "binaria_200", "binaria_220"):
        sigma = 31 if variante == "normalizada_suave" else 21
        fondo = cv2.GaussianBlur(gris, (0, 0), sigma)
        gris = cv2.divide(gris, fondo, scale=255)
        if variante.startswith("binaria_"):
            gris = cv2.threshold(gris, int(variante.split("_")[1]), 255, cv2.THRESH_BINARY)[1]
    elif variante == "otsu":
        gris = cv2.threshold(gris, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    return cv2.copyMakeBorder(gris, 15, 15, 15, 15, cv2.BORDER_CONSTANT, value=255)


def limpiar_texto(texto):
    return " ".join(texto.upper().split()).strip(" |.,-_")


def normalizar_identificador(texto, tipo):
    """Corrige confusiones OCR solo donde el formato exige letras o números."""
    compacto = re.sub(r"[^A-Z0-9]", "", texto.upper())
    if len(compacto) != 18:
        return None
    if tipo == "curp":
        posiciones_numericas = set(range(4, 10)) | {17}
        posiciones_letras = set(range(4)) | set(range(10, 16))
        patron = r"[A-Z][AEIOUX][A-Z]{2}\d{6}[HM][A-Z]{5}[A-Z0-9]\d"
    else:
        posiciones_numericas = set(range(6, 14)) | {15, 16, 17}
        posiciones_letras = set(range(6)) | {14}
        patron = r"[A-Z]{6}\d{8}[HM]\d{3}"
    numeros = str.maketrans({"O": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8"})
    letras = str.maketrans({"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B"})
    caracteres = []
    for i, caracter in enumerate(compacto):
        if i in posiciones_numericas:
            caracter = caracter.translate(numeros)
        elif i in posiciones_letras:
            caracter = caracter.translate(letras)
        caracteres.append(caracter)
    valor = "".join(caracteres)
    if not re.fullmatch(patron, valor):
        return None
    fecha = valor[4:10] if tipo == "curp" else valor[6:12]
    try:
        datetime.strptime(fecha, "%y%m%d")
    except ValueError:
        return None
    return valor


def interpretar_campo(campo, texto):
    texto = limpiar_texto(texto)
    if campo in ("curp", "clave_elector"):
        return normalizar_identificador(texto, campo)
    if campo == "sexo":
        encontrado = re.search(r"(?:SEXO|SXO)\s*([HM])\b", texto)
        return encontrado[1] if encontrado else texto if texto in ("H", "M") else None
    if campo == "fecha_nacimiento":
        encontrado = re.search(r"\b(\d{2})\s*[/.-]\s*(\d{2})\s*[/.-]\s*(\d{4})\b", texto)
        if encontrado:
            fecha = "/".join(encontrado.groups())
            try:
                datetime.strptime(fecha, "%d/%m/%Y")
                return fecha
            except ValueError:
                pass
        return None
    patrones = {
        "seccion": r"(?<!\d)\d{4}(?!\d)",
        "registro": r"\b((?:19|20)\d{2})\s+(\d{2})\b",
        "vigencia": r"\b((?:19|20)\d{2})\s*[-–—]\s*((?:19|20)\d{2})\b",
    }
    encontrado = re.search(patrones[campo], texto)
    if not encontrado:
        return None
    if campo == "seccion":
        return encontrado[0]
    if campo == "vigencia" and int(encontrado[1]) > int(encontrado[2]):
        return None
    return "-".join(encontrado.groups()) if campo == "vigencia" else " ".join(encontrado.groups())


def seleccionar_valor(campo, lecturas, advertencias):
    validos = [valor for texto in lecturas if (valor := interpretar_campo(campo, texto)) is not None]
    conteo = Counter(validos)
    valor = conteo.most_common(1)[0][0] if conteo else None
    if not validos:
        advertencias.append(f"No se pudo leer {campo} con un formato válido.")
    elif len(conteo) > 1:
        if conteo.most_common(1)[0][1] == 1:
            valor = None
        advertencias.append(f"Lecturas diferentes para {campo}: {' / '.join(conteo)}. Revisar la imagen.")
    elif len(validos) == 1:
        advertencias.append(f"Solo una lectura válida para {campo}. Revisar la imagen.")
    return valor


def leer_region(roi, variante, psm=6):
    """Conserva la confianza de los tokens y los saltos de línea del OCR."""
    resultado = pytesseract.image_to_data(
        preprocesar_segmento(roi, variante), lang="spa",
        config=f"--oem 3 --psm {psm}", timeout=30,
        output_type=pytesseract.Output.DICT,
    )
    lineas, confianzas = {}, []
    for i, texto in enumerate(resultado["text"]):
        if not texto.strip():
            continue
        linea = tuple(resultado[k][i] for k in ("block_num", "par_num", "line_num"))
        lineas.setdefault(linea, []).append(texto)
        # La puntuación decorativa no debe elevar ni reducir la confianza.
        if any(c.isalnum() for c in texto):
            confianzas.append(float(resultado["conf"][i]))
    return {
        "texto": "\n".join(" ".join(palabras) for palabras in lineas.values()),
        "confianza_ocr": min(confianzas) if confianzas else 0.0,
        "variante": variante,
        "psm": psm,
    }


def evaluar_lecturas(campo, lecturas):
    """Resuelve solo coincidencias respaldadas por variantes de imagen distintas.

    La confianza de Tesseract es una puntuación, no una probabilidad.
    Una alternativa fuerte mantiene la advertencia aunque pierda la votación.
    """
    candidatos = {}
    for lectura in lecturas:
        valor = interpretar_campo(campo, lectura["texto"])
        if valor is not None:
            variantes = candidatos.setdefault(valor, {})
            variante = lectura["variante"]
            variantes[variante] = max(variantes.get(variante, 0), lectura["confianza_ocr"])
    orden = sorted(candidatos, key=lambda v: (len(candidatos[v]), max(candidatos[v].values())), reverse=True)
    if not orden:
        return None, False, {"estado": "no_leido", "candidatos": {}}
    ganador = orden[0]
    apoyos = candidatos[ganador]
    fuertes = sum(confianza >= 75 for confianza in apoyos.values())
    rivales = [c for valor in orden[1:] for c in candidatos[valor].values()]
    empate = len(orden) > 1 and len(apoyos) == len(candidatos[orden[1]])
    consenso_amplio = not rivales and len(apoyos) >= 5 and fuertes >= 1 and sum(c >= 60 for c in apoyos.values()) >= 3
    resuelto = (fuertes >= 2 or consenso_amplio) and not empate and (not rivales or max(rivales) < 60)
    return (None if empate else ganador), resuelto, {
        "estado": "confirmado" if resuelto else "revisar",
        "variantes_coincidentes": len(apoyos),
        "variantes_confianza_alta": fuertes,
        "confianza_ocr_maxima": max(apoyos.values()),
        "consenso_amplio": consenso_amplio,
        "candidatos": {v: {"variantes": list(c), "confianza_maxima": max(c.values())} for v, c in candidatos.items()},
    }


def extraer_campo_con_reintentos(campo, roi):
    lecturas = [leer_region(roi, variante) for variante in ("normalizada", "gris", "otsu")]
    valor, resuelto, calidad = evaluar_lecturas(campo, lecturas)
    reintentos = not resuelto
    if reintentos:
        lecturas.extend(leer_region(roi, variante, psm=7) for variante in ("binaria_200", "binaria_220", "normalizada_suave"))
        valor, resuelto, calidad = evaluar_lecturas(campo, lecturas)
    calidad["relectura_aplicada"] = reintentos
    avisos = []
    if not resuelto:
        opciones = " / ".join(calidad["candidatos"])
        avisos.append(f"Revisar {campo}: {opciones or 'sin lectura válida'}; la relectura no logró suficiente acuerdo y confianza.")
    return valor, lecturas, calidad, avisos


def extraer_datos(ruta, ya_recortada=False, pagina=1):
    imagen, entrada = cargar_pagina(ruta, pagina)
    resultado = extraer_imagen_ine(imagen, ya_recortada)
    resultado["entrada"] = entrada
    return resultado


def extraer_imagen_ine(imagen, ya_recortada=False):
    tarjeta, advertencias = (imagen, []) if ya_recortada else detectar_credencial(imagen)
    if tarjeta.shape[1] > 1200:
        tarjeta = cv2.resize(tarjeta, (1200, round(tarjeta.shape[0] * 1200 / tarjeta.shape[1])))
    alto, ancho = tarjeta.shape[:2]
    datos, textos, calidad_campos, detalle_ocr = {}, {}, {}, {}
    for campo, (x1, y1, x2, y2) in REGIONES.items():
        roi = tarjeta[int(y1 * alto):int(y2 * alto), int(x1 * ancho):int(x2 * ancho)]
        if campo in ("nombre", "domicilio"):
            detalle = [leer_region(roi, variante) for variante in ("normalizada", "gris", "otsu")]
            lecturas = [lectura["texto"] for lectura in detalle]
            textos[campo], detalle_ocr[campo] = lecturas, detalle
            calidad_campos[campo] = {"estado": "texto_libre", "confianza_ocr": detalle[0]["confianza_ocr"]}
            lineas = [limpiar_texto(linea) for linea in lecturas[0].splitlines()]
            lineas = [linea for linea in lineas if linea]
            datos[campo] = " ".join(lineas) or None
            if campo == "nombre":
                datos["apellido_paterno"] = lineas[0] if len(lineas) == 3 else None
                datos["apellido_materno"] = lineas[1] if len(lineas) == 3 else None
                datos["nombres"] = lineas[2] if len(lineas) == 3 else None
            else:
                cp = re.search(r"\b\d{5}\b", datos[campo] or "")
                datos["codigo_postal"] = cp[0] if cp else None
            if not datos[campo]:
                advertencias.append(f"No se pudo leer {campo}.")
            continue
        valor, detalle, calidad, avisos = extraer_campo_con_reintentos(campo, roi)
        datos[campo], calidad_campos[campo] = valor, calidad
        detalle_ocr[campo] = detalle
        textos[campo] = [lectura["texto"] for lectura in detalle]
        advertencias.extend(avisos)
    registro = datos.pop("registro")
    datos["anio_registro"], datos["numero_emision"] = registro.split() if registro else (None, None)
    if datos["curp"]:
        if datos["sexo"] and datos["sexo"] != datos["curp"][10]:
            advertencias.append("El sexo leído no coincide con la CURP.")
        if datos["fecha_nacimiento"]:
            fecha = datetime.strptime(datos["fecha_nacimiento"], "%d/%m/%Y").strftime("%y%m%d")
            if fecha != datos["curp"][4:10]:
                advertencias.append("La fecha de nacimiento leída no coincide con la CURP.")
    return {"datos": datos, "advertencias": advertencias, "calidad_campos": calidad_campos, "texto_ocr": textos, "detalle_ocr": detalle_ocr}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("imagen", nargs="?", type=Path, default=Path.home() / "Downloads/prueba.jpeg", help="Imagen o PDF con el anverso de la INE.")
    parser.add_argument("--pagina", type=int, default=1, help="Página del PDF con el anverso (por defecto: 1).")
    parser.add_argument("--salida", type=Path, help="Guardar el resultado en un archivo JSON.")
    parser.add_argument("--tesseract", help="Ruta del ejecutable de Tesseract.")
    parser.add_argument("--recortada", action="store_true", help="La imagen ya contiene solamente la tarjeta.")
    parser.add_argument("--incluir-ocr", action="store_true", help="Incluir las lecturas originales para revisar discrepancias.")
    args = parser.parse_args()
    if args.salida and args.salida.resolve() == args.imagen.resolve():
        parser.error("La salida JSON no puede sobrescribir la imagen de entrada.")
    try:
        configurar_tesseract(args.tesseract)
        resultado = extraer_datos(args.imagen, args.recortada, args.pagina)
        if not args.incluir_ocr:
            resultado.pop("texto_ocr")
            resultado.pop("detalle_ocr")
        contenido = json.dumps(resultado, ensure_ascii=False, indent=2)
        if args.salida:
            args.salida.write_text(contenido + "\n", encoding="utf-8")
        print(contenido)
        return 0
    except (OSError, ValueError, RuntimeError, cv2.error, pytesseract.TesseractError) as exc:
        print(f"Error al procesar: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
