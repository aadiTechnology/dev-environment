"""Verify development databases, catalog seed, and one CRM tenant-context request.

Does not print passwords or connection strings.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

WORKSPACE = Path(__file__).resolve().parents[2]
DEV = WORKSPACE / "dev-environment"
CONTROL_BACKEND = WORKSPACE / "MultiTenant" / "Aadi-MultiTenant-Platform" / "backend"
CRM_BACKEND = WORKSPACE / "Product" / "aadi-crm" / "backend"
LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def fail(message: str) -> None:
    print(f"FAILED {message}")
    raise SystemExit(1)


def status(action: str, subject: str) -> None:
    print(f"{action} {subject}")


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        fail(f"Could not load {path.name}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def env_assignments(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def alembic_head() -> str:
    revisions = {}
    parents = set()
    for path in (CONTROL_BACKEND / "migrations" / "versions").glob("*.py"):
        revision = None
        down = None
        for raw in path.read_text(encoding="utf-8").splitlines():
            if raw.startswith("revision"):
                revision = raw.split("=", 1)[1].strip().strip('"').strip("'")
            if raw.startswith("down_revision"):
                down = raw.split("=", 1)[1].strip()
        if revision:
            revisions[revision] = down
            if down and down not in {"None", "none"}:
                parents.add(down.strip('"').strip("'"))
    heads = [revision for revision in revisions if revision not in parents]
    if len(heads) != 1:
        fail("Control Plane migrations do not have one head.")
    return heads[0]


def verify_databases(crm_database: str) -> None:
    os.chdir(CONTROL_BACKEND)
    sys.path.insert(0, str(CONTROL_BACKEND))
    from app.core.config import get_settings, reset_settings_cache

    reset_settings_cache()
    settings = get_settings()
    if settings.environment != "development":
        fail("Control Plane environment is not development.")
    control = make_url(settings.database_url)
    if (control.host or "") not in LOOPBACK:
        fail("Control Plane database host is not loopback.")
    crm_values = env_assignments(CRM_BACKEND / ".env")
    os.environ["CRM_DATABASE_URL"] = crm_values["CRM_DATABASE_URL"]
    os.environ["CRM_DATABASE_SSLMODE"] = crm_values.get("CRM_DATABASE_SSLMODE", "")
    from urllib.parse import urlparse

    crm = urlparse(os.environ["CRM_DATABASE_URL"])
    if (crm.hostname or "") not in LOOPBACK:
        fail("CRM database host is not loopback.")
    if crm.path.lstrip("/") != crm_database:
        fail("CRM is not configured for the development database.")
    if control.database == crm_database:
        fail("Control Plane and CRM use the same database.")
    status("verified", f"control-plane-database {control.database}")
    status("verified", f"crm-database {crm_database}")
    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        versions = [row[0] for row in connection.execute(text("SELECT version_num FROM alembic_version"))]
    engine.dispose()
    head = alembic_head()
    if versions != [head]:
        fail(f"Control Plane migration is {versions or 'missing'}, expected {head}.")
    status("verified", f"control-plane-migration {head}")
    import psycopg

    try:
        crm_connection = psycopg.connect(
            crm_values["CRM_DATABASE_URL"],
            sslmode=crm_values.get("CRM_DATABASE_SSLMODE") or "verify-full",
            connect_timeout=5,
        )
    except Exception:
        fail("Could not connect to the CRM development database.")
    try:
        applied = {row[0] for row in crm_connection.execute("SELECT version FROM crm_schema_migrations")}
    finally:
        crm_connection.close()
    expected = {path.name for path in (CRM_BACKEND / "migrations" / "postgres").glob("*.sql")}
    if applied != expected:
        fail("CRM migrations do not match the PostgreSQL scripts.")
    status("verified", f"crm-migrations {len(applied)}")


def verify_integration(state: dict, catalog: dict) -> None:
    import httpx

    password = os.environ.get("IDENTITY_PASSWORD", "")
    if not password:
        fail("IDENTITY_PASSWORD is not set, so the signed-in CRM request was not sent.")
    platform = os.environ.get("CONTROL_PLANE_API_BASE_URL", "http://localhost:8000").rstrip("/")
    crm = os.environ.get("CRM_API_BASE_URL", "http://localhost:8001").rstrip("/")
    comparer = load_module(
        CRM_BACKEND / "scripts" / "seed_development_projects.py",
        "crm_seed",
    )
    with httpx.Client(timeout=30.0) as client:
        login = client.post(
            f"{platform}/api/v1/auth/login",
            json={"email": state["email"], "password": password},
        )
        if login.status_code != 200:
            fail("Control Plane sign-in failed during verification.")
        if not client.cookies.get("aadi_csrf") or not client.cookies.get("aadi_session"):
            fail("Control Plane sign-in did not return session cookies.")
        tenant_id = state["tenant_id"]
        access = client.get(f"{platform}/api/v1/tenants/{tenant_id}/products/crm/access")
        if access.status_code != 200 or access.json().get("available") is not True:
            fail("CRM product access is not available.")
        status("verified", "product-access")
        permissions = client.get(
            f"{platform}/api/v1/tenants/{tenant_id}/permissions",
        )
        keys = set(permissions.json())
        for key in ("crm.lead_management.read", "crm.project_management.manage", "roles.manage"):
            if key not in keys:
                fail(f"Missing permission {key}.")
        status("verified", "permissions")
        shell = client.get(f"{crm}/api/v1/shell/tenants/{tenant_id}")
        if shell.status_code != 200 or shell.json().get("available") is not True:
            fail("CRM shell did not return tenant context.")
        if shell.json().get("tenant_id") != tenant_id:
            fail("CRM shell returned a different tenant.")
        status("verified", "crm-shell")
        leads = client.get(f"{crm}/api/v1/shell/tenants/{tenant_id}/leads")
        if leads.status_code != 200:
            fail("CRM leads route did not accept the session.")
        status("verified", "crm-leads")
        projects = client.get(f"{crm}/api/v1/tenants/{tenant_id}/projects")
        if projects.status_code != 200:
            fail("CRM projects were not readable.")
        found = {item["code"]: item for item in projects.json().get("items", [])}
        required = {project["code"] for project in catalog["projects"]}
        if not required.issubset(found):
            fail("The four development projects are not all present.")
        status("verified", "projects 4")
        for project in catalog["projects"]:
            project_id = found[project["code"]]["id"]
            forms = client.get(
                f"{crm}/api/v1/tenants/{tenant_id}/projects/{project_id}/forms",
            )
            form = next(item for item in forms.json().get("items", []) if item["name"] == project["form_name"])
            desired = list(catalog["common_fields"]) + list(project["extra_fields"])
            if comparer.compare_fields(form.get("fields") or [], desired) != "match":
                fail(f"{project['name']} form fields do not match the seed.")
            records = client.get(
                f"{crm}/api/v1/tenants/{tenant_id}/projects/{project_id}/records",
                params={"limit": 100},
            )
            names = {item["display_name"] for item in records.json().get("items", [])}
            for record in project["records"]:
                if record["values"]["contact_record_name"] not in names:
                    fail(f"Missing record {record['seed_key']}.")
                if record.get("follow_up"):
                    detail = next(
                        item
                        for item in records.json()["items"]
                        if item["display_name"] == record["values"]["contact_record_name"]
                    )
                    follow_ups = client.get(
                        f"{crm}/api/v1/tenants/{tenant_id}/projects/{project_id}/records/{detail['id']}/follow-ups",
                    )
                    summaries = {item.get("summary") for item in follow_ups.json().get("items", [])}
                    if record["follow_up"]["summary"] not in summaries:
                        fail(f"Missing follow-up {record['seed_key']}.")
            status("verified", f"project {project['code']}")
        import_name = catalog["import_fixture"]["row"]["contact_record_name"]
        preschool = found["PRESCHOOL"]["id"]
        imported = client.get(
            f"{crm}/api/v1/tenants/{tenant_id}/projects/{preschool}/records",
            params={"q": import_name, "limit": 10},
        )
        if not any(item.get("display_name") == import_name for item in imported.json().get("items", [])):
            fail("Import fixture record is missing.")
        status("verified", "import-fixture")


def main() -> None:
    state = json.loads((DEV / "config" / "seed-state.json").read_text(encoding="utf-8"))
    catalog = json.loads((DEV / "seeds" / "crm_seed.json").read_text(encoding="utf-8"))
    verify_databases(os.environ.get("CRM_DATABASE_NAME", "aadi_crm_dev"))
    verify_integration(state, catalog)
    status("verified", "bootstrap")


if __name__ == "__main__":
    main()
