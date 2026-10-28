"""Safety checks for the disposable Control Plane test database.

These tests do not connect to PostgreSQL.
"""

from __future__ import annotations

import importlib.util
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

DEV = Path(__file__).resolve().parents[1]
SCRIPT = DEV / "scripts" / "provision_control_plane_test_database.py"
ADMIN_URL = "postgresql+psycopg://postgres:secret@localhost:5433/aadi_platform"
APP_URL = "postgresql+psycopg://aadi_platform_app:secret@localhost:5433/aadi_platform"
MIGRATOR_URL = "postgresql+psycopg://aadi_platform_migrator:secret@localhost:5433/aadi_platform"


def load_script():
    spec = importlib.util.spec_from_file_location("provision_control_plane_test_database", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProvisionControlPlaneTestDatabaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = load_script()

    def test_target_is_the_disposable_database_and_refuses_the_others(self) -> None:
        self.assertEqual(self.script.TARGET_DATABASE, "aadi_platform_test")
        self.assertNotIn(self.script.TARGET_DATABASE, self.script.REFUSED_TARGETS)
        for name in (
            "aadi_platform",
            "aadi_crm_dev",
            "aadi_platform_onboarding_test",
            "tenant-subscription-platform",
        ):
            with self.subTest(name=name):
                buffer = StringIO()
                with redirect_stdout(buffer):
                    with self.assertRaises(SystemExit) as caught:
                        self.script.assert_target(name)
                self.assertEqual(caught.exception.code, 1)
                self.assertIn(f"Refusing to target {name}.", buffer.getvalue())

    def test_connect_refuses_development_and_preserved_databases(self) -> None:
        import psycopg

        for name in (
            "aadi_platform",
            "aadi_crm_dev",
            "aadi_platform_onboarding_test",
            "aadi_platform_",
            "aadi_crm_",
        ):
            with self.subTest(name=name):
                with patch.object(psycopg, "connect") as mocked:
                    buffer = StringIO()
                    with redirect_stdout(buffer):
                        with self.assertRaises(SystemExit) as caught:
                            self.script.connect(ADMIN_URL, name)
                    self.assertEqual(caught.exception.code, 1)
                    self.assertIn(f"Refusing to open {name}.", buffer.getvalue())
                    mocked.assert_not_called()

    def test_admin_endpoint_requires_localhost_5433(self) -> None:
        buffer = StringIO()
        with redirect_stdout(buffer):
            with self.assertRaises(SystemExit) as caught:
                self.script.assert_admin_endpoint(
                    "postgresql+psycopg://postgres:secret@db.example:5433/aadi_platform"
                )
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("localhost port 5433", buffer.getvalue())

        buffer = StringIO()
        with redirect_stdout(buffer):
            with self.assertRaises(SystemExit) as caught:
                self.script.assert_admin_endpoint(
                    "postgresql+psycopg://postgres:secret@localhost:5432/aadi_platform"
                )
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("localhost port 5433", buffer.getvalue())

    def test_create_uses_the_exact_name_only_when_absent(self) -> None:
        class Connection:
            def __init__(self, present: bool) -> None:
                self.present = present
                self.statements: list[str] = []

            def execute(self, query, params=None):
                self.statements.append(str(query))
                if params == ("aadi_platform_test",):
                    return _Rows((1,) if self.present else None)
                return _Rows(None)

        present = Connection(True)
        self.assertEqual(self.script.create_if_absent(present), "present")
        self.assertEqual(len(present.statements), 1)

        absent = Connection(False)
        self.assertEqual(self.script.create_if_absent(absent), "created")
        self.assertIn("aadi_platform_test", absent.statements[-1])
        self.assertIn("aadi_platform_migrator", absent.statements[-1])
        self.assertNotIn("aadi_platform_app", absent.statements[-1])

    def test_test_url_changes_only_the_database_name(self) -> None:
        app = self.script.test_url(APP_URL, "aadi_platform_app")
        migrator = self.script.test_url(MIGRATOR_URL, "aadi_platform_migrator")
        self.assertIn("@localhost:5433/aadi_platform_test", app)
        self.assertTrue(app.startswith("postgresql+psycopg://aadi_platform_app:"))
        self.assertTrue(migrator.startswith("postgresql+psycopg://aadi_platform_migrator:"))
        self.assertNotIn("/aadi_platform?", app)
        self.assertFalse(app.endswith("/aadi_platform"))

    def test_source_does_not_grant_superuser_or_createdb(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("SUPERUSER", source)
        self.assertNotIn("CREATEDB", source)
        self.assertNotIn("ALTER ROLE", source.upper())
        self.assertIn('"aadi_platform_onboarding_test"', source)


class _Rows:
    def __init__(self, row: object) -> None:
        self._row = row

    def fetchone(self):
        return self._row


if __name__ == "__main__":
    unittest.main()
