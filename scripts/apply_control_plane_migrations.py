"""Apply Control Plane migrations with the migration role when one is configured.

The runtime application URL stays in the gitignored backend env file. This
process uses the migrator URL only when that URL points at the local
development database. The URL is not printed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy.engine.url import make_url

WORKSPACE = Path(__file__).resolve().parents[2]
BACKEND = WORKSPACE / "MultiTenant" / "Aadi-MultiTenant-Platform" / "backend"
LOCAL_ENV = WORKSPACE / "dev-environment" / "config" / "dev.local.env"
LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def load_assignments(path: Path) -> dict[str, str]:
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


def main() -> None:
    migrator = load_assignments(LOCAL_ENV).get("CONTROL_PLANE_MIGRATOR_DATABASE_URL", "")
    if migrator:
        parsed = make_url(migrator)
        if (parsed.host or "") not in LOOPBACK or parsed.database != "aadi_platform":
            print("FAILED Control Plane migration URL is not the local development database.")
            raise SystemExit(1)
        os.environ["DATABASE_URL"] = migrator
    os.chdir(BACKEND)
    upgrade = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=False)
    if upgrade.returncode != 0:
        raise SystemExit(upgrade.returncode)
    current = subprocess.run([sys.executable, "-m", "alembic", "current"], check=False)
    raise SystemExit(current.returncode)


if __name__ == "__main__":
    main()
