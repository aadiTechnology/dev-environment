"""Role checks stay on the two development databases.

Preserved databases are not opened. A runtime role that can already read one
does not block initialization, and no legacy database is created to satisfy a
probe.
"""

from __future__ import annotations

import importlib.util
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

DEV = Path(__file__).resolve().parents[1]
ROLE_SCRIPT = DEV / "scripts" / "configure_database_roles.py"
APP_URL = "postgresql://aadi_platform_app:secret@127.0.0.1:5433/aadi_platform"
MIGRATOR_URL = "postgresql://aadi_platform_migrator:secret@127.0.0.1:5433/aadi_platform"
LEGACY_NAMES = (
    "aadi_platform_",
    "aadi_crm_",
    "aadi_crm_dev_",
    "aadi_platform_test",
    "aadi_platform_onboarding_test",
    "tenant-subscription-platform",
)


def load_roles():
    spec = importlib.util.spec_from_file_location("configure_database_roles", ROLE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScriptedConnection:
    def __init__(self, steps: list[object]) -> None:
        self.steps = list(steps)
        self.statements: list[str] = []

    def execute(self, query, params=None):
        self.statements.append(str(query))
        if not self.steps:
            raise AssertionError(f"unexpected query: {query}")
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        return _Row(step)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _Row:
    def __init__(self, row: object) -> None:
        self._row = row

    def fetchone(self):
        return self._row


class InsufficientPrivilege(Exception):
    pass


class ConfigureDatabaseRolesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.roles = load_roles()

    def test_targets_are_only_the_two_development_databases(self) -> None:
        self.assertEqual(
            {item["database"] for item in self.roles.TARGETS.values()},
            {"aadi_platform", "aadi_crm_dev"},
        )
        source = ROLE_SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("Runtime role can read preserved database", source)
        self.assertNotIn('preserved = "aadi_platform_"', source)

    def test_connect_refuses_legacy_and_unrelated_databases(self) -> None:
        import psycopg

        for name in LEGACY_NAMES:
            with self.subTest(name=name):
                with patch.object(psycopg, "connect") as mocked:
                    buffer = StringIO()
                    with redirect_stdout(buffer):
                        with self.assertRaises(SystemExit) as caught:
                            self.roles.connect(
                                "postgresql://postgres:secret@127.0.0.1:5433/postgres",
                                name,
                            )
                    self.assertEqual(caught.exception.code, 1)
                    self.assertIn(f"Refusing to open {name}.", buffer.getvalue())
                    mocked.assert_not_called()

    def test_connect_refuses_a_non_loopback_host_before_connecting(self) -> None:
        import psycopg

        with patch.object(psycopg, "connect") as mocked:
            buffer = StringIO()
            with redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as caught:
                    self.roles.connect(
                        "postgresql://postgres:secret@db.example.com:5432/postgres",
                        "aadi_platform",
                    )
            self.assertEqual(caught.exception.code, 1)
            self.assertIn("not loopback", buffer.getvalue())
            mocked.assert_not_called()

    def test_runtime_check_does_not_open_legacy_names(self) -> None:
        import psycopg

        for name in ("aadi_platform_", "aadi_crm_", "aadi_crm_dev_"):
            with self.subTest(name=name):
                with patch.object(psycopg, "connect") as mocked:
                    buffer = StringIO()
                    with redirect_stdout(buffer):
                        with self.assertRaises(SystemExit) as caught:
                            self.roles.assert_runtime(APP_URL, MIGRATOR_URL, name)
                    self.assertEqual(caught.exception.code, 1)
                    self.assertIn(f"not {name}.", buffer.getvalue())
                    mocked.assert_not_called()

    def test_runtime_check_opens_only_the_named_target(self) -> None:
        for database in ("aadi_platform", "aadi_crm_dev"):
            with self.subTest(database=database):
                opened: list[str] = []
                app = ScriptedConnection(
                    [(False,), (0,), InsufficientPrivilege("permission denied for schema public")]
                )
                migrator = ScriptedConnection([None, None, None])

                def fake_connect(url: str, name: str, app=app, migrator=migrator) -> ScriptedConnection:
                    opened.append(name)
                    return migrator if "migrator" in url else app

                with patch.object(self.roles, "connect", side_effect=fake_connect):
                    self.roles.assert_runtime(APP_URL, MIGRATOR_URL, database)
                self.assertEqual(opened, [database, database])
                self.assertEqual(app.steps, [])
                self.assertEqual(migrator.steps, [])
                self.assertIn("ROLLBACK", migrator.statements)

    def test_runtime_role_cannot_be_superuser(self) -> None:
        opened: list[str] = []

        def fake_connect(url: str, name: str) -> ScriptedConnection:
            opened.append(name)
            return ScriptedConnection([(True,)])

        buffer = StringIO()
        with patch.object(self.roles, "connect", side_effect=fake_connect):
            with redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as caught:
                    self.roles.assert_runtime(APP_URL, MIGRATOR_URL, "aadi_platform")
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("still a superuser", buffer.getvalue())
        self.assertEqual(opened, ["aadi_platform"])

    def test_runtime_role_cannot_create_a_table(self) -> None:
        opened: list[str] = []
        app = ScriptedConnection([(False,), (0,), None, None])

        def fake_connect(url: str, name: str) -> ScriptedConnection:
            opened.append(name)
            return app

        buffer = StringIO()
        with patch.object(self.roles, "connect", side_effect=fake_connect):
            with redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as caught:
                    self.roles.assert_runtime(APP_URL, MIGRATOR_URL, "aadi_crm_dev")
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("able to create a table", buffer.getvalue())
        self.assertEqual(opened, ["aadi_crm_dev"])
        self.assertTrue(any("DROP TABLE dev_role_probe" in statement for statement in app.statements))

    def test_unexpected_create_probe_error_still_fails(self) -> None:
        def fake_connect(url: str, name: str) -> ScriptedConnection:
            return ScriptedConnection([(False,), (0,), RuntimeError("disk full")])

        buffer = StringIO()
        with patch.object(self.roles, "connect", side_effect=fake_connect):
            with redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as caught:
                    self.roles.assert_runtime(APP_URL, MIGRATOR_URL, "aadi_platform")
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("unexpected reason", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
