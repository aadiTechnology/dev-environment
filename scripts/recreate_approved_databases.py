"""Drop only aadi_platform and aadi_crm_dev after an exact approval file.

The approval file must contain these two lines and nothing else:

    APPROVE aadi_platform
    APPROVE aadi_crm_dev

Preserved databases are refused. A wildcard is refused. This script does not
create a database and does not print a password or connection string.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy.engine.url import make_url

WORKSPACE = Path(__file__).resolve().parents[2]
DEV = WORKSPACE / "dev-environment"
CONTROL_BACKEND = WORKSPACE / "MultiTenant" / "Aadi-MultiTenant-Platform" / "backend"
CRM_BACKEND = WORKSPACE / "Product" / "aadi-crm" / "backend"
APPROVED = ("aadi_platform", "aadi_crm_dev")
PRESERVED = {
    "aadi_platform_",
    "aadi_crm_",
    "aadi_platform_test",
    "aadi_platform_onboarding_test",
}
LOOPBACK = {"localhost", "127.0.0.1", "::1"}
APPROVAL_LINES = ("APPROVE aadi_platform", "APPROVE aadi_crm_dev")


def fail(message: str, code: int = 1) -> None:
    text_value = " ".join(message.split())
    if "://" in text_value or "password" in text_value.lower():
        print("FAILED Details were withheld because they included a secret or connection string.")
    else:
        print(f"FAILED {text_value}")
    raise SystemExit(code)


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


def approval_matches(path: Path) -> bool:
    if not path.is_file():
        return False
    lines = [raw.strip() for raw in path.read_text(encoding="utf-8").splitlines() if raw.strip()]
    return tuple(lines) == APPROVAL_LINES


def main() -> None:
    parser = argparse.ArgumentParser(description="Drop the two approved development databases.")
    parser.add_argument("--name", action="append", required=True)
    parser.add_argument("--approval-file", type=Path, required=True)
    args = parser.parse_args()
    requested = tuple(args.name)
    if requested != APPROVED:
        fail("Refusing recreation. The only allowed names, in order, are aadi_platform and aadi_crm_dev.", 2)
    if any(name in PRESERVED or any(char in name for char in "*?%\"';") for name in requested):
        fail("Refusing a preserved name or a wildcard. No database was dropped.", 2)
    if not approval_matches(args.approval_file):
        fail(
            "Approval file must contain exactly 'APPROVE aadi_platform' and 'APPROVE aadi_crm_dev'. "
            "No database was dropped.",
            2,
        )

    sys.path.insert(0, str(CONTROL_BACKEND))
    from app.core.config import get_settings, reset_settings_cache

    reset_settings_cache()
    settings = get_settings()
    if settings.environment != "development":
        fail("Control Plane ENVIRONMENT must be development. No database was dropped.")
    control = make_url(settings.database_url)
    if (control.host or "") not in LOOPBACK or control.database != "aadi_platform":
        fail("Control Plane is not the local aadi_platform database. No database was dropped.")
    crm_env = read_env(CRM_BACKEND / ".env")
    crm = make_url(crm_env.get("CRM_DATABASE_URL", ""))
    if (crm.host or "") not in LOOPBACK or crm.database != "aadi_crm_dev":
        fail("CRM is not the local aadi_crm_dev database. No database was dropped.")
    if control.port != crm.port:
        fail("The two development databases are not on the same local port. No database was dropped.")

    local = read_env(DEV / "config" / "dev.local.env")
    admin_url = local.get("CONTROL_PLANE_ADMIN_DATABASE_URL", "")
    if not admin_url:
        fail("The administrator URL is missing. No database was dropped.")
    admin = make_url(admin_url)
    if (admin.host or "") not in LOOPBACK or admin.database not in {"aadi_platform", "postgres"}:
        fail("The administrator URL is not a local development connection. No database was dropped.")

    import psycopg
    from psycopg import sql

    connection = psycopg.connect(
        admin.set(database="postgres").render_as_string(hide_password=False),
        sslmode="disable",
        connect_timeout=5,
        autocommit=True,
    )
    try:
        superuser = connection.execute(
            "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
        if not superuser or not superuser[0]:
            fail("The administrator role is not a superuser. No database was dropped.")
        existing = {
            row[0]
            for row in connection.execute("SELECT datname FROM pg_database WHERE datistemplate = false")
        }
        for preserved in PRESERVED:
            if preserved in requested:
                fail("A preserved database was requested. No database was dropped.")
        for name in APPROVED:
            if name not in existing:
                line("absent", name)
                continue
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
                (name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            line("dropped", name)
    finally:
        connection.close()
    line("RESULT", "ok")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        fail(type(exc).__name__)
