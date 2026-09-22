import tempfile
from pathlib import Path
import unittest

import cv2
import numpy as np

from prueba import (
    cargar_imagen,
    detectar_credencial,
    interpretar_campo,
    normalizar_identificador,
    seleccionar_valor,
    evaluar_lecturas,
)


class ExtraccionTests(unittest.TestCase):
    def lecturas(self, valores):
        return [{"texto": valor, "confianza_ocr": confianza, "variante": str(i)} for i, (valor, confianza) in enumerate(valores)]

    def test_relecturas_resuelven_alternativa_de_baja_confianza(self):
        valor, resuelto, _ = evaluar_lecturas("seccion", self.lecturas([("0047", 40), ("0042", 90), ("0042", 85)]))
        self.assertEqual(valor, "0042")
        self.assertTrue(resuelto)

    def test_alternativa_fuerte_se_sigue_advirtiendo(self):
        _, resuelto, _ = evaluar_lecturas("seccion", self.lecturas([("0047", 85), ("0042", 95), ("0042", 90)]))
        self.assertFalse(resuelto)

    def test_consenso_amplio_con_varias_confianzas_moderadas(self):
        _, resuelto, calidad = evaluar_lecturas("seccion", self.lecturas([("0042", c) for c in (67, 51, 55, 67, 78, 69)]))
        self.assertTrue(resuelto)
        self.assertTrue(calidad["consenso_amplio"])

    def test_repetir_la_misma_variante_no_cuenta_como_acuerdo(self):
        lectura = {"texto": "0042", "confianza_ocr": 95, "variante": "gris"}
        _, resuelto, _ = evaluar_lecturas("seccion", [lectura] * 5)
        self.assertFalse(resuelto)

    def test_consenso_de_baja_confianza_no_se_oculta(self):
        _, resuelto, _ = evaluar_lecturas("seccion", self.lecturas([("0042", 30)] * 6))
        self.assertFalse(resuelto)

    def test_empate_ponderado_no_inventa(self):
        valor, resuelto, _ = evaluar_lecturas("seccion", self.lecturas([("0042", 95), ("0047", 80)]))
        self.assertIsNone(valor)
        self.assertFalse(resuelto)

    def test_identificadores_corrigen_solo_posiciones_compatibles(self):
        self.assertEqual(
            normalizar_identificador("LOPE9O0101HDFRRSO1", "curp"),
            "LOPE900101HDFRRSO1",
        )
        self.assertEqual(
            normalizar_identificador("LPRSMN9O010109H100", "clave_elector"),
            "LPRSMN90010109H100",
        )
        self.assertIsNone(normalizar_identificador("ILEGIBLE", "curp"))
        self.assertIsNone(normalizar_identificador("LOPE901332HDFRRS01", "curp"))

    def test_fechas_imposibles_no_se_aceptan(self):
        self.assertIsNone(interpretar_campo("fecha_nacimiento", "31/02/2003"))
        self.assertEqual(interpretar_campo("fecha_nacimiento", "29 / 02 / 2004"), "29/02/2004")
        self.assertIsNone(interpretar_campo("vigencia", "2031-2021"))

    def test_conserva_ceros_iniciales(self):
        self.assertEqual(interpretar_campo("seccion", "0042"), "0042")
        self.assertEqual(interpretar_campo("registro", "2020 00."), "2020 00")

    def test_mayoria_con_discrepancia_advierte(self):
        avisos = []
        self.assertEqual(seleccionar_valor("seccion", ["0042", "0047", "0042"], avisos), "0042")
        self.assertTrue(avisos)

    def test_empate_no_inventa_valor(self):
        avisos = []
        self.assertIsNone(seleccionar_valor("seccion", ["0042", "0047", "ilegible"], avisos))
        self.assertTrue(avisos)

    def test_campo_ausente_es_null(self):
        avisos = []
        self.assertIsNone(seleccionar_valor("sexo", ["", "", ""], avisos))
        self.assertTrue(avisos)

    def test_detecta_tarjeta_fuera_del_centro(self):
        imagen = np.full((900, 1100, 3), 220, dtype=np.uint8)
        cv2.rectangle(imagen, (75, 380), (875, 880), (80, 80, 80), -1)
        tarjeta, avisos = detectar_credencial(imagen)
        self.assertLess(abs(tarjeta.shape[1] - 800), 10)
        self.assertLess(abs(tarjeta.shape[0] - 500), 10)
        self.assertFalse(avisos)

    def test_imagen_sin_tarjeta(self):
        with self.assertRaises(ValueError):
            detectar_credencial(np.full((900, 600, 3), 255, dtype=np.uint8))

    def test_archivo_invalido(self):
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "imagen.jpeg"
            for contenido in (b"", b"no es una imagen"):
                ruta.write_bytes(contenido)
                with self.assertRaises(ValueError):
                    cargar_imagen(ruta)


if __name__ == "__main__":
    unittest.main()
