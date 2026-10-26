"""Start one local API if it is not already answering /health.

The CRM process receives its database URL from the gitignored backend .env.
That URL is not printed.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
DETACHED = 0x00000008
NEW_GROUP = 0x00000200


def healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


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
    parser = argparse.ArgumentParser(description="Start a local development API.")
    parser.add_argument("--app", choices=("control-plane", "crm"), required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--health-path", default="/health")
    args = parser.parse_args()
    health = f"http://localhost:{args.port}{args.health_path}"
    if healthy(health):
        print(f"reused {args.app} api")
        return
    if args.app == "control-plane":
        backend = WORKSPACE / "MultiTenant" / "Aadi-MultiTenant-Platform" / "backend"
        env = os.environ.copy()
    else:
        backend = WORKSPACE / "Product" / "aadi-crm" / "backend"
        env = os.environ.copy()
        values = load_assignments(backend / ".env")
        for key in ("CRM_DATABASE_URL", "CRM_DATABASE_SSLMODE"):
            if values.get(key):
                env[key] = values[key]
        env["PLATFORM_API_BASE_URL"] = env.get("CONTROL_PLANE_API_BASE_URL", "http://localhost:8000")
    args.log.parent.mkdir(parents=True, exist_ok=True)
    log = args.log.open("a", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "localhost",
            "--port",
            str(args.port),
        ],
        cwd=backend,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=DETACHED | NEW_GROUP,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        if healthy(health):
            print(f"started {args.app} api pid={process.pid}")
            return
        if process.poll() is not None:
            print(f"FAILED {args.app} api exited before it became ready. See the log file.")
            raise SystemExit(1)
        time.sleep(0.5)
    print(f"FAILED {args.app} api did not become ready. See the log file.")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
