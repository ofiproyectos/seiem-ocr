from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np
import pymupdf

from archivos import cargar_pagina, es_pdf
from acta_nacimiento import extraer_acta, texto_pdf
from prueba import detectar_credencial, extraer_datos
from extraer_documento import procesar_documento
from test_acta_nacimiento import crear_pdf_sintetico


class ArchivosTests(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.directorio = Path(self.temporal.name)

    def pdf_imagen(self, nombre="escaneo.pdf", paginas=1):
        ruta = self.directorio / nombre
        imagen = np.full((600, 450, 3), 255, dtype=np.uint8)
        cv2.putText(imagen, "ESCANEO", (40, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
        png = cv2.imencode(".png", imagen)[1].tobytes()
        with pymupdf.open() as doc:
            for _ in range(paginas):
                pagina = doc.new_page(width=612, height=792)
                pagina.insert_image(pagina.rect, stream=png)
            doc.save(ruta)
        return ruta

    def test_renderiza_pdf_que_no_contiene_texto(self):
        ruta = self.pdf_imagen()
        with pymupdf.open(ruta) as doc:
            self.assertEqual(doc[0].get_text().strip(), "")
        imagen, entrada = cargar_pagina(ruta)
        self.assertEqual(entrada["formato"], "pdf")
        self.assertEqual(imagen.shape[:2], (2376, 1836))
        self.assertLess(imagen.min(), 10)

    def test_detecta_pdf_aunque_su_extension_sea_otra(self):
        ruta = self.pdf_imagen("archivo.bin")
        self.assertTrue(es_pdf(ruta))
        self.assertEqual(cargar_pagina(ruta)[1]["formato"], "pdf")

    def test_imagen_no_se_confunde_con_pdf_por_su_extension(self):
        ruta = self.directorio / "imagen.pdf"
        ruta.write_bytes(cv2.imencode(".png", np.full((100, 200, 3), 255, np.uint8))[1].tobytes())
        self.assertFalse(es_pdf(ruta))
        self.assertEqual(cargar_pagina(ruta)[1]["formato"], "imagen")
        with self.assertRaises(ValueError):
            cargar_pagina(ruta, pagina=2)

    def test_seleccion_y_limites_de_pagina(self):
        ruta = self.pdf_imagen(paginas=2)
        self.assertEqual(cargar_pagina(ruta, pagina=2)[1]["pagina"], 2)
        for numero in (0, 3):
            with self.assertRaises(ValueError):
                cargar_pagina(ruta, pagina=numero)

    def test_pdf_con_contrasena_da_error_claro(self):
        ruta = self.directorio / "protegido.pdf"
        with pymupdf.open() as doc:
            doc.new_page()
            doc.save(ruta, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="propietario", user_pw="lectura")
        with self.assertRaisesRegex(ValueError, "contraseña"):
            cargar_pagina(ruta)

    def test_ine_pequena_en_hoja_completa(self):
        imagen = np.full((1200, 900, 3), 255, dtype=np.uint8)
        cv2.rectangle(imagen, (100, 350), (420, 550), (80, 80, 80), -1)
        tarjeta, _ = detectar_credencial(imagen)
        self.assertLess(abs(tarjeta.shape[1] - 320), 10)
        self.assertLess(abs(tarjeta.shape[0] - 200), 10)

    def test_ine_pdf_llega_al_mismo_extractor_de_imagen(self):
        ruta = self.pdf_imagen()
        with patch("prueba.extraer_imagen_ine", return_value={"datos": {}}) as extraer:
            resultado = extraer_datos(ruta)
        self.assertEqual(extraer.call_args.args[0].shape[:2], (2376, 1836))
        self.assertEqual(resultado["entrada"]["formato"], "pdf")

    def test_acta_pdf_sin_texto_activa_ocr_sin_pedirlo(self):
        escaneo = self.pdf_imagen()
        digital = self.directorio / "digital.pdf"
        crear_pdf_sintetico(digital)
        with pymupdf.open(digital) as doc:
            pagina_reconocida = texto_pdf(doc[0])
        with patch("acta_nacimiento.configurar_tesseract") as configurar, patch("acta_nacimiento.texto_ocr", return_value=pagina_reconocida) as ocr, patch("acta_nacimiento.leer_qr", return_value=[]):
            resultado = extraer_acta(escaneo)
        configurar.assert_called_once()
        ocr.assert_called_once()
        self.assertEqual(resultado["metodo"], "ocr")
        self.assertEqual(resultado["datos"]["persona_registrada"]["nombres"], "MARIA ELENA")

    def test_selector_de_documentos(self):
        with patch("extraer_documento.extraer_acta", return_value={"datos": {}}) as acta:
            procesar_documento("acta", "archivo.pdf")
        acta.assert_called_once()
        with self.assertRaises(ValueError):
            procesar_documento("otro", "archivo.pdf")
        with self.assertRaises(ValueError):
            procesar_documento("acta", "archivo.pdf", pagina=2)


if __name__ == "__main__":
    unittest.main()
