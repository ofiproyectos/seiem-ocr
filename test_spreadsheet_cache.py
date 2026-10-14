from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from backend.app.services import spreadsheet_service as sheets


class SheetCacheTests(TestCase):
    def setUp(self):
        settings = SimpleNamespace(google_sheets_enabled=True, google_sheets_spreadsheet_id="test",
                                   google_sheets_sheet_name="datos", google_service_account_file=None,
                                   google_service_account_json=None)
        self.settings = patch.object(sheets, "get_settings", return_value=settings)
        self.settings.start()
        self.addCleanup(self.settings.stop)
        sheets.invalidate_sheet_requests()
        self.addCleanup(sheets.invalidate_sheet_requests)
        self.rows = [{"id": f"sheet-row-{i}", "sheet_row_number": i,
                      "nombre_completo": "PERSONA DE PRUEBA", "correo_electronico": "test@example.com",
                      "datos": {"telefono": "5551234567", "referencias": []}}
                     for i in range(2, 123)]

    def test_pages_share_one_read_and_omit_details(self):
        with patch.object(sheets, "_read_sheet_requests", return_value=self.rows) as read:
            first = sheets.list_sheet_requests_page()
            second = sheets.list_sheet_requests_page(2)
        self.assertEqual(read.call_count, 1)
        self.assertEqual(first["total"], 121)
        self.assertEqual(len(first["items"]), 50)
        self.assertEqual(first["items"][0]["sheet_row_number"], 122)
        self.assertEqual(first["items"][-1]["sheet_row_number"], 73)
        self.assertEqual(second["items"][0]["sheet_row_number"], 72)
        self.assertNotIn("datos", first["items"][0])

    def test_search_includes_rows_outside_first_page_without_accents(self):
        self.rows[0]["nombre_completo"] = "MAR\u00cdA L\u00d3PEZ"
        with patch.object(sheets, "_read_sheet_requests", return_value=self.rows):
            result = sheets.list_sheet_requests_page(query="lopez maria")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["sheet_row_number"], 2)

    def test_expiration_and_manual_refresh(self):
        with patch.object(sheets, "_read_sheet_requests", return_value=self.rows) as read, patch.object(sheets.time, "monotonic", return_value=0) as clock:
            sheets.list_sheet_requests()
            clock.return_value = 59
            sheets.list_sheet_requests()
            self.assertEqual(read.call_count, 1)
            clock.return_value = 61
            sheets.list_sheet_requests()
            sheets.list_sheet_requests(force_refresh=True)
            self.assertEqual(read.call_count, 3)

    def test_concurrent_readers_fetch_once_and_cannot_mutate_cache(self):
        with patch.object(sheets, "_read_sheet_requests", return_value=self.rows) as read:
            with ThreadPoolExecutor(max_workers=5) as pool:
                results = list(pool.map(lambda _: sheets.list_sheet_requests(), range(5)))
            results[0][0]["datos"]["telefono"] = "changed"
            self.assertEqual(sheets.list_sheet_requests()[0]["datos"]["telefono"], "5551234567")
        self.assertEqual(read.call_count, 1)

    def test_refresh_error_does_not_cache_empty_results(self):
        with patch.object(sheets, "_read_sheet_requests", side_effect=[self.rows, RuntimeError("offline")]):
            sheets.list_sheet_requests()
            with self.assertRaises(RuntimeError):
                sheets.list_sheet_requests(force_refresh=True)
            self.assertEqual(len(sheets.list_sheet_requests()), 121)

    def test_empty_and_out_of_range_pages(self):
        with patch.object(sheets, "_read_sheet_requests", return_value=self.rows):
            self.assertEqual(sheets.list_sheet_requests_page(99)["page"], 3)
            result = sheets.list_sheet_requests_page(99, query="no-match")
        self.assertEqual((result["page"], result["pages"], result["items"]), (1, 1, []))

    def test_successful_write_invalidates_cache(self):
        with patch.object(sheets, "_read_sheet_requests", return_value=self.rows) as read, patch.object(sheets.httpx, "put") as put:
            put.return_value.is_success = True
            sheets.list_sheet_requests()
            sheets.update_values("test", "datos", "token", 2, ["updated"])
            sheets.list_sheet_requests()
        self.assertEqual(read.call_count, 2)
