"""Extrae actas de nacimiento mexicanas en formato nacional, PDF o imagen."""

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import sys
import unicodedata

import cv2
import numpy as np
import pymupdf
import pytesseract

from prueba import cargar_imagen, configurar_tesseract, interpretar_campo
from archivos import es_pdf, renderizar_pagina, validar_pdf


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto.upper())
    return re.sub(r"[^A-Z0-9]", "", texto)


@dataclass
class Palabra:
    texto: str
    x0: float
    y0: float
    x1: float
    y1: float
    confianza: float = 100.0

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2


def agrupar_lineas(palabras):
    lineas = []
    for palabra in sorted(palabras, key=lambda p: (p.cy, p.x0)):
        if not lineas or abs(palabra.cy - np.median([p.cy for p in lineas[-1]])) > 2.8:
            lineas.append([])
        lineas[-1].append(palabra)
    return [sorted(linea, key=lambda p: p.x0) for linea in lineas]


class PaginaTexto:
    """Coordenadas normalizadas a una página carta (612 x 792 puntos)."""

    def __init__(self, palabras):
        self.palabras = palabras
        self.lineas = agrupar_lineas(palabras)

    def buscar(self, etiqueta):
        objetivo = normalizar(etiqueta)
        encontrados = []
        for linea in self.lineas:
            for i in range(len(linea)):
                texto = ""
                for j in range(i, len(linea)):
                    texto += normalizar(linea[j].texto)
                    if texto == objetivo:
                        grupo = linea[i:j + 1]
                        encontrados.append(Palabra(etiqueta, min(p.x0 for p in grupo), min(p.y0 for p in grupo), max(p.x1 for p in grupo), max(p.y1 for p in grupo)))
                        break
                    if not objetivo.startswith(texto):
                        break
        return encontrados

    def etiqueta(self, nombre):
        encontrados = self.buscar(nombre)
        return encontrados[0] if encontrados else None

    def caja(self, x0, y0, x1, y1):
        palabras = [p for p in self.palabras if x0 <= p.cx <= x1 and y0 <= p.cy <= y1]
        return "\n".join(" ".join(p.texto for p in linea) for linea in agrupar_lineas(palabras)).strip()

    def completo(self):
        return "\n".join(" ".join(p.texto for p in linea) for linea in self.lineas)

    def debajo(self, nombre, izquierda=365, derecha=580):
        etiqueta = self.etiqueta(nombre)
        if etiqueta is None:
            return None
        return limpiar_valor(self.caja(izquierda, etiqueta.cy + 5, derecha, etiqueta.cy + 25))


def limpiar_valor(texto):
    if texto is None:
        return None
    texto = " ".join(texto.split()).strip()
    if not texto or re.fullmatch(r"[-_—–.\s]+", texto):
        return None
    return texto


def extraer_fila(pagina, etiquetas, arriba=33):
    """Lee valores sobre sus etiquetas y calcula columnas entre sus centros."""
    etiquetas = sorted(etiquetas, key=lambda p: p.cx)
    limites = [40] + [(a.cx + b.cx) / 2 for a, b in zip(etiquetas, etiquetas[1:])] + [580]
    return [pagina.caja(limites[i], etiqueta.cy - arriba, limites[i + 1], etiqueta.cy - 5) for i, etiqueta in enumerate(etiquetas)]


def fecha_escrita(texto):
    # Acepta la expresión habitual de expedición, sin deducir fechas ausentes.
    meses = {mes: i for i, mes in enumerate(("ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"), 1)}
    meses["SETIEMBRE"] = 9
    plano = "".join(c for c in unicodedata.normalize("NFKD", texto.upper()) if not unicodedata.combining(c))
    encontrado = re.search(r"A\s*LOS\s+(\d{1,2})\s+DIAS DEL MES DE\s+([A-Z]+)\s+DE\s+(\d{4})", plano)
    if not encontrado or encontrado[2] not in meses:
        return None
    try:
        return datetime(int(encontrado[3]), meses[encontrado[2]], int(encontrado[1])).strftime("%d/%m/%Y")
    except ValueError:
        return None


def interpretar_acta(pagina):
    advertencias = []
    datos = {
        "tipo_documento": "acta_nacimiento",
        "identificador_electronico": pagina.debajo("Identificador Electrónico"),
        "curp": pagina.debajo("Clave Única de Registro de Población"),
        "numero_certificado_nacimiento": pagina.debajo("Número de Certificado de Nacimiento"),
        "registro": {
            "entidad": pagina.debajo("Entidad de Registro"),
            "municipio": pagina.debajo("Municipio de Registro"),
        },
    }
    for campo, etiqueta in (("oficialia", "Oficialía"), ("fecha_registro", "Fecha de Registro"), ("libro", "Libro"), ("numero_acta", "Número de Acta")):
        ancla = pagina.etiqueta(etiqueta)
        # Límites de tabla calculados mediante las etiquetas vecinas.
        vecinos = sorted([p for nombre in ("Oficialía", "Fecha de Registro", "Libro", "Número de Acta") for p in pagina.buscar(nombre)], key=lambda p: p.cx)
        valor = None
        if ancla and vecinos:
            indice = next(i for i, p in enumerate(vecinos) if normalizar(p.texto) == normalizar(etiqueta))
            izquierda = (vecinos[indice - 1].cx + ancla.cx) / 2 if indice else 365
            derecha = (ancla.cx + vecinos[indice + 1].cx) / 2 if indice + 1 < len(vecinos) else 580
            valor = limpiar_valor(pagina.caja(izquierda, ancla.cy + 5, derecha, ancla.cy + 25))
        datos["registro"][campo] = valor

    persona = dict.fromkeys(("nombres", "primer_apellido", "segundo_apellido", "nombre_completo", "sexo", "fecha_nacimiento", "lugar_nacimiento"))
    filiacion = []
    seccion_filiacion = pagina.etiqueta("Datos de Filiación de la Persona Registrada")
    nombres = pagina.buscar("Nombre(s)")
    for nombre in nombres:
        es_filiacion = seccion_filiacion is not None and nombre.cy > seccion_filiacion.cy
        campos = ["nombres", "primer_apellido", "segundo_apellido"]
        titulos = ["Nombre(s)", "Primer Apellido", "Segundo Apellido"]
        if es_filiacion:
            campos += ["nacionalidad", "curp"]
            titulos += ["Nacionalidad", "CURP"]
        etiquetas = []
        for titulo in titulos:
            opciones = [p for p in pagina.buscar(titulo) if abs(p.cy - nombre.cy) < 8]
            if opciones:
                etiquetas.append(opciones[0])
        if len(etiquetas) != len(titulos):
            advertencias.append("No se reconocieron todas las columnas de una fila de nombres.")
            continue
        valores = extraer_fila(pagina, etiquetas)
        fila = {campo: limpiar_valor(valor) for campo, valor in zip(campos, valores)}
        fila["nombre_completo"] = " ".join(fila[c] for c in campos[:3] if fila[c]) or None
        if es_filiacion:
            filiacion.append(fila)
        else:
            persona.update(fila)
    etiquetas_nacimiento = [pagina.etiqueta(nombre) for nombre in ("Sexo", "Fecha de Nacimiento", "Lugar de Nacimiento")]
    if all(etiquetas_nacimiento):
        sexo, fecha, lugar = extraer_fila(pagina, etiquetas_nacimiento, arriba=38)
        persona["sexo"] = limpiar_valor(sexo)
        persona["fecha_nacimiento"] = limpiar_valor(fecha)
        lineas_lugar = [limpiar_valor(linea) for linea in lugar.splitlines() if limpiar_valor(linea)]
        persona["lugar_nacimiento"] = {
            "texto": limpiar_valor(lugar),
            "municipio": lineas_lugar[0] if len(lineas_lugar) == 2 else None,
            "entidad": lineas_lugar[1] if len(lineas_lugar) == 2 else None,
        }
    datos["persona_registrada"], datos["filiacion"] = persona, filiacion

    anotaciones = pagina.etiqueta("Anotaciones Marginales")
    certificacion = pagina.etiqueta("Certificación")
    firma = next((p for p in pagina.buscar("Firma Electrónica") if 550 < p.cy < 625), None)
    limite_inferior = firma.cy - 12 if firma else 580
    datos["anotaciones_marginales"] = limpiar_valor(pagina.caja(40, anotaciones.cy + 10, 347, limite_inferior)) if anotaciones else None
    texto_certificacion = pagina.caja(350, certificacion.cy + 10, 580, limite_inferior) if certificacion else ""
    fecha_literal = next((linea for linea in texto_certificacion.splitlines() if fecha_escrita(linea)), None)
    # El cargo puede cambiar entre entidades; se conserva la línea completa.
    cargo = next((linea for linea in pagina.lineas if any(normalizar(p.texto).startswith("DIRECTOR") for p in linea) and linea[0].cy > 650), [])
    cargo = [p for p in cargo if 310 < p.cx < 560]
    cargo_y = min((p.cy for p in cargo), default=713)
    datos["certificacion"] = {
        "texto": limpiar_valor(texto_certificacion),
        "fecha_expedicion": fecha_escrita(texto_certificacion),
        "fecha_expedicion_texto": fecha_literal,
        "cargo_funcionario": limpiar_valor(" ".join(p.texto for p in cargo)),
        "nombre_funcionario": limpiar_valor(pagina.caja(310, cargo_y + 6, 580, cargo_y + 24)) if cargo else None,
    }
    qr = next((p for p in pagina.buscar("Código QR") if 620 < p.cy < 680 and p.cx > 480), None)
    texto_firma = pagina.caja(305, firma.cy + 8, 580, min(qr.cy - 8, firma.cy + 40) if qr else firma.cy + 40) if firma else None
    datos["firma_electronica"] = {
        "texto": texto_firma or None,
        "cadena": re.sub(r"\s+", "", texto_firma) if texto_firma else None,
    }
    datos["codigo_verificacion"] = pagina.debajo("Código de Verificación", izquierda=190, derecha=310)
    if datos["codigo_verificacion"]:
        codigo = re.search(r"\b\d{15,30}\b", datos["codigo_verificacion"])
        if codigo:
            datos["codigo_verificacion"] = codigo[0]
        else:
            advertencias.append("El código de verificación no tiene un formato numérico reconocido.")
    datos["leyenda_validacion"] = limpiar_valor(pagina.caja(40, 740, 580, 768))
    enlace = re.search(r"https?://[^\s,]+", datos["leyenda_validacion"] or "")
    datos["url_verificacion"] = enlace[0] if enlace else None

    # Los guiones impresos representan datos no proporcionados, no fallos OCR.
    obligatorios = {
        "identificador_electronico": datos["identificador_electronico"],
        "curp": datos["curp"],
        **{f"registro.{k}": v for k, v in datos["registro"].items()},
        **{f"persona_registrada.{k}": persona[k] for k in ("nombres", "primer_apellido", "sexo", "fecha_nacimiento")},
        "codigo_verificacion": datos["codigo_verificacion"],
    }
    for campo, valor in obligatorios.items():
        if not valor:
            advertencias.append(f"No se pudo extraer {campo}.")
    for nombre, fecha in (("fecha de nacimiento", persona["fecha_nacimiento"]), ("fecha de registro", datos["registro"]["fecha_registro"])):
        if fecha and interpretar_campo("fecha_nacimiento", fecha) is None:
            advertencias.append(f"Revisar {nombre}: formato de fecha no reconocido.")
    if not filiacion:
        advertencias.append("No se pudieron separar los datos de filiación.")
    return datos, advertencias


def imagen_pagina(pagina):
    return renderizar_pagina(pagina)


def texto_pdf(pagina):
    ancho, alto = pagina.rect.width, pagina.rect.height
    return PaginaTexto([Palabra(w[4], w[0] * 612 / ancho, w[1] * 792 / alto, w[2] * 612 / ancho, w[3] * 792 / alto) for w in pagina.get_text("words")])


def texto_ocr(imagen):
    alto, ancho = imagen.shape[:2]
    factor = min(2.0, 2550 / ancho)
    gris = cv2.resize(cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY), None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)
    # Elimina la mayor parte del fondo claro y las marcas de agua sin alterar
    # posiciones: las mismas reglas de columnas sirven para PDF y OCR.
    gris = cv2.threshold(gris, 180, 255, cv2.THRESH_BINARY)[1]
    resultado = pytesseract.image_to_data(gris, lang="spa", config="--oem 3 --psm 11", output_type=pytesseract.Output.DICT, timeout=90)
    palabras = []
    for i, texto in enumerate(resultado["text"]):
        if not texto.strip():
            continue
        x, y, w, h = (resultado[k][i] for k in ("left", "top", "width", "height"))
        palabras.append(Palabra(texto, x * 612 / gris.shape[1], y * 792 / gris.shape[0], (x + w) * 612 / gris.shape[1], (y + h) * 792 / gris.shape[0], float(resultado["conf"][i])))
    # En el formato nacional, tablas, letra pequeña y códigos de barras
    # necesitan segmentación específica. Sustituye únicamente esas regiones.
    refinamientos = [
        ((368, 197, 575, 225), 6, "tabla"),
        ((380, 123, 575, 137), 7, "opcional"),
        ((455, 378, 540, 394), 7, "opcional"),
        ((455, 431, 540, 447), 7, "opcional"),
        ((41, 472, 340, 490), 7, "texto"),
        ((41, 492, 343, 578), 6, "texto"),
        ((350, 472, 574, 490), 7, "texto"),
        ((356, 490, 574, 530), 6, "texto"),
        ((355, 552, 574, 575), 6, "texto"),
        ((370, 584, 478, 604), 7, "texto"),
        ((317, 607, 535, 631), 6, "texto"),
        ((525, 632, 566, 646), 7, "texto"),
        ((211, 704, 282, 717), 7, "texto"),
        ((200, 717, 291, 729), 7, "texto"),
        ((328, 706, 560, 735), 6, "texto"),
        ((40, 742, 580, 768), 6, "texto"),
    ]
    for caja, psm, tipo in refinamientos:
        x0, y0, x1, y1 = caja
        nuevas = ocr_region(imagen, caja, psm, tipo)
        palabras = [p for p in palabras if not (x0 <= p.cx <= x1 and y0 <= p.cy <= y1)]
        palabras.extend(nuevas)
    return PaginaTexto(palabras)


def ocr_region(imagen, caja, psm, tipo):
    alto, ancho = imagen.shape[:2]
    x0, y0, x1, y1 = caja
    roi = imagen[round(y0 * alto / 792):round(y1 * alto / 792), round(x0 * ancho / 612):round(x1 * ancho / 612)]
    gris = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    if tipo == "opcional":
        filas, _ = np.where(gris < 100)
        # Los campos sin dato son una raya horizontal; no convertirla en letras.
        if len(filas) and (filas.max() - filas.min() + 1) * 792 / alto <= 2:
            return [Palabra("---------------", x0, y0, x1, y1)]
    gris = cv2.resize(gris, (round((x1 - x0) * 4.5), round((y1 - y0) * 4.5)), interpolation=cv2.INTER_CUBIC)
    gris = cv2.threshold(gris, 180, 255, cv2.THRESH_BINARY)[1]
    if tipo == "tabla":
        inversa = 255 - gris
        horizontales = cv2.morphologyEx(inversa, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (100, 1)))
        verticales = cv2.morphologyEx(inversa, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 60)))
        gris[cv2.bitwise_or(horizontales, verticales) > 0] = 255
    ancho_roi, alto_roi = gris.shape[1], gris.shape[0]
    gris = cv2.copyMakeBorder(gris, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    resultado = pytesseract.image_to_data(gris, lang="spa", config=f"--oem 3 --psm {psm}", output_type=pytesseract.Output.DICT, timeout=30)
    palabras = []
    for i, texto in enumerate(resultado["text"]):
        if not texto.strip():
            continue
        x, y, w, h = (resultado[k][i] for k in ("left", "top", "width", "height"))
        palabras.append(Palabra(texto, x0 + (x - 20) * (x1 - x0) / ancho_roi, y0 + (y - 20) * (y1 - y0) / alto_roi, x0 + (x + w - 20) * (x1 - x0) / ancho_roi, y0 + (y + h - 20) * (y1 - y0) / alto_roi, float(resultado["conf"][i])))
    return palabras


def interpretar_qr(contenido):
    campos = {}
    for fragmento in contenido.split("|"):
        if ":" not in fragmento:
            continue
        etiqueta, valor = fragmento.split(":", 1)
        clave = re.sub(r"\s+", "_", "".join(c for c in unicodedata.normalize("NFKD", etiqueta.strip().lower()) if not unicodedata.combining(c)))
        campos[clave] = valor.strip().rstrip(",").strip()
    return campos


def leer_qr(imagen):
    alto, ancho = imagen.shape[:2]
    codigos = []
    regiones = {
        "firma": [(39, 590, 190, 739), (30, 580, 210, 740)],
        "datos": [(510, 645, 575, 709), (490, 630, 580, 710)],
    }
    for tipo, cajas in regiones.items():
        contenido, detectado = "", False
        for x0, y0, x1, y1 in cajas:
            roi = imagen[round(y0 * alto / 792):round(y1 * alto / 792), round(x0 * ancho / 612):round(x1 * ancho / 612)]
            contenido, puntos, _ = cv2.QRCodeDetector().detectAndDecode(roi)
            detectado = detectado or puntos is not None
            if contenido:
                break
        codigos.append({"tipo": tipo, "detectado": detectado, "contenido": contenido or None, "campos": interpretar_qr(contenido) if contenido else {}})
    return codigos


def es_acta(pagina):
    return bool(pagina.etiqueta("Acta de Nacimiento") and pagina.etiqueta("Datos de la Persona Registrada"))


def extraer_acta(ruta, tesseract=None, forzar_ocr=False):
    ruta = Path(ruta)
    paginas = []
    candidatos = []
    ocr_configurado = False

    def procesar(numero, nativa, obtener_imagen):
        nonlocal ocr_configurado
        imagen = None
        metodo = "texto_pdf"
        pagina = nativa
        if forzar_ocr or pagina is None or not es_acta(pagina) or len(pagina.palabras) < 80:
            if not ocr_configurado:
                configurar_tesseract(tesseract)
                ocr_configurado = True
            imagen = obtener_imagen()
            pagina = texto_ocr(imagen)
            metodo = "ocr"
        paginas.append({"pagina": numero, "metodo": metodo, "texto_completo": pagina.completo()})
        if es_acta(pagina):
            datos, avisos = interpretar_acta(pagina)
            if metodo == "ocr":
                avisos.append("La certificación y la firma electrónica se transcribieron mediante OCR: revisar su texto literal. El contenido decodificado de los QR se entrega por separado.")
            if imagen is None:
                imagen = obtener_imagen()
            datos["codigos_qr"] = leer_qr(imagen)
            for qr in datos["codigos_qr"]:
                if not qr["contenido"]:
                    avisos.append(f"No se pudo decodificar el QR de {qr['tipo']}; puede no estar presente en este formato.")
                curp_qr = qr["campos"].get("curp")
                if curp_qr and datos["curp"] and curp_qr != datos["curp"]:
                    avisos.append("La CURP del QR no coincide con el texto del acta.")
            candidatos.append({"pagina": numero, "metodo": metodo, "datos": datos, "advertencias": avisos})

    formato_pdf = es_pdf(ruta)
    if formato_pdf:
        with pymupdf.open(ruta) as documento:
            validar_pdf(documento)
            for i, pagina in enumerate(documento):
                procesar(i + 1, texto_pdf(pagina), lambda p=pagina: imagen_pagina(p))
    else:
        imagen = cargar_imagen(ruta)
        procesar(1, None, lambda: imagen)
    if not candidatos:
        raise ValueError("No se reconoció un acta de nacimiento en formato nacional. Verifica que la página esté completa y derecha.")
    principal = candidatos[0]
    resultado = {"datos": principal["datos"], "advertencias": principal["advertencias"], "metodo": principal["metodo"], "pagina_principal": principal["pagina"], "paginas": paginas}
    resultado["entrada"] = {"formato": "pdf" if formato_pdf else "imagen", "total_paginas": len(paginas)}
    if len(candidatos) > 1:
        resultado["actas_adicionales"] = candidatos[1:]
    return resultado


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("documento", type=Path, help="Acta en PDF, JPEG o PNG.")
    parser.add_argument("--salida", type=Path, help="Guardar JSON en UTF-8.")
    parser.add_argument("--tesseract", help="Ruta de Tesseract, necesaria solo para OCR.")
    parser.add_argument("--forzar-ocr", action="store_true", help="Leer el PDF como imagen incluso si contiene texto.")
    args = parser.parse_args()
    if args.salida and args.salida.resolve() == args.documento.resolve():
        parser.error("La salida no puede sobrescribir el documento de entrada.")
    try:
        resultado = extraer_acta(args.documento, args.tesseract, args.forzar_ocr)
        contenido = json.dumps(resultado, ensure_ascii=False, indent=2)
        if args.salida:
            args.salida.write_text(contenido + "\n", encoding="utf-8")
        print(contenido)
        return 0
    except (OSError, ValueError, RuntimeError, cv2.error, pymupdf.FileDataError) as exc:
        print(f"Error al procesar: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
