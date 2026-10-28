"""Create the disposable Control Plane test database when it is absent.

The postgres administrator URL creates the database and grants. The migrator
owns objects created by Alembic. The application role receives data privileges
only. This script does not open or change aadi_platform, aadi_crm_dev, or any
preserved database. It does not print a password or connection string.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy.engine.url import make_url

WORKSPACE = Path(__file__).resolve().parents[2]
LOCAL_ENV = WORKSPACE / "dev-environment" / "config" / "dev.local.env"
BACKEND = WORKSPACE / "MultiTenant" / "Aadi-MultiTenant-Platform" / "backend"
TARGET_DATABASE = "aadi_platform_test"
MIGRATOR_ROLE = "aadi_platform_migrator"
APP_ROLE = "aadi_platform_app"
REQUIRED_PORT = 5433
LOOPBACK = {"localhost", "127.0.0.1", "::1"}
REFUSED_TARGETS = frozenset(
    {
        "aadi_platform",
        "aadi_crm_dev",
        "aadi_platform_onboarding_test",
        "aadi_platform_",
        "aadi_crm_",
        "tenant-subscription-platform",
    }
)
OPEN_DATABASES = frozenset({"postgres", TARGET_DATABASE})


def fail(message: str) -> None:
    print(f"FAILED {message}")
    raise SystemExit(1)


def line(key: str, value: object) -> None:
    print(f"{key}={value}")


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def upsert_env(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    seen: set[str] = set()
    rewritten: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            rewritten.append(raw)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            rewritten.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            rewritten.append(raw)
    for key, value in updates.items():
        if key not in seen:
            rewritten.append(f"{key}={value}")
    path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def assert_admin_endpoint(url_text: str) -> None:
    parsed = make_url(url_text)
    if (parsed.host or "") not in LOOPBACK or parsed.port != REQUIRED_PORT:
        fail("Administrator URL is not localhost port 5433.")
    if parsed.database != "aadi_platform":
        fail("Administrator URL does not point at the development database credential.")


def assert_target(database: str) -> None:
    if database != TARGET_DATABASE or database in REFUSED_TARGETS:
        fail(f"Refusing to target {database}.")


def connect(url_text: str, database: str):
    if database not in OPEN_DATABASES:
        fail(f"Refusing to open {database}.")
    import psycopg

    parsed = make_url(url_text).set(drivername="postgresql", database=database)
    if (parsed.host or "") not in LOOPBACK or parsed.port != REQUIRED_PORT:
        fail("Refusing a connection that is not localhost port 5433.")
    if database == TARGET_DATABASE:
        assert_target(database)
    return psycopg.connect(
        parsed.render_as_string(hide_password=False),
        sslmode="disable",
        connect_timeout=5,
        autocommit=True,
    )


def create_if_absent(connection) -> str:
    from psycopg import sql

    assert_target(TARGET_DATABASE)
    existing = connection.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s",
        (TARGET_DATABASE,),
    ).fetchone()
    if existing:
        return "present"
    connection.execute(
        sql.SQL("CREATE DATABASE {} OWNER {}").format(
            sql.Identifier(TARGET_DATABASE),
            sql.Identifier(MIGRATOR_ROLE),
        )
    )
    return "created"


def grant_test_privileges(connection) -> None:
    from psycopg import sql

    assert_target(TARGET_DATABASE)
    connection.execute(
        sql.SQL("GRANT CONNECT, TEMP ON DATABASE {} TO {}").format(
            sql.Identifier(TARGET_DATABASE),
            sql.Identifier(APP_ROLE),
        )
    )
    connection.execute(
        sql.SQL("GRANT CONNECT, TEMP ON DATABASE {} TO {}").format(
            sql.Identifier(TARGET_DATABASE),
            sql.Identifier(MIGRATOR_ROLE),
        )
    )
    connection.execute(sql.SQL("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
    connection.execute(
        sql.SQL("REVOKE CREATE ON SCHEMA public FROM {}").format(sql.Identifier(APP_ROLE))
    )
    connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(APP_ROLE)))
    connection.execute(
        sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(sql.Identifier(MIGRATOR_ROLE))
    )
    connection.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
        ).format(sql.Identifier(MIGRATOR_ROLE), sql.Identifier(APP_ROLE))
    )
    connection.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
            "GRANT USAGE, SELECT ON SEQUENCES TO {}"
        ).format(sql.Identifier(MIGRATOR_ROLE), sql.Identifier(APP_ROLE))
    )
    connection.execute(
        sql.SQL(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}"
        ).format(sql.Identifier(APP_ROLE))
    )
    connection.execute(
        sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(
            sql.Identifier(APP_ROLE)
        )
    )


def test_url(source: str, username: str) -> str:
    parsed = make_url(source)
    if parsed.username != username:
        fail(f"Saved role URL is not {username}.")
    updated = parsed.set(database=TARGET_DATABASE)
    if (updated.host, updated.port, updated.username) != (parsed.host, parsed.port, username):
        fail("Test URL host, port, or role changed unexpectedly.")
    if updated.database != TARGET_DATABASE:
        fail("Test URL database is not aadi_platform_test.")
    assert_admin_endpoint(parsed.set(database="aadi_platform").render_as_string(hide_password=False))
    return updated.render_as_string(hide_password=False)


def read_revision(url_text: str, database: str) -> str:
    """Read alembic_version. The only statement is a select."""

    if database not in {"aadi_platform", TARGET_DATABASE}:
        fail(f"Refusing to read a revision from {database}.")
    parsed = make_url(url_text)
    if (parsed.host or "") not in LOOPBACK or parsed.port != REQUIRED_PORT or parsed.database != database:
        fail("Revision URL does not match the requested database.")
    import psycopg

    with psycopg.connect(
        parsed.set(drivername="postgresql").render_as_string(hide_password=False),
        sslmode="disable",
        connect_timeout=5,
    ) as connection:
        try:
            row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        except Exception:
            return "missing"
    return str(row[0]) if row else "missing"


def apply_migrations(app_url: str, migrator_url: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = app_url
    env["CONTROL_PLANE_MIGRATION_DATABASE_URL"] = migrator_url
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        fail("Alembic upgrade failed on aadi_platform_test.")


def assert_ownership_and_runtime(admin_url: str, app_url: str) -> None:
    with connect(admin_url, TARGET_DATABASE) as connection:
        owner = connection.execute(
            """
            SELECT pg_catalog.pg_get_userbyid(c.relowner)
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = 'audit_events'
            """
        ).fetchone()
        if owner is None or owner[0] != MIGRATOR_ROLE:
            fail("audit_events is not owned by aadi_platform_migrator.")
        triggers = connection.execute(
            """
            SELECT t.tgname
            FROM pg_trigger t
            WHERE t.tgrelid = 'public.audit_events'::regclass AND NOT t.tgisinternal
            ORDER BY 1
            """
        ).fetchall()
        names = [row[0] for row in triggers]
        if names != ["audit_events_no_delete", "audit_events_no_update"]:
            fail("Append-only audit triggers are missing.")
    with connect(app_url, TARGET_DATABASE) as connection:
        current = connection.execute("SELECT current_user, current_database()").fetchone()
        if current != (APP_ROLE, TARGET_DATABASE):
            fail("Application probe did not connect as aadi_platform_app.")
        try:
            connection.execute("CREATE TABLE dev_role_probe (id integer)")
        except Exception as exc:
            if "permission denied" not in str(exc).lower() and "InsufficientPrivilege" not in type(exc).__name__:
                fail("Application role failed for an unexpected reason during the create probe.")
        else:
            connection.execute("DROP TABLE dev_role_probe")
            fail("Application role was able to create a table.")


def main() -> None:
    assert_target(TARGET_DATABASE)
    local = read_env(LOCAL_ENV)
    admin_url = local.get("CONTROL_PLANE_ADMIN_DATABASE_URL", "")
    app_source = local.get("CONTROL_PLANE_APP_DATABASE_URL", "")
    migrator_source = local.get("CONTROL_PLANE_MIGRATOR_DATABASE_URL", "")
    if not admin_url or not app_source or not migrator_source:
        fail("Administrator, application, or migrator URL is missing from dev.local.env.")
    assert_admin_endpoint(admin_url)
    with connect(admin_url, "postgres") as admin:
        current = admin.execute(
            "SELECT current_user, rolsuper, inet_server_port() FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
        line("admin_role", current[0])
        line("admin_is_superuser", bool(current[1]))
        line("server_port", current[2])
        if not current[1] or current[2] != REQUIRED_PORT:
            fail("Administrator connection is not a superuser on port 5433. Nothing was created.")
        names = [
            row[0]
            for row in admin.execute(
                "SELECT datname FROM pg_database WHERE datname ILIKE '%aadi%' OR datname ILIKE '%platform%' OR datname ILIKE '%crm%' ORDER BY 1"
            )
        ]
        line("catalog", ",".join(names))
        if "aadi_platform_onboarding_test" in names:
            line("aadi_platform_onboarding_test", "present-not-opened")
        state = create_if_absent(admin)
        line("database", TARGET_DATABASE)
        line("database_state", state)
    app_test = test_url(app_source, APP_ROLE)
    migrator_test = test_url(migrator_source, MIGRATOR_ROLE)
    before = read_revision(app_source, "aadi_platform")
    line("aadi_platform_revision_before", before)
    with connect(admin_url, TARGET_DATABASE) as connection:
        grant_test_privileges(connection)
    line("privileges", "granted")
    apply_migrations(app_test, migrator_test)
    with connect(admin_url, TARGET_DATABASE) as connection:
        grant_test_privileges(connection)
    line("privileges", "granted")
    after_test = read_revision(migrator_test, TARGET_DATABASE)
    line("aadi_platform_test_revision", after_test)
    assert_ownership_and_runtime(admin_url, app_test)
    after = read_revision(app_source, "aadi_platform")
    line("aadi_platform_revision_after", after)
    if before != after:
        fail("aadi_platform revision changed. Test setup stopped.")
    upsert_env(
        LOCAL_ENV,
        {
            "CONTROL_PLANE_TEST_APP_DATABASE_URL": app_test,
            "CONTROL_PLANE_TEST_MIGRATOR_DATABASE_URL": migrator_test,
        },
    )
    line("test_urls", "saved")
    line("RESULT", "ok")


if __name__ == "__main__":
    main()
