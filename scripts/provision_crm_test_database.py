"""Create the disposable CRM test database when it is absent.

The postgres administrator URL creates the database. The migrator owns it.
This script does not open aadi_platform, aadi_crm_dev for changes, or any
preserved database. It does not print a password or connection string.
Migrations 001 through 008 are applied later by the CRM PostgreSQL tests.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine.url import make_url

WORKSPACE = Path(__file__).resolve().parents[2]
LOCAL_ENV = WORKSPACE / "dev-environment" / "config" / "dev.local.env"
TARGET_DATABASE = "aadi_crm_test"
MIGRATOR_ROLE = "aadi_crm_migrator"
APP_ROLE = "aadi_crm_app"
REQUIRED_PORT = 5433
LOOPBACK = {"localhost", "127.0.0.1", "::1"}
REFUSED_TARGETS = frozenset(
    {
        "aadi_platform",
        "aadi_platform_test",
        "aadi_platform_onboarding_test",
        "aadi_platform_",
        "aadi_crm",
        "aadi_crm_dev",
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
    if parsed.database != "aadi_crm_dev":
        fail("Administrator URL does not point at the CRM development credential.")


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
    connection.execute(sql.SQL("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
    connection.execute(
        sql.SQL("REVOKE CREATE ON SCHEMA public FROM {}").format(sql.Identifier(APP_ROLE))
    )
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
    connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(APP_ROLE)))
    connection.execute(
        sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(sql.Identifier(MIGRATOR_ROLE))
    )


def test_url(source: str) -> str:
    parsed = make_url(source)
    if parsed.username != MIGRATOR_ROLE or parsed.database != "aadi_crm_dev":
        fail("Saved migrator URL is not aadi_crm_migrator on aadi_crm_dev.")
    updated = parsed.set(drivername="postgresql", database=TARGET_DATABASE)
    if (updated.host, updated.port, updated.username) != (parsed.host, parsed.port, MIGRATOR_ROLE):
        fail("Test URL host, port, or role changed unexpectedly.")
    if updated.database != TARGET_DATABASE or not updated.render_as_string(hide_password=False).startswith(
        "postgresql://"
    ):
        fail("Test URL is not a postgresql:// URL for aadi_crm_test.")
    return updated.render_as_string(hide_password=False)


def read_versions(url_text: str) -> str:
    """Read applied CRM migration names. The only statement is a select."""

    parsed = make_url(url_text)
    if (
        (parsed.host or "") not in LOOPBACK
        or parsed.port != REQUIRED_PORT
        or parsed.database != "aadi_crm_dev"
    ):
        fail("Refusing to read migration versions from a database other than aadi_crm_dev.")
    import psycopg

    with psycopg.connect(
        parsed.set(drivername="postgresql").render_as_string(hide_password=False),
        sslmode="disable",
        connect_timeout=5,
    ) as connection:
        rows = connection.execute(
            "SELECT version FROM crm_schema_migrations ORDER BY version"
        ).fetchall()
    return ",".join(row[0] for row in rows)


def assert_runtime(admin_url: str, app_source: str, migrator_url: str) -> None:
    app_parsed = make_url(app_source)
    if app_parsed.username != APP_ROLE:
        fail("Saved application URL is not aadi_crm_app.")
    app_test = app_parsed.set(drivername="postgresql", database=TARGET_DATABASE)
    with connect(migrator_url, TARGET_DATABASE) as connection:
        connection.execute("BEGIN")
        connection.execute("CREATE TABLE dev_role_probe (id integer)")
        connection.execute("ROLLBACK")
    with connect(app_test.render_as_string(hide_password=False), TARGET_DATABASE) as connection:
        current = connection.execute("SELECT current_user, current_database()").fetchone()
        if current != (APP_ROLE, TARGET_DATABASE):
            fail("Application probe did not connect as aadi_crm_app.")
        try:
            connection.execute("CREATE TABLE dev_role_probe (id integer)")
        except Exception as exc:
            if "permission denied" not in str(exc).lower() and "InsufficientPrivilege" not in type(exc).__name__:
                fail("Application role failed for an unexpected reason during the create probe.")
        else:
            connection.execute("DROP TABLE dev_role_probe")
            fail("Application role was able to create a table.")
    del admin_url


def main() -> None:
    assert_target(TARGET_DATABASE)
    local = read_env(LOCAL_ENV)
    admin_url = local.get("CRM_ADMIN_DATABASE_URL", "")
    app_source = local.get("CRM_APP_DATABASE_URL", "")
    migrator_source = local.get("CRM_MIGRATOR_DATABASE_URL", "")
    if not admin_url or not app_source or not migrator_source:
        fail("CRM administrator, application, or migrator URL is missing from dev.local.env.")
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
                "SELECT datname FROM pg_database WHERE datname ILIKE '%aadi%' OR datname ILIKE '%crm%' OR datname ILIKE '%platform%' ORDER BY 1"
            )
        ]
        line("catalog", ",".join(names))
        state = create_if_absent(admin)
        line("database", TARGET_DATABASE)
        line("database_state", state)
    migrator_test = test_url(migrator_source)
    before = read_versions(migrator_source)
    line("aadi_crm_dev_versions_before", before)
    with connect(admin_url, TARGET_DATABASE) as connection:
        grant_test_privileges(connection)
    line("privileges", "granted")
    assert_runtime(admin_url, app_source, migrator_test)
    after = read_versions(migrator_source)
    line("aadi_crm_dev_versions_after", after)
    if before != after:
        fail("aadi_crm_dev migration versions changed. Test setup stopped.")
    upsert_env(
        LOCAL_ENV,
        {
            "CRM_TEST_DATABASE_URL": migrator_test,
            "CRM_TEST_DATABASE_SSLMODE": "disable",
        },
    )
    line("test_url", "saved")
    line("RESULT", "ok")


if __name__ == "__main__":
    main()
