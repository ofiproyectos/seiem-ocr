"""Extrae actas de nacimiento mexicanas en formato nacional, PDF o imagen."""

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import sys
import unicodedata

import cv2
import numpy as np
import pymupdf
import pytesseract

from prueba import cargar_imagen, configurar_tesseract, detectar_documento_rectangular, interpretar_campo
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
        if encontrados or len(objetivo) < 12:
            return encontrados
        # Tolerancia limitada a etiquetas largas, nunca a valores personales.
        for linea in self.lineas:
            for i in range(len(linea)):
                for j in range(i + 1, min(len(linea), i + 9) + 1):
                    grupo = linea[i:j]
                    texto = normalizar("".join(p.texto for p in grupo))
                    if abs(len(texto) - len(objetivo)) <= 2 and SequenceMatcher(None, texto, objetivo).ratio() >= .93:
                        encontrados.append(Palabra(etiqueta, grupo[0].x0, min(p.y0 for p in grupo), grupo[-1].x1, max(p.y1 for p in grupo)))
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


def limpiar_por_patron(texto, campo, estricto=False):
    texto = limpiar_valor(texto)
    if not texto:
        return None
    texto = texto.upper()
    texto_numerico = texto.translate(str.maketrans({"O": "0", "I": "1", "L": "1", "|": "1", "S": "5", "B": "8"}))
    patrones = {
        "oficialia": r"\b\d{1,5}\b",
        "fecha_registro": r"\b\d{1,2}\s*[/.-]\s*\d{1,2}\s*[/.-]\s*\d{4}\b",
        "libro": r"\b[A-Z0-9]{1,8}\b",
        "numero_acta": r"\b\d{1,10}\b",
    }
    if campo == "fecha_registro":
        encontrado = re.search(patrones[campo], texto_numerico)
        return re.sub(r"\s+", "", encontrado[0]).replace("-", "/").replace(".", "/") if encontrado else None
    if campo in ("oficialia", "numero_acta"):
        tokens = re.findall(r"[A-Z0-9|]+", texto_numerico)
        candidatos = [token for token in tokens if token.isdigit()]
        compacto = re.sub(r"[^0-9]", "", texto_numerico) if all(not c.isalpha() for c in texto_numerico.replace("O", "").replace("I", "").replace("L", "").replace("S", "").replace("B", "")) else ""
        if compacto:
            candidatos.append(compacto)
        for candidato in candidatos:
            if registro_valido(campo, candidato, estricto=estricto):
                return candidato
        return None
    if campo == "libro":
        candidatos = re.findall(patrones[campo], texto)
        candidatos = [c for c in candidatos if normalizar(c) not in {"OFICIALIA", "FECHA", "REGISTRO", "LIBRO", "NUMERO", "ACTA"}]
        con_digito = [c for c in candidatos if any(ch.isdigit() for ch in c)]
        if con_digito:
            return con_digito[0]
        if candidatos:
            return candidatos[0]
        return None
    encontrado = re.search(patrones[campo], texto)
    if not encontrado:
        return texto
    valor = re.sub(r"\s+", "", encontrado[0])
    return valor.replace("-", "/").replace(".", "/") if campo == "fecha_registro" else valor


def registro_valido(campo, valor, estricto=False):
    if not valor:
        return False
    if campo in ("oficialia", "numero_acta"):
        if not re.fullmatch(r"\d{1,10}", valor):
            return False
        if campo == "numero_acta" and estricto and (len(valor) < 3 or set(valor) == {"0"}):
            return False
    if campo == "fecha_registro":
        try:
            datetime.strptime(valor, "%d/%m/%Y")
        except ValueError:
            return False
    return True


def texto_columna(palabras, izquierda, derecha, y0, y1):
    elegidas = [
        p for p in palabras
        if izquierda <= p.cx <= derecha and y0 <= p.cy <= y1 and normalizar(p.texto) not in {"OFICIALIA", "FECHADEREGISTRO", "FECHA", "REGISTRO", "LIBRO", "NUMERODEACTA", "NUMERO", "ACTA"}
    ]
    return " ".join(p.texto for p in sorted(elegidas, key=lambda p: (p.cy, p.x0)))


def extraer_registro_por_columnas(palabras, y0=205, y1=275, estricto=False):
    columnas = {
        "oficialia": (360, 420),
        "fecha_registro": (410, 482),
        "libro": (475, 528),
        "numero_acta": (520, 588),
    }
    return {campo: limpiar_por_patron(texto_columna(palabras, izquierda, derecha, y0, y1), campo, estricto=estricto) for campo, (izquierda, derecha) in columnas.items()}


def recortar_normalizado(imagen, caja):
    alto, ancho = imagen.shape[:2]
    x0, y0, x1, y1 = caja
    return imagen[
        max(0, round(y0 * alto / 792)):min(alto, round(y1 * alto / 792)),
        max(0, round(x0 * ancho / 612)):min(ancho, round(x1 * ancho / 612)),
    ]


def corregir_numero_acta_visual(roi, valor):
    if not valor or not valor.startswith("1") or len(valor) < 3:
        return valor
    gris = normalizar_iluminacion(roi)
    evidencias_7 = 0
    for escala in (6, 8):
        ampliada = cv2.resize(gris, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
        for binaria in (
            cv2.threshold(ampliada, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1],
            255 - cv2.adaptiveThreshold(ampliada, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 9),
        ):
            horizontales = cv2.morphologyEx(binaria, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, binaria.shape[1] // 3), 1)))
            verticales = cv2.morphologyEx(binaria, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, binaria.shape[0] // 2))))
            limpia = binaria.copy()
            limpia[cv2.bitwise_or(horizontales, verticales) > 0] = 0
            contornos, _ = cv2.findContours(limpia, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cajas = []
            for contorno in contornos:
                x, y, w, h = cv2.boundingRect(contorno)
                if h > limpia.shape[0] * .18 and w > 3:
                    cajas.append((x, y, w, h))
            if not cajas:
                continue
            x, y, w, h = sorted(cajas, key=lambda c: c[0])[0]
            digito = limpia[y:y + h, x:x + w]
            if digito.size == 0:
                continue
            tercio = max(1, h // 3)
            mitad = max(1, h // 2)
            barra_superior = np.count_nonzero(digito[:tercio]) / max(1, tercio * w)
            tinta_abajo_izquierda = np.count_nonzero(digito[mitad:, :max(1, w // 2)]) / max(1, (h - mitad) * max(1, w // 2))
            ancho_superior = np.count_nonzero(np.any(digito[:tercio] > 0, axis=0)) / max(1, w)
            if ancho_superior > .55 and barra_superior > .18 and tinta_abajo_izquierda < .22:
                evidencias_7 += 1
    return "7" + valor[1:] if evidencias_7 >= 2 else valor


def ocr_celda_registro(imagen, caja, campo, estricto=True):
    roi = recortar_normalizado(imagen, caja)
    if roi.size == 0:
        return None
    gris = normalizar_iluminacion(roi)
    whitelist = "0123456789" if campo in ("oficialia", "libro", "numero_acta") else "0123456789/"
    lecturas = []
    for escala in (6, 8, 10):
        ampliada = cv2.resize(gris, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
        variantes = [
            cv2.threshold(ampliada, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
            cv2.adaptiveThreshold(ampliada, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 9),
            cv2.threshold(ampliada, 170, 255, cv2.THRESH_BINARY)[1],
        ]
        for variante in variantes:
            variante = cv2.copyMakeBorder(variante, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)
            texto = pytesseract.image_to_string(variante, lang="spa", config=f"--oem 3 --psm 7 -c tessedit_char_whitelist={whitelist}", timeout=20)
            valor = limpiar_por_patron(texto, campo, estricto=estricto)
            if valor:
                lecturas.append(valor)
    if not lecturas:
        return None
    conteo = Counter(lecturas)
    valor, repeticiones = conteo.most_common(1)[0]
    if repeticiones >= 2:
        if campo == "numero_acta":
            valor = corregir_numero_acta_visual(roi, valor)
        return valor
    return None


def extraer_valores_registro(pagina):
    campos = (("oficialia", "Oficialia"), ("fecha_registro", "Fecha de Registro"), ("libro", "Libro"), ("numero_acta", "Numero de Acta"))
    etiquetas = [(campo, etiqueta, pagina.etiqueta(etiqueta)) for campo, etiqueta in campos]
    visibles = [(campo, etiqueta, palabra) for campo, etiqueta, palabra in etiquetas if palabra]
    valores = {campo: None for campo, _ in campos}
    if not visibles:
        vecinos = []
    else:
        vecinos = sorted([palabra for _, _, palabra in visibles], key=lambda p: p.cx)
        limites = [365] + [(a.cx + b.cx) / 2 for a, b in zip(vecinos, vecinos[1:])] + [580]
        for campo, etiqueta, ancla in etiquetas:
            valor = None
            if ancla:
                indice = min(range(len(vecinos)), key=lambda i: abs(vecinos[i].cx - ancla.cx))
                izquierda, derecha = limites[indice], limites[indice + 1]
                for alto in (28, 42, 58):
                    valor = limpiar_por_patron(pagina.caja(izquierda, ancla.cy + 4, derecha, ancla.cy + alto), campo)
                    if valor:
                        break
                if not valor:
                    candidatas = [p for p in pagina.palabras if izquierda <= p.cx <= derecha and 0 < p.cy - ancla.cy <= 65 and normalizar(p.texto) != normalizar(etiqueta)]
                    valor = limpiar_por_patron(" ".join(p.texto for p in sorted(candidatas, key=lambda p: (p.cy, p.x0))), campo)
            valores[campo] = valor
    if any(valor is None for valor in valores.values()):
        por_columnas = extraer_registro_por_columnas(pagina.palabras)
        for campo, valor in por_columnas.items():
            valores[campo] = valores[campo] or valor
    return valores


def extraer_registro_desde_imagen(imagen):
    candidatos_por_campo = {"oficialia": [], "fecha_registro": [], "libro": [], "numero_acta": []}
    cajas = (
        (345, 185, 592, 270),
        (350, 195, 590, 290),
        (360, 190, 585, 255),
    )
    for caja in cajas:
        palabras = []
        for psm in (6, 11, 7):
            palabras.extend(ocr_region(imagen, caja, psm, "tabla"))
        pagina = PaginaTexto(palabras)
        candidatos = extraer_valores_registro(pagina)
        por_columnas = extraer_registro_por_columnas(palabras, y0=caja[1], y1=caja[3], estricto=True)
        for campo in candidatos_por_campo:
            for valor in (candidatos.get(campo), por_columnas.get(campo)):
                if valor and registro_valido(campo, valor, estricto=True):
                    candidatos_por_campo[campo].append(valor)
    mejores = {campo: None for campo in candidatos_por_campo}
    for campo, lecturas in candidatos_por_campo.items():
        if lecturas:
            valor, repeticiones = Counter(lecturas).most_common(1)[0]
            if repeticiones >= 2 or len(set(lecturas)) == 1:
                mejores[campo] = valor
    celdas = {
        "oficialia": [(360, 220, 420, 265), (365, 228, 415, 255)],
        "fecha_registro": [(408, 220, 482, 265), (412, 228, 478, 255)],
        "libro": [(475, 220, 525, 265), (485, 228, 518, 255)],
        "numero_acta": [(520, 220, 592, 265), (530, 225, 590, 258), (540, 228, 585, 255)],
    }
    for campo, cajas_campo in celdas.items():
        lecturas = [valor for caja in cajas_campo if (valor := ocr_celda_registro(imagen, caja, campo))]
        if lecturas:
            valor, _ = Counter(lecturas).most_common(1)[0]
            if registro_valido(campo, valor, estricto=(campo != "libro")):
                mejores[campo] = valor
    return mejores


def quitar_avisos_resueltos(avisos, datos):
    resueltos = {f"registro.{campo}" for campo, valor in datos["registro"].items() if valor}
    return [aviso for aviso in avisos if not any(aviso == f"No se pudo extraer {campo}." for campo in resueltos)]


def agregar_aviso(avisos, texto):
    if texto not in avisos:
        avisos.append(texto)


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
        "identificador_electronico": pagina.debajo("Identificador Electronico"),
        "curp": pagina.debajo("Clave Unica de Registro de Poblacion"),
        "numero_certificado_nacimiento": pagina.debajo("Numero de Certificado de Nacimiento"),
        "registro": {
            "entidad": pagina.debajo("Entidad de Registro"),
            "municipio": pagina.debajo("Municipio de Registro"),
        },
    }
    datos["registro"].update(extraer_valores_registro(pagina))

    persona = dict.fromkeys(("nombres", "primer_apellido", "segundo_apellido", "nombre_completo", "sexo", "fecha_nacimiento", "lugar_nacimiento"))
    filiacion = []
    seccion_filiacion = pagina.etiqueta("Datos de Filiacion de la Persona Registrada")
    nombres = pagina.buscar("Nombre(s)")
    for nombre in nombres:
        # Nacionalidad identifica filiación incluso si se perdió su encabezado.
        es_filiacion = (seccion_filiacion is not None and nombre.cy > seccion_filiacion.cy) or any(abs(p.cy - nombre.cy) < 8 for p in pagina.buscar("Nacionalidad"))
        if not es_filiacion and persona["nombre_completo"]:
            advertencias.append("Se encontro otra fila de nombres sin seccion identificable; revisar filiacion.")
            continue
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
    certificacion = pagina.etiqueta("Certificacion")
    firma = next((p for p in pagina.buscar("Firma Electronica") if 550 < p.cy < 625), None)
    limite_inferior = firma.cy - 12 if firma else 580
    datos["anotaciones_marginales"] = limpiar_valor(pagina.caja(40, anotaciones.cy + 10, 347, limite_inferior)) if anotaciones else None
    texto_certificacion = pagina.caja(350, certificacion.cy + 10, 580, limite_inferior) if certificacion else ""
    fecha_literal = next((linea for linea in texto_certificacion.splitlines() if fecha_escrita(linea)), None)
    # El cargo puede cambiar entre entidades; se conserva la linea completa.
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
    qr = next((p for p in pagina.buscar("Codigo QR") if 620 < p.cy < 680 and p.cx > 480), None)
    texto_firma = pagina.caja(305, firma.cy + 8, 580, min(qr.cy - 8, firma.cy + 40) if qr else firma.cy + 40) if firma else None
    datos["firma_electronica"] = {
        "texto": texto_firma or None,
        "cadena": re.sub(r"\s+", "", texto_firma) if texto_firma else None,
    }
    datos["codigo_verificacion"] = pagina.debajo("Codigo de Verificacion", izquierda=190, derecha=310)
    if datos["codigo_verificacion"]:
        codigo = re.search(r"\b\d{15,30}\b", datos["codigo_verificacion"])
        if codigo:
            datos["codigo_verificacion"] = codigo[0]
        else:
            advertencias.append("El codigo de verificacion no tiene un formato numerico reconocido.")
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


def preparar_foto(imagen):
    """Rectifica una hoja grande y convexa; conserva el original si no es clara."""
    rectificada = detectar_documento_rectangular(imagen, .65, .9, area_min=0.25)
    if rectificada is not None:
        return rectificada
    alto, ancho = imagen.shape[:2]
    escala = min(1.0, 1200 / max(alto, ancho))
    pequena = cv2.resize(imagen, None, fx=escala, fy=escala)
    gris = cv2.cvtColor(pequena, cv2.COLOR_BGR2GRAY)
    mascara = cv2.threshold(cv2.GaussianBlur(gris, (5, 5), 0), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contorno in sorted(contornos, key=cv2.contourArea, reverse=True)[:5]:
        if cv2.contourArea(contorno) < gris.size * .5:
            continue
        poligono = cv2.approxPolyDP(contorno, .02 * cv2.arcLength(contorno, True), True)
        if len(poligono) != 4 or not cv2.isContourConvex(poligono):
            continue
        puntos = poligono[:, 0].astype(np.float32) / escala
        suma, diferencia = puntos.sum(axis=1), np.diff(puntos, axis=1).ravel()
        orden = puntos[[suma.argmin(), diferencia.argmin(), suma.argmax(), diferencia.argmax()]]
        if len(np.unique(orden, axis=0)) != 4:
            continue
        tl, tr, br, bl = orden
        w = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
        h = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
        if not .65 < w / h < .9:
            continue
        destino = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]])
        return cv2.warpPerspective(imagen, cv2.getPerspectiveTransform(orden, destino), (round(w), round(h)), borderValue=(255, 255, 255))
    return imagen


def normalizar_iluminacion(imagen):
    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    # Estima el fondo sin letras antes de dividir: conserva trazos en sombras.
    tamano = max(15, round(min(gris.shape) * .025) | 1)
    fondo = cv2.morphologyEx(gris, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (tamano, tamano)))
    return cv2.divide(gris, np.maximum(fondo, 1), scale=255)


def puntuar_lectura(pagina):
    titulos = ("Acta de Nacimiento", "Datos de la Persona Registrada", "Datos de Filiacion de la Persona Registrada", "Nombre(s)", "Primer Apellido", "Segundo Apellido", "Fecha de Nacimiento", "Municipio de Registro", "Oficialia", "Numero de Acta")
    return (es_acta(pagina), sum(len(pagina.buscar(t)) for t in titulos), sum(p.confianza for p in pagina.palabras) / max(1, len(pagina.palabras)))


def texto_ocr(imagen):
    gris = normalizar_iluminacion(imagen)
    factor = min(3.0, 2550 / gris.shape[1])
    gris = cv2.resize(gris, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)
    candidatos = []
    for psm in (11, 6):
        resultado = pytesseract.image_to_data(gris, lang="spa", config=f"--oem 3 --psm {psm}", output_type=pytesseract.Output.DICT, timeout=90)
        palabras = []
        for i, texto in enumerate(resultado["text"]):
            if not texto.strip():
                continue
            x, y, w, h = (resultado[k][i] for k in ("left", "top", "width", "height"))
            palabras.append(Palabra(texto, x * 612 / gris.shape[1], y * 792 / gris.shape[0], (x + w) * 612 / gris.shape[1], (y + h) * 792 / gris.shape[0], float(resultado["conf"][i])))
        candidatos.append(PaginaTexto(palabras))
        if puntuar_lectura(candidatos[-1])[:2] >= (True, 15):
            break
    pagina = max(candidatos, key=puntuar_lectura)
    # La tabla se localiza por sus etiquetas, no por un recuadro fijo.
    anclas = [pagina.etiqueta(t) for t in ("Oficialia", "Fecha de Registro", "Libro", "Numero de Acta")]
    anclas = [p for p in anclas if p]
    if len(anclas) >= 2 and max(p.cy for p in anclas) - min(p.cy for p in anclas) < 8:
        caja = (max(0, min(p.x0 for p in anclas) - 12), max(0, min(p.y0 for p in anclas) - 4), min(612, max(p.x1 for p in anclas) + 12), min(792, max(p.y1 for p in anclas) + 20))
        nuevas = ocr_region(imagen, caja, 6, "tabla")
        x0, y0, x1, y1 = caja
        reemplazo = PaginaTexto([p for p in pagina.palabras if not (x0 <= p.cx <= x1 and y0 <= p.cy <= y1)] + nuevas)
        if nuevas and puntuar_lectura(reemplazo) >= puntuar_lectura(pagina):
            pagina = reemplazo
    return pagina


def ocr_region(imagen, caja, psm, tipo):
    alto, ancho = imagen.shape[:2]
    x0, y0, x1, y1 = caja
    roi = imagen[round(y0 * alto / 792):round(y1 * alto / 792), round(x0 * ancho / 612):round(x1 * ancho / 612)]
    gris = normalizar_iluminacion(roi)
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


def decodificar_qr(roi):
    detector = cv2.QRCodeDetector()
    intentos = [roi]
    gris = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    intentos.extend([
        cv2.resize(roi, None, fx=1.6, fy=1.6, interpolation=cv2.INTER_CUBIC),
        cv2.cvtColor(cv2.threshold(gris, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1], cv2.COLOR_GRAY2BGR),
    ])
    detectado = False
    for imagen in intentos:
        contenido, puntos, _ = detector.detectAndDecode(imagen)
        detectado = detectado or puntos is not None
        if contenido:
            return contenido, True
    return "", detectado


def leer_qr(imagen):
    alto, ancho = imagen.shape[:2]
    codigos_por_tipo = {}
    detector = cv2.QRCodeDetector()
    try:
        detectados, contenidos, puntos, _ = detector.detectAndDecodeMulti(imagen)
    except cv2.error:
        detectados, contenidos, puntos = False, (), None
    if detectados and puntos is not None:
        for contenido, poligono in zip(contenidos, puntos):
            xs = poligono[:, 0]
            ys = poligono[:, 1]
            x0, y0, x1, y1 = max(0, int(xs.min()) - 12), max(0, int(ys.min()) - 12), min(ancho, int(xs.max()) + 12), min(alto, int(ys.max()) + 12)
            tipo = "firma" if (x0 + x1) / 2 < ancho * .45 else "datos"
            if not contenido:
                contenido, _ = decodificar_qr(imagen[y0:y1, x0:x1])
            codigos_por_tipo[tipo] = {"tipo": tipo, "detectado": True, "contenido": contenido or None, "campos": interpretar_qr(contenido) if contenido else {}}
    regiones = {
        "firma": [(39, 590, 190, 739), (30, 580, 210, 740)],
        "datos": [(510, 645, 575, 709), (490, 630, 580, 710)],
    }
    for tipo, cajas in regiones.items():
        if tipo in codigos_por_tipo and codigos_por_tipo[tipo]["contenido"]:
            continue
        contenido, detectado = "", False
        for x0, y0, x1, y1 in cajas:
            roi = imagen[round(y0 * alto / 792):round(y1 * alto / 792), round(x0 * ancho / 612):round(x1 * ancho / 612)]
            contenido, visto = decodificar_qr(roi)
            detectado = detectado or visto
            if contenido:
                break
        codigos_por_tipo[tipo] = {"tipo": tipo, "detectado": codigos_por_tipo.get(tipo, {}).get("detectado", False) or detectado, "contenido": contenido or codigos_por_tipo.get(tipo, {}).get("contenido"), "campos": interpretar_qr(contenido) if contenido else codigos_por_tipo.get(tipo, {}).get("campos", {})}
    return [codigos_por_tipo.get(tipo, {"tipo": tipo, "detectado": False, "contenido": None, "campos": {}}) for tipo in ("firma", "datos")]


def es_acta(pagina):
    evidencias = sum(bool(pagina.etiqueta(titulo)) for titulo in (
        "Datos de la Persona Registrada", "Datos de Filiacion de la Persona Registrada",
        "Entidad de Registro", "Municipio de Registro", "Numero de Acta",
        "Identificador Electronico",
    ))
    return evidencias >= (2 if pagina.etiqueta("Acta de Nacimiento") else 4)


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
            imagen = preparar_foto(obtener_imagen())
            pagina = texto_ocr(imagen)
            metodo = "ocr"
        paginas.append({"pagina": numero, "metodo": metodo, "texto_completo": pagina.completo()})
        if es_acta(pagina):
            datos, avisos = interpretar_acta(pagina)
            if imagen is None:
                imagen = obtener_imagen()
            if metodo == "ocr":
                try:
                    registro_imagen = extraer_registro_desde_imagen(imagen)
                except (RuntimeError, pytesseract.TesseractError, pytesseract.TesseractNotFoundError):
                    registro_imagen = {}
                    agregar_aviso(avisos, "No se pudo aplicar la relectura fina del registro; revisar los campos de oficialia, fecha, libro y numero de acta.")
                for campo, valor in registro_imagen.items():
                    if valor and registro_valido(campo, valor, estricto=(campo != "libro")):
                        if campo == "numero_acta" or not registro_valido(campo, datos["registro"].get(campo), estricto=(campo != "libro")):
                            datos["registro"][campo] = valor
                for campo in ("oficialia", "fecha_registro", "numero_acta"):
                    if not registro_valido(campo, datos["registro"].get(campo), estricto=True):
                        datos["registro"][campo] = None
                        agregar_aviso(avisos, f"No se pudo extraer registro.{campo}.")
                avisos = quitar_avisos_resueltos(avisos, datos)
            datos["codigos_qr"] = leer_qr(imagen)
            for qr in datos["codigos_qr"]:
                if qr["tipo"] == "datos" and qr["detectado"] and not qr["contenido"]:
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
