"""Safety checks for the disposable CRM test database.

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
SCRIPT = DEV / "scripts" / "provision_crm_test_database.py"
ADMIN_URL = "postgresql://postgres:secret@127.0.0.1:5433/aadi_crm_dev"
MIGRATOR_URL = "postgresql://aadi_crm_migrator:secret@127.0.0.1:5433/aadi_crm_dev"


def load_script():
    spec = importlib.util.spec_from_file_location("provision_crm_test_database", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProvisionCrmTestDatabaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = load_script()

    def test_target_is_disposable_and_refuses_development_databases(self) -> None:
        self.assertEqual(self.script.TARGET_DATABASE, "aadi_crm_test")
        self.assertNotIn(self.script.TARGET_DATABASE, self.script.REFUSED_TARGETS)
        for name in ("aadi_crm_dev", "aadi_platform", "aadi_platform_test", "aadi_crm_"):
            with self.subTest(name=name):
                buffer = StringIO()
                with redirect_stdout(buffer):
                    with self.assertRaises(SystemExit) as caught:
                        self.script.assert_target(name)
                self.assertEqual(caught.exception.code, 1)
                self.assertIn(f"Refusing to target {name}.", buffer.getvalue())

    def test_connect_does_not_open_development_databases(self) -> None:
        import psycopg

        for name in ("aadi_crm_dev", "aadi_platform", "aadi_platform_test"):
            with self.subTest(name=name):
                with patch.object(psycopg, "connect") as mocked:
                    buffer = StringIO()
                    with redirect_stdout(buffer):
                        with self.assertRaises(SystemExit) as caught:
                            self.script.connect(ADMIN_URL, name)
                    self.assertEqual(caught.exception.code, 1)
                    mocked.assert_not_called()

    def test_test_url_changes_only_the_database_name(self) -> None:
        url = self.script.test_url(MIGRATOR_URL)
        self.assertTrue(url.startswith("postgresql://aadi_crm_migrator:"))
        self.assertTrue(url.endswith("@127.0.0.1:5433/aadi_crm_test"))
        self.assertNotIn("aadi_crm_dev", url)

    def test_source_does_not_grant_superuser_or_createdb(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("SUPERUSER", source)
        self.assertNotIn("CREATEDB", source)
        self.assertNotIn("ALTER ROLE", source.upper())
        self.assertNotIn("009", source)


if __name__ == "__main__":
    unittest.main()
