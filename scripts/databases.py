"""Check or create the development databases. This script does not drop or truncate.

It prints database names, loopback status, and table counts. It does not print
usernames, passwords, or connection strings.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

WORKSPACE = Path(__file__).resolve().parents[2]
CONTROL_PLANE = WORKSPACE / "MultiTenant" / "Aadi-MultiTenant-Platform"
CRM = WORKSPACE / "Product" / "aadi-crm"
SAFE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
LOOPBACK = {"localhost", "127.0.0.1", "::1"}
REFUSED = {"aadi_platform_", "aadi_crm_", "aadi_platform_test", "aadi_platform_onboarding_test"}


def fail(message: str) -> None:
    print(f"FAILED {message}")
    raise SystemExit(1)


def line(key: str, value: object) -> None:
    print(f"{key}={value}")


def load_control_plane():
    import os

    backend = CONTROL_PLANE / "backend"
    os.chdir(backend)
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    admin_url = read_env_assignments(WORKSPACE / "dev-environment" / "config" / "dev.local.env").get(
        "CONTROL_PLANE_ADMIN_DATABASE_URL", ""
    )
    if admin_url:
        parsed = make_url(admin_url)
        if (parsed.host or "") not in LOOPBACK or parsed.database in REFUSED or "prod" in (parsed.database or "").lower():
            fail("The saved administrator database URL is not a local development database.")
        os.environ["DATABASE_URL"] = admin_url
    from app.core.config import get_settings, reset_settings_cache

    reset_settings_cache()
    return get_settings()


def assert_development(settings) -> None:
    line("environment", settings.environment)
    if settings.environment != "development":
        fail("Control Plane ENVIRONMENT must be development.")
    url = make_url(settings.database_url)
    host = url.host or ""
    line("control_plane_host_loopback", host in LOOPBACK)
    line("control_plane_port", url.port or 5432)
    line("control_plane_database", url.database or "")
    if host not in LOOPBACK:
        fail("Control Plane database host is not loopback.")
    if not url.database or not SAFE_NAME.fullmatch(url.database):
        fail("Control Plane database name is not a safe identifier.")
    lowered = url.database.lower()
    if "prod" in lowered or url.database in REFUSED:
        fail("Control Plane database name is refused.")


def maintenance_engine(settings):
    url = make_url(settings.database_url).set(database="postgres")
    return create_engine(url, isolation_level="AUTOCOMMIT")


def database_names(connection) -> list[str]:
    return [
        row[0]
        for row in connection.execute(
            text("SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname")
        )
    ]


def table_count(settings, database: str) -> int | None:
    if not SAFE_NAME.fullmatch(database):
        return None
    engine = create_engine(make_url(settings.database_url).set(database=database))
    try:
        with engine.connect() as connection:
            return int(
                connection.execute(
                    text(
                        "SELECT count(*) FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).scalar()
                or 0
            )
    except Exception:
        return None
    finally:
        engine.dispose()


def create_database(connection, name: str) -> str:
    if not SAFE_NAME.fullmatch(name) or name in REFUSED or "prod" in name.lower():
        fail(f"Refusing to create database {name}.")
    found = connection.execute(
        text("SELECT 1 FROM pg_database WHERE datname = :name"),
        {"name": name},
    ).scalar()
    if found:
        return "exists"
    connection.execute(text(f"CREATE DATABASE {name}"))
    return "created"


def crm_env_path() -> Path:
    return CRM / "backend" / ".env"


def read_env_assignments(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line_text = raw.strip()
        if not line_text or line_text.startswith("#") or "=" not in line_text:
            continue
        key, value = line_text.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def crm_target_from_env() -> tuple[str, int, str, str]:
    values = read_env_assignments(crm_env_path())
    raw = values.get("CRM_DATABASE_URL", "")
    if not raw:
        fail("CRM backend .env has no CRM_DATABASE_URL.")
    parsed = urlparse(raw)
    host = parsed.hostname or ""
    database = parsed.path.lstrip("/")
    sslmode = values.get("CRM_DATABASE_SSLMODE", "")
    return host, parsed.port or 5432, database, sslmode


def retarget_crm_env(target_name: str) -> str:
    path = crm_env_path()
    text_value = path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in text_value else "\n"
    lines = text_value.splitlines()
    changed = False
    found = False
    for index, raw in enumerate(lines):
        stripped = raw.strip()
        if stripped.startswith("#") or not stripped.startswith("CRM_DATABASE_URL="):
            continue
        found = True
        key, value = raw.split("=", 1)
        parsed = urlparse(value.strip().strip('"').strip("'"))
        current = parsed.path.lstrip("/")
        if current == target_name:
            return "unchanged"
        if current != "aadi_crm":
            fail(
                "CRM_DATABASE_URL does not name aadi_crm or the configured development database. "
                "The file was not changed."
            )
        suffix = f"/{current}"
        if suffix not in value:
            fail("CRM_DATABASE_URL could not be retargeted without rewriting the credential.")
        lines[index] = f"{key}={value.replace(suffix, f'/{target_name}', 1)}"
        changed = True
        break
    if not found:
        fail("CRM backend .env has no CRM_DATABASE_URL assignment.")
    if changed:
        path.write_text(newline.join(lines) + newline, encoding="utf-8")
        return "retargeted"
    return "unchanged"


def generate_password(local_env: Path) -> str:
    import secrets

    text_value = local_env.read_text(encoding="utf-8") if local_env.is_file() else ""
    for raw in text_value.splitlines():
        if raw.startswith("IDENTITY_PASSWORD=") and raw.split("=", 1)[1].strip():
            line("local_password", "present")
            return "present"
    password = secrets.token_urlsafe(24)
    newline = "\r\n" if "\r\n" in text_value else "\n"
    if text_value and not text_value.endswith(("\n", "\r\n")):
        text_value += newline
    local_env.parent.mkdir(parents=True, exist_ok=True)
    local_env.write_text(text_value + f"IDENTITY_PASSWORD={password}{newline}", encoding="utf-8")
    line("local_password", "generated")
    return "generated"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check or create development databases.")
    parser.add_argument("--create", action="store_true")
    parser.add_argument("--require-targets", action="store_true")
    parser.add_argument("--crm-database", default="aadi_crm_dev")
    parser.add_argument("--configure-crm-env", action="store_true")
    parser.add_argument("--generate-password", action="store_true")
    parser.add_argument("--local-env", type=Path, default=None)
    args = parser.parse_args()

    if args.generate_password:
        if args.local_env is None:
            fail("A local env path is required to generate a password.")
        generate_password(args.local_env)

    settings = load_control_plane()
    assert_development(settings)
    configured = make_url(settings.database_url).database or ""
    if args.crm_database == configured:
        fail("CRM and Control Plane database names are the same.")
    if not SAFE_NAME.fullmatch(args.crm_database) or "prod" in args.crm_database.lower():
        fail("CRM database name is not a safe development identifier.")

    host, port, crm_env_database, sslmode = crm_target_from_env()
    line("crm_env_host_loopback", host in LOOPBACK)
    line("crm_env_port", port)
    line("crm_env_database", crm_env_database)
    line("crm_env_sslmode", sslmode or "unset")
    if host not in LOOPBACK:
        fail("CRM database host is not loopback.")
    if sslmode == "disable" and host not in LOOPBACK:
        fail("CRM TLS disable is refused for a non-loopback host.")
    control_port = make_url(settings.database_url).port or 5432
    if port != control_port:
        fail("CRM and Control Plane are not on the same development port.")

    engine = maintenance_engine(settings)
    try:
        with engine.connect() as connection:
            version = str(connection.execute(text("SHOW server_version")).scalar()).split()[0]
            line("server_version", version)
            line("server_ssl", connection.execute(text("SHOW ssl")).scalar())
            role = connection.execute(
                text("SELECT usesuper, usecreatedb FROM pg_user WHERE usename = current_user")
            ).one()
            line("role_is_superuser", bool(role[0]))
            line("role_can_create_db", bool(role[1]))
            names = database_names(connection)
            for name in names:
                if "aadi" in name.lower() or "platform" in name.lower() or "crm" in name.lower():
                    count = table_count(settings, name) if SAFE_NAME.fullmatch(name) else "unreadable"
                    marker = "target" if name in {configured, args.crm_database} else "preserved"
                    line(f"{marker}_database", f"{name} tables={count}")
            if args.create:
                if not role[1]:
                    fail(
                        "The database role cannot create databases. "
                        f"Ask an administrator to create {configured} and {args.crm_database} "
                        "on the loopback PostgreSQL server. Do not paste a password into chat."
                    )
                line("control_plane_create", create_database(connection, configured))
                line("crm_create", create_database(connection, args.crm_database))
            current_names = database_names(connection)
            line("control_plane_exists", configured in current_names)
            line("crm_target_exists", args.crm_database in current_names)
            line("control_plane_tables", table_count(settings, configured))
            line("crm_target_tables", table_count(settings, args.crm_database))
            if args.require_targets and (
                configured not in current_names or args.crm_database not in current_names
            ):
                fail("A required development database does not exist. Creation was not attempted.")
    finally:
        engine.dispose()

    if args.configure_crm_env:
        line("crm_env_database_update", retarget_crm_env(args.crm_database))
        host, _port, database, _sslmode = crm_target_from_env()
        if database != args.crm_database:
            fail("CRM environment does not name the development database after configuration.")
        line("crm_env_database_now", database)
        line("crm_env_host_loopback_now", host in LOOPBACK)
    line("RESULT", "ok")


if __name__ == "__main__":
    main()
