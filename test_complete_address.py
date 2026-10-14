from unittest import TestCase

from backend.app.services.excel_service import format_address as excel_address
from backend.app.services.spreadsheet_service import (
    format_address, parse_sheet_address, restore_complete_sheet_addresses,
)


class CompleteAddressTests(TestCase):
    def test_sheet_address_roundtrip_preserves_every_segment(self):
        value = "CALLE RIO NO. 111, DEPARTAMENTO 104, COLONIA CENTRO, TOLUCA, MEXICO, 50000"
        address = parse_sheet_address(value)
        self.assertEqual(address["completo"], value)
        self.assertEqual(format_address(address), value)
        self.assertEqual(excel_address(address), value)

    def test_legacy_addresses_are_restored_without_changing_review_fields(self):
        original = {"padre": "PADRE REVISADO", "domicilio": {"calle": "CALLE"},
                    "referencias": [{"nombre": "REFERENCIA", "domicilio": {"calle": "OTRA CALLE"}}]}
        source = {"domicilio": parse_sheet_address("CALLE, CENTRO, MUNICIPIO, ESTADO"),
                  "referencias": [{"domicilio": parse_sheet_address("OTRA CALLE S/N, CENTRO, ESTADO")}]}
        result = restore_complete_sheet_addresses(original, source)
        self.assertEqual(result["domicilio"]["completo"], "CALLE, CENTRO, MUNICIPIO, ESTADO")
        self.assertEqual(result["referencias"][0]["domicilio"]["completo"], "OTRA CALLE S/N, CENTRO, ESTADO")
        self.assertEqual(result["padre"], "PADRE REVISADO")
        self.assertEqual(original["domicilio"], {"calle": "CALLE"})

    def test_edited_and_cleared_complete_addresses_are_preserved(self):
        source = {"domicilio": parse_sheet_address("ORIGINAL")}
        for value in ("CORREGIDO", ""):
            result = restore_complete_sheet_addresses({"domicilio": {"completo": value}}, source)
            self.assertEqual(format_address(result["domicilio"]), value)
            self.assertEqual(excel_address(result["domicilio"]), value)
