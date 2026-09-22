from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf

from acta_nacimiento import (
    extraer_acta,
    fecha_escrita,
    interpretar_acta,
    interpretar_qr,
    limpiar_valor,
    texto_pdf,
)


def crear_pdf_sintetico(ruta):
    """Documento de prueba con valores ficticios; no copia archivos personales."""
    doc = pymupdf.open()
    pagina = doc.new_page(width=612, height=792)

    def texto(cx, y, valor, tamano=10):
        ancho = pymupdf.get_text_length(valor, fontsize=tamano)
        pagina.insert_text((cx - ancho / 2, y), valor, fontsize=tamano)

    texto(230, 162, "Acta de Nacimiento", 18)
    for etiqueta, valor, y in (
        ("Identificador Electrónico", "00123456789012345678", 45),
        ("Clave Única de Registro de Población", "LOPE900101HDFRRS01", 85),
        ("Número de Certificado de Nacimiento", "---------------", 123),
        ("Entidad de Registro", "ENTIDAD DE PRUEBA", 151),
        ("Municipio de Registro", "MUNICIPIO DE PRUEBA", 179),
    ):
        texto(475, y, etiqueta, 9)
        texto(475, y + 15, valor)
    for cx, etiqueta, valor in ((390, "Oficialía", "0001"), (445, "Fecha de Registro", "02/01/1990"), (498, "Libro", "03"), (550, "Número de Acta", "0007")):
        texto(cx, 206, etiqueta, 7)
        texto(cx, 221, valor, 8)
    texto(308, 240, "Datos de la Persona Registrada")
    for cx, etiqueta, valor in ((130, "Nombre(s)", "MARIA ELENA"), (313, "Primer Apellido", "LOPEZ"), (491, "Segundo Apellido", "PEREZ")):
        texto(cx, 270, valor)
        texto(cx, 283, etiqueta)
    for cx, etiqueta, valor in ((130, "Sexo", "MUJER"), (313, "Fecha de Nacimiento", "01/01/1990"), (491, "Lugar de Nacimiento", "ENTIDAD DE PRUEBA")):
        texto(cx, 317, valor)
        texto(cx, 330, etiqueta)
    texto(491, 303, "MUNICIPIO DE PRUEBA")
    texto(308, 353, "Datos de Filiación de la Persona Registrada")
    for y, valores in ((392, ("PEDRO", "LOPEZ", "RUIZ", "MEXICANA", "---------------")), (445, ("ANA", "PEREZ", "SOTO", "MEXICANA", "---------------"))):
        for cx, etiqueta, valor in zip((105, 205, 308, 416, 496), ("Nombre(s)", "Primer Apellido", "Segundo Apellido", "Nacionalidad", "CURP"), valores):
            texto(cx, y, valor, 8)
            texto(cx, y + 13, etiqueta, 8)
    texto(115, 484, "Anotaciones Marginales")
    texto(405, 484, "Certificación")
    texto(120, 502, "Sin anotaciones marginales.", 8)
    texto(455, 505, "Texto de certificación de prueba.", 8)
    texto(455, 565, "A los 3 días del mes de Enero de 2022. Doy fe.", 7)
    texto(425, 600, "Firma Electrónica")
    texto(425, 620, "QU JD RA ==", 8)
    texto(545, 644, "Código QR", 8)
    texto(245, 715, "Código de Verificación", 8)
    texto(245, 727, "00012345678901234567", 8)
    texto(440, 715, "Director General del Registro Civil", 8)
    texto(440, 730, "PERSONA FUNCIONARIA", 9)
    texto(310, 752, "Texto completo de prueba que conserva información adicional del documento.", 8)
    doc.save(ruta)
    doc.close()


class ActaTests(unittest.TestCase):
    def test_extrae_columnas_y_filiacion_sin_mezclar_personas(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "acta.pdf"
            crear_pdf_sintetico(ruta)
            with pymupdf.open(ruta) as doc:
                datos, avisos = interpretar_acta(texto_pdf(doc[0]))
        self.assertFalse(avisos)
        self.assertEqual(datos["registro"]["oficialia"], "0001")
        self.assertEqual(datos["registro"]["numero_acta"], "0007")
        self.assertEqual(datos["persona_registrada"]["nombre_completo"], "MARIA ELENA LOPEZ PEREZ")
        self.assertEqual(datos["filiacion"][0]["nombre_completo"], "PEDRO LOPEZ RUIZ")
        self.assertEqual(datos["filiacion"][1]["nombre_completo"], "ANA PEREZ SOTO")
        self.assertIsNone(datos["numero_certificado_nacimiento"])
        self.assertIsNone(datos["filiacion"][0]["curp"])
        self.assertEqual(datos["certificacion"]["fecha_expedicion"], "03/01/2022")
        self.assertEqual(datos["firma_electronica"]["cadena"], "QUJDRA==")
        self.assertEqual(datos["codigo_verificacion"], "00012345678901234567")

    def test_pdf_digital_no_necesita_tesseract(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "acta.pdf"
            crear_pdf_sintetico(ruta)
            with patch("acta_nacimiento.configurar_tesseract") as configurar, patch("acta_nacimiento.leer_qr", return_value=[]):
                resultado = extraer_acta(ruta)
            configurar.assert_not_called()
        self.assertEqual(resultado["metodo"], "texto_pdf")
        self.assertIn("información adicional", resultado["paginas"][0]["texto_completo"])

    def test_qr_conserva_codigos_y_convenciones_originales(self):
        datos = interpretar_qr("Libro:04,|Acta:007,|Sexo:M,|Impreso en: CIUDAD;ENTIDAD")
        self.assertEqual(datos, {"libro": "04", "acta": "007", "sexo": "M", "impreso_en": "CIUDAD;ENTIDAD"})

    def test_guiones_son_ausencia_no_texto_inventado(self):
        self.assertIsNone(limpiar_valor(" ---- ---- "))
        self.assertEqual(limpiar_valor("SIN ANOTACIONES"), "SIN ANOTACIONES")

    def test_fechas_escritas(self):
        self.assertEqual(fecha_escrita("Alos 9 días del mes de Septiembre de 2020. Doy fe."), "09/09/2020")
        self.assertIsNone(fecha_escrita("A los 31 días del mes de Febrero de 2020."))
        self.assertIsNone(fecha_escrita("No hay fecha"))

    def test_pdf_invalido(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "invalido.pdf"
            ruta.write_bytes(b"esto no es un PDF")
            with self.assertRaises((ValueError, pymupdf.FileDataError)):
                extraer_acta(ruta)


if __name__ == "__main__":
    unittest.main()
