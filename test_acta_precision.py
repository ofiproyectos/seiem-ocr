from time import monotonic
from unittest import TestCase
from unittest.mock import patch

import cv2
import numpy as np

from acta_nacimiento import (
    PaginaTexto, Palabra, aviso_legible, detectar_celdas_registro,
    extraer_curp_validada, interpretar_acta, ocr_celda_aislada, recuperar_codigos_numericos,
)


class ActaPrecisionTests(TestCase):
    def test_missing_numeric_code_is_reread_from_its_label(self):
        page = PaginaTexto([Palabra("Identificador Electronico", 380, 40, 540, 50)])
        code = Palabra("00123456789012345678", 390, 57, 540, 67, confianza=95)
        with patch("acta_nacimiento.ocr_region", return_value=[code]) as region:
            recovered = recuperar_codigos_numericos(np.full((792, 612, 3), 255, dtype=np.uint8), page)
        self.assertIn(code.texto, recovered.completo())
        region.assert_called_once()

    def test_uncertain_numeric_code_is_not_applied(self):
        page = PaginaTexto([Palabra("Identificador Electronico", 380, 40, 540, 50)])
        code = Palabra("00123456789012345678", 390, 57, 540, 67, confianza=20)
        with patch("acta_nacimiento.ocr_region", return_value=[code]):
            recovered = recuperar_codigos_numericos(np.full((792, 612, 3), 255, dtype=np.uint8), page)
        self.assertNotIn(code.texto, recovered.completo())

    def test_empty_parent_row_keeps_its_position_and_gets_a_warning(self):
        words = [Palabra("Datos de Filiacion de la Persona Registrada", 40, 300, 540, 310)]
        for y in (350, 405):
            for x, title in zip((100, 205, 308, 416, 500), ("Nombre(s)", "Primer Apellido", "Segundo Apellido", "Nacionalidad", "CURP")):
                words.append(Palabra(title, x - 20, y, x + 20, y + 8))
        words.append(Palabra("ANA", 80, 380, 120, 390))
        data, warnings = interpretar_acta(PaginaTexto(words))
        self.assertEqual(len(data["filiacion"]), 2)
        self.assertIsNone(data["filiacion"][0]["nombre_completo"])
        self.assertEqual(data["filiacion"][1]["nombres"], "ANA")
        self.assertIn("No se pudo extraer filiacion.0.nombre_completo.", warnings)

    def test_warning_names_field_and_location_instead_of_internal_key(self):
        message = aviso_legible("No se pudo extraer identificador_electronico.")
        self.assertIn("parte superior derecha", message)
        self.assertNotIn("identificador_electronico", message)
        self.assertIn("padre", aviso_legible("No se pudo extraer filiacion.0.nombre_completo."))

    def test_curp_excludes_border_noise_and_rejects_ambiguous_matches(self):
        value = "LOPM900101MDFPRS01"
        self.assertEqual(extraer_curp_validada(value + " CO o"), value)
        self.assertIsNone(extraer_curp_validada("-- --"))
        self.assertIsNone(extraer_curp_validada(value + " LOPM900102MDFPRS01"))
        self.assertIsNone(extraer_curp_validada("LOPM903201MDFPRS01"))

    def test_grid_tracks_offsets_instead_of_fixed_value_positions(self):
        for offset in (0, 15, 30):
            with self.subTest(offset=offset):
                image = np.full((1584, 1224, 3), 255, dtype=np.uint8)
                xs = (355, 392, 457, 492, 551)
                ys = (185 + offset, 199 + offset, 213 + offset)
                for x in xs:
                    cv2.line(image, (x * 2, ys[0] * 2), (x * 2, ys[-1] * 2), (0, 0, 0), 2)
                for y in ys:
                    cv2.line(image, (xs[0] * 2, y * 2), (xs[-1] * 2, y * 2), (0, 0, 0), 2)
                boxes = detectar_celdas_registro(image)
                self.assertEqual(set(boxes), {"oficialia", "fecha_registro", "libro", "numero_acta"})
                self.assertTrue(all(ys[1] <= box[1] < ys[2] for box in boxes.values()))

    def test_blank_page_does_not_invent_a_grid(self):
        self.assertEqual(detectar_celdas_registro(np.full((792, 612, 3), 255, dtype=np.uint8)), {})

    def read_cell(self, readings, campo="numero_acta"):
        image = np.full((792, 612, 3), 255, dtype=np.uint8)
        cv2.putText(image, "987", (505, 221), cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 0, 0), 1)
        with patch("acta_nacimiento.pytesseract.image_to_string", side_effect=readings):
            return ocr_celda_aislada(image, (490, 207, 555, 229), campo, monotonic() + 10)

    def test_cell_needs_two_matching_valid_readings(self):
        self.assertEqual(self.read_cell(["987", "987"]), "987")
        self.assertIsNone(self.read_cell(["987", "887", "787", "687"]))

    def test_book_does_not_accept_letter_noise(self):
        self.assertEqual(self.read_cell(["A", "4", "4"], "libro"), "4")

    def test_impossible_registration_date_is_not_applied(self):
        self.assertIsNone(self.read_cell(["31/02/2020"] * 4, "fecha_registro"))
