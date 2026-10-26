"""Apply CRM PostgreSQL migrations from the gitignored backend environment file.

Prints the database name only.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
BACKEND = WORKSPACE / "Product" / "aadi-crm" / "backend"
ENV_PATH = BACKEND / ".env"
LOCAL_ENV = WORKSPACE / "dev-environment" / "config" / "dev.local.env"
LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def load_assignments(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> None:
    if not ENV_PATH.is_file():
        print("FAILED CRM backend .env is missing.")
        raise SystemExit(1)
    values = load_assignments(ENV_PATH)
    migrator = load_assignments(LOCAL_ENV).get("CRM_MIGRATOR_DATABASE_URL", "")
    if migrator:
        from urllib.parse import urlparse

        parsed = urlparse(migrator)
        if (parsed.hostname or "") not in LOOPBACK or parsed.path.lstrip("/") != "aadi_crm_dev":
            print("FAILED CRM migration URL is not the local development database.")
            raise SystemExit(1)
        os.environ["CRM_DATABASE_URL"] = migrator
    for key in ("CRM_DATABASE_URL", "CRM_DATABASE_SSLMODE"):
        if key not in os.environ and values.get(key):
            os.environ[key] = values[key]
    if not os.environ.get("CRM_DATABASE_URL"):
        print("FAILED CRM_DATABASE_URL is not set.")
        raise SystemExit(1)
    sys.path.insert(0, str(BACKEND))
    from app.db import apply_postgres_migrations

    database_name = apply_postgres_migrations()
    print(f"crm_migrations database={database_name}")


if __name__ == "__main__":
    main()
