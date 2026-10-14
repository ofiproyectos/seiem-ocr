from concurrent.futures import ThreadPoolExecutor
import os
from threading import Barrier
from unittest import TestCase, skipUnless
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, or_, select

from backend.app.db.session import SessionLocal, engine
from backend.app.models import Solicitud, UsuarioRevision
from backend.app.models.revision_audit import RevisionAudit
from backend.app.models.revision_lock import RevisionLock
from backend.app.services import revision_lock_service as locks


@skipUnless(os.environ.get("SEIEM_MYSQL_TESTS") == "1", "Prueba MySQL habilitada explicitamente")
class MysqlRevisionLocksTests(TestCase):
    def setUp(self):
        self.assertEqual(engine.dialect.name, "mysql")
        self.solicitud_id = str(uuid4())
        self.names = [f"_TEST_LOCK_{uuid4().hex[:12]}_{suffix}" for suffix in ("A", "B")]
        self.addCleanup(self.cleanup)
        with SessionLocal() as db:
            for name in self.names:
                db.add(UsuarioRevision(username=name, nombre="PRUEBA AUTOMATICA BLOQUEO", password_hash="no-login", activo=False))
            db.add(Solicitud(id=self.solicitud_id, nombre_completo="PRUEBA AUTOMATICA", datos={}))
            db.commit()

    def cleanup(self):
        with SessionLocal() as db:
            db.execute(delete(RevisionLock).where(or_(RevisionLock.username.in_(self.names), RevisionLock.resource.like("test:" + self.solicitud_id + "%"), RevisionLock.resource == "solicitud:" + self.solicitud_id)))
            db.execute(delete(RevisionAudit).where(RevisionAudit.username.in_(self.names)))
            db.execute(delete(Solicitud).where(Solicitud.id == self.solicitud_id))
            db.execute(delete(UsuarioRevision).where(UsuarioRevision.username.in_(self.names)))
            db.commit()

    def simultaneous(self, attempts):
        barrier = Barrier(2)
        def run(attempt):
            username, resource = attempt
            with SessionLocal() as db:
                barrier.wait()
                try:
                    locks.acquire_review_lock(db, resource, username, "test-browser-" + resource)
                    return 200
                except HTTPException as error:
                    return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            return sorted(pool.map(run, attempts))

    def test_two_users_and_two_tabs_are_atomic_on_mysql(self):
        resource = "test:" + self.solicitud_id
        self.assertEqual(self.simultaneous([(self.names[0], resource), (self.names[1], resource)]), [200, 409])
        with SessionLocal() as db:
            for name in self.names:
                locks.release_user_locks(db, name)
            db.commit()
        self.assertEqual(self.simultaneous([(self.names[0], resource + ":1"), (self.names[0], resource + ":2")]), [200, 409])

    def test_resolution_guard_audit_and_release_on_mysql(self):
        with SessionLocal() as db:
            solicitud = db.get(Solicitud, self.solicitud_id)
            token = locks.acquire_review_lock(db, locks.solicitud_resource(solicitud), self.names[0], "test-browser")
            locks.require_review_lock(db, solicitud, self.names[0], token)
            locks.finish_review(db, solicitud, self.names[0], token, {"nombre_completo": "PRUEBA CORREGIDA", "estado": "revisada"})
            db.commit()
            db.refresh(solicitud)
            self.assertEqual(solicitud.nombre_completo, "PRUEBA CORREGIDA")
            self.assertIsNone(db.get(RevisionLock, locks.solicitud_resource(solicitud)))
            self.assertIsNotNone(db.scalar(select(RevisionAudit).where(RevisionAudit.solicitud_id == self.solicitud_id)))
