from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api import solicitudes as api
from backend.app.schemas.solicitud import SolicitudUpdate
from backend.app.services import spreadsheet_service as sheets


class ReviewSyncTests(TestCase):
    def setUp(self):
        for name in ("acquire_review_lock", "require_review_lock", "ensure_reviewable"):
            guard = patch.object(api, name)
            guard.start()
            self.addCleanup(guard.stop)
        def finish(_db, solicitud, _operator, _token, values):
            for field, value in values.items():
                setattr(solicitud, field, value)
        finishing = patch.object(api, "finish_review", side_effect=finish)
        finishing.start()
        self.addCleanup(finishing.stop)
        self.origin = {"rowNumber": 27, "timestamp": "13/10/2026 10:00:00"}
        self.solicitud = SimpleNamespace(
            id="test", datos={"origenGoogleSheet": self.origin, "padre": "PADRE DE PRUEBA"},
            nombre_completo="NOMBRE ANTERIOR", correo_electronico="test@example.com",
        )
        self.db = MagicMock()
        self.db.get.return_value = self.solicitud

    def test_save_commits_before_sync_and_preserves_origin(self):
        events = []
        self.db.commit.side_effect = lambda: events.append("commit")
        payload = SolicitudUpdate(nombre_completo="NOMBRE CORREGIDO", datos={"padre": "PADRE CORREGIDO", "origenGoogleSheet": {"rowNumber": 99}})
        with patch.object(api, "update_sheet_request_from_solicitud", side_effect=lambda row: events.append("sheet")) as sync:
            result = api.actualizar_solicitud("test", payload, self.db, "revisor")
        self.assertEqual(events, ["commit", "sheet"])
        sync.assert_called_once_with(self.solicitud)
        self.assertEqual(result.nombre_completo, "NOMBRE CORREGIDO")
        self.assertEqual(result.datos["origenGoogleSheet"], self.origin)
        self.assertEqual(result.datos["padre"], "PADRE CORREGIDO")

    def test_google_failure_reports_partial_save_and_can_retry(self):
        with patch.object(api, "update_sheet_request_from_solicitud", side_effect=[RuntimeError("offline"), None]) as sync:
            with self.assertRaises(HTTPException) as error:
                api.actualizar_solicitud("test", SolicitudUpdate(nombre_completo="CORREGIDO"), self.db, "revisor")
            self.assertEqual(error.exception.status_code, 503)
            self.assertIn("se guardo en la base de datos", error.exception.detail)
            self.assertEqual(self.solicitud.nombre_completo, "CORREGIDO")
            api.actualizar_solicitud("test", SolicitudUpdate(nombre_completo="CORREGIDO"), self.db, "revisor")
            self.assertEqual(sync.call_count, 2)
        self.db.rollback.assert_not_called()

    def test_database_failure_does_not_write_google(self):
        self.db.commit.side_effect = SQLAlchemyError("offline")
        with patch.object(api, "update_sheet_request_from_solicitud") as sync:
            with self.assertRaises(HTTPException):
                api.actualizar_solicitud("test", SolicitudUpdate(nombre_completo="CORREGIDO"), self.db, "revisor")
            sync.assert_not_called()
        self.db.rollback.assert_called_once()

    def test_reopening_preserves_review_and_does_not_write_google(self):
        self.db.scalars.return_value.all.return_value = [self.solicitud]
        with patch.object(api, "list_sheet_requests", return_value=[{"sheet_row_number": 27, "datos": {}}]), patch.object(api, "update_sheet_request_from_solicitud") as sync:
            result = api.importar_solicitud_google_sheet(27, self.db, "revisor")
            sync.assert_not_called()
        self.assertEqual(result.datos["padre"], "PADRE DE PRUEBA")
        self.db.commit.assert_not_called()

    def test_new_import_does_not_write_google(self):
        self.db.scalars.return_value.all.return_value = []
        with patch.object(api, "list_sheet_requests", return_value=[{"sheet_row_number": 27, "datos": {"origenGoogleSheet": self.origin}}]), patch.object(api, "update_sheet_request_from_solicitud") as sync:
            api.importar_solicitud_google_sheet(27, self.db, "revisor")
            sync.assert_not_called()
        self.db.commit.assert_called_once()

    def test_sync_targets_original_row_and_all_sixteen_columns(self):
        self.solicitud.datos.update({"telefono": "001234", "estadoCivil": "CASADO", "rasgos": {"estatura": "1.70"}})
        settings = SimpleNamespace(google_sheets_enabled=True, google_sheets_spreadsheet_id="test-sheet", google_sheets_sheet_name="datos", google_service_account_json=None, google_service_account_file=None)
        with patch.object(sheets, "get_settings", return_value=settings), patch.object(sheets, "load_service_account_credentials", return_value={}), patch.object(sheets, "fetch_access_token", return_value="test-token"), patch.object(sheets.httpx, "put") as put:
            put.return_value.is_success = True
            sheets.update_sheet_request_from_solicitud(self.solicitud)
        args, kwargs = put.call_args
        self.assertTrue(args[0].endswith("%27datos%27%21A27%3AP27"))
        self.assertEqual(kwargs["params"]["valueInputOption"], "RAW")
        row = kwargs["json"]["values"][0]
        self.assertEqual(len(row), 16)
        self.assertEqual(row[7], "001234")
        self.assertEqual(row[3], "CASADO")

    def test_local_request_does_not_require_google_configuration(self):
        self.solicitud.datos = {}
        with patch.object(sheets, "get_settings") as settings:
            sheets.update_sheet_request_from_solicitud(self.solicitud)
            settings.assert_not_called()
