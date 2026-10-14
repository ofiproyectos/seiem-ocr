from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.api import auth, solicitudes as api
from backend.app.api.auth import get_current_operator
from backend.app.db.session import Base, get_db
from backend.app.models import Solicitud, UsuarioRevision
from backend.app.models.revision_lock import RevisionLock
from backend.app.models.revision_audit import RevisionAudit
from backend.app.services import revision_lock_service as locks


class RevisionLockTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = create_engine(f"sqlite:///{Path(self.temp.name) / 'locks.db'}", connect_args={"check_same_thread": False, "timeout": 10})
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(self.engine)
        with self.sessions() as db:
            for username, name in (("uno", "REVISOR UNO"), ("dos", "REVISOR DOS")):
                db.add(UsuarioRevision(username=username, nombre=name, password_hash="test"))
            db.add(Solicitud(id="test", nombre_completo="PERSONA DE PRUEBA", datos={}))
            db.commit()
        self.app = FastAPI()
        self.app.include_router(api.router, prefix="/api")
        self.app.include_router(auth.router, prefix="/api")
        def test_db():
            with self.sessions() as db:
                yield db
        def test_operator(x_test_operator: str = Header(default="uno")):
            return x_test_operator
        self.app.dependency_overrides[get_db] = test_db
        self.app.dependency_overrides[get_current_operator] = test_operator
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.headers = {"X-Revision-Lease": "lease-uno"}

    def open_request(self, solicitud_id="test"):
        response = self.client.get(f"/api/solicitudes/{solicitud_id}", headers=self.headers)
        if response.status_code == 200:
            self.headers["X-Revision-Token"] = response.json()["revision_token"]
        return response

    def test_concurrent_acquisition_has_exactly_one_winner(self):
        barrier = Barrier(2)
        def acquire(username):
            with self.sessions() as db:
                barrier.wait()
                try:
                    locks.acquire_review_lock(db, "test-resource", username, "lease-" + username)
                    return 200
                except HTTPException as error:
                    return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(acquire, ("uno", "dos")))
        self.assertEqual(sorted(statuses), [200, 409])

    def test_another_session_cannot_release_or_steal_active_lock(self):
        with self.sessions() as db:
            token = locks.acquire_review_lock(db, "test", "uno", "lease-uno")
            with self.assertRaises(HTTPException):
                locks.release_review_lock(db, "test", "dos", "lease-dos")
            with self.assertRaises(HTTPException) as error:
                locks.acquire_review_lock(db, "test", "dos", "lease-dos")
            self.assertIn("REVISOR UNO", error.exception.detail)
            with self.assertRaises(HTTPException):
                locks.acquire_review_lock(db, "test", "uno", "another-tab")
            locks.acquire_review_lock(db, "test", "uno", "lease-uno")
            locks.release_review_lock(db, "test", "uno", token)
            locks.acquire_review_lock(db, "test", "dos", "lease-dos")

    def test_expired_lock_can_be_taken_and_old_owner_cannot_save(self):
        with self.sessions() as db:
            locks.acquire_review_lock(db, "solicitud:test", "uno", "lease-uno")
            db.get(RevisionLock, "solicitud:test").expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
            locks.acquire_review_lock(db, "solicitud:test", "dos", "lease-dos")
            with self.assertRaises(HTTPException):
                locks.require_review_lock(db, db.get(Solicitud, "test"), "uno", "lease-uno")

    def test_detail_and_save_are_protected_even_with_direct_url(self):
        first = self.open_request()
        self.assertEqual(first.status_code, 200)
        headers = {"X-Test-Operator": "dos", "X-Revision-Lease": "lease-dos"}
        second = self.client.get("/api/solicitudes/test", headers=headers)
        self.assertEqual(second.status_code, 409)
        self.assertIn("REVISOR UNO", second.json()["detail"])
        with patch.object(api, "update_sheet_request_from_solicitud") as sheets:
            result = self.client.put("/api/solicitudes/test", headers=headers, json={"nombre_completo": "NO DEBE GUARDARSE"})
            self.assertEqual(result.status_code, 409)
            sheets.assert_not_called()
        with self.sessions() as db:
            self.assertEqual(db.get(Solicitud, "test").nombre_completo, "PERSONA DE PRUEBA")

    def test_renewal_release_and_expiration(self):
        self.open_request()
        self.assertEqual(self.client.post("/api/solicitudes/test/bloqueo", headers=self.headers).status_code, 200)
        with self.sessions() as db:
            db.get(RevisionLock, "solicitud:test").expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.client.post("/api/solicitudes/test/bloqueo", headers=self.headers).status_code, 409)
        self.open_request()
        self.assertEqual(self.client.delete("/api/solicitudes/test/bloqueo", headers=self.headers).status_code, 204)
        self.assertEqual(self.client.get("/api/solicitudes/test", headers={"X-Test-Operator": "dos", "X-Revision-Lease": "lease-dos"}).status_code, 200)

    def test_same_sheet_row_is_locked_before_import_and_visible_in_table(self):
        row = {"sheet_row_number": 27, "datos": {"origenGoogleSheet": {"rowNumber": 27}}, "nombre_completo": "PRUEBA"}
        with patch.object(api, "list_sheet_requests", return_value=[row]):
            first = self.client.post("/api/solicitudes/google-sheet/27/importar", headers=self.headers)
            self.assertEqual(first.status_code, 200)
            second = self.client.post("/api/solicitudes/google-sheet/27/importar", headers={"X-Test-Operator": "dos", "X-Revision-Lease": "lease-dos"})
            self.assertEqual(second.status_code, 409)
        response = self.client.get("/api/solicitudes/google-sheet/bloqueos?rows=27&rows=28", headers={"X-Test-Operator": "dos"})
        self.assertEqual(response.json()["27"]["nombre"], "REVISOR UNO")
        self.assertFalse(response.json()["27"]["propio"])
        self.assertIsNone(response.json()["28"])
        with self.sessions() as db:
            imported = db.scalars(select(Solicitud).where(Solicitud.id != "test")).all()
            self.assertEqual(len(imported), 1)

    def test_missing_lease_cannot_open_a_request(self):
        self.assertEqual(self.client.get("/api/solicitudes/test").status_code, 409)

    def test_excel_is_blocked_for_other_reviewer(self):
        self.open_request()
        headers = {"X-Test-Operator": "dos", "X-Revision-Lease": "lease-dos"}
        with patch.object(api, "exportar_filiacion_excel") as export:
            self.assertEqual(self.client.post("/api/solicitudes/test/excel", headers=headers, json={}).status_code, 409)
            export.assert_not_called()

    def test_server_generates_token_and_refresh_keeps_same_session(self):
        response = self.open_request()
        token = response.json()["revision_token"]
        self.assertRegex(token, r"^[0-9a-f]{32}$")
        self.assertNotEqual(token, self.headers["X-Revision-Lease"])
        self.assertEqual(self.open_request().json()["revision_token"], token)
        with self.sessions() as db:
            lock = db.get(RevisionLock, "solicitud:test")
            self.assertIsNotNone(lock.acquired_at)
            self.assertIsNotNone(lock.user_id)
            self.assertGreater(lock.expires_at, datetime.utcnow() + timedelta(minutes=9))

    def test_one_active_review_per_user_including_different_tabs(self):
        with self.sessions() as db:
            db.add(Solicitud(id="second", datos={}))
            db.commit()
        self.open_request()
        result = self.client.get("/api/solicitudes/second", headers=self.headers)
        self.assertEqual(result.status_code, 409)
        self.assertIn("Ya tienes una revision activa", result.json()["detail"])
        self.assertEqual(self.client.get("/api/solicitudes/test", headers={"X-Revision-Lease": "another-tab"}).status_code, 409)

    def test_same_user_cannot_concurrently_take_two_different_requests(self):
        barrier = Barrier(2)
        def acquire(resource):
            with self.sessions() as db:
                barrier.wait()
                try:
                    locks.acquire_review_lock(db, resource, "uno", resource)
                    return 200
                except HTTPException as error:
                    return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(acquire, ("first", "second"))), [200, 409])

    def test_save_releases_lock_and_records_revision_in_same_transaction(self):
        self.open_request()
        with patch.object(api, "update_sheet_request_from_solicitud"):
            response = self.client.put("/api/solicitudes/test", headers=self.headers, json={"nombre_completo": "NOMBRE CORREGIDO"})
        self.assertEqual(response.status_code, 200)
        with self.sessions() as db:
            self.assertIsNone(db.get(RevisionLock, "solicitud:test"))
            self.assertEqual(db.get(Solicitud, "test").estado, "revisada")
            audit = db.scalar(select(RevisionAudit))
            self.assertEqual(audit.username, "uno")
            self.assertIn("nombre_completo", audit.campos)

    def test_wrong_token_and_changed_state_cannot_resolve(self):
        self.open_request()
        headers = {**self.headers, "X-Revision-Token": "wrong"}
        self.assertEqual(self.client.put("/api/solicitudes/test", headers=headers, json={"nombre_completo": "WRONG"}).status_code, 409)
        with self.sessions() as db:
            db.get(Solicitud, "test").estado = "cancelada"
            db.commit()
        self.assertEqual(self.client.put("/api/solicitudes/test", headers=self.headers, json={"nombre_completo": "WRONG"}).status_code, 409)

    def test_logout_releases_only_current_users_reservations(self):
        self.open_request()
        with self.sessions() as db:
            locks.acquire_review_lock(db, "another", "dos", "lease-dos")
        self.assertEqual(self.client.post("/api/auth/logout", headers=self.headers).status_code, 200)
        with self.sessions() as db:
            self.assertIsNone(db.get(RevisionLock, "solicitud:test"))
            self.assertIsNotNone(db.get(RevisionLock, "another"))
