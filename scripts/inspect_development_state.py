"""Read-only inventory of the local development databases.

Prints names, owners, table counts, roles, migration revisions, and seed
counts. It does not create, drop, grant, update, or print a password or
connection string.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

WORKSPACE = Path(__file__).resolve().parents[2]
DEV = WORKSPACE / "dev-environment"
CONTROL_BACKEND = WORKSPACE / "MultiTenant" / "Aadi-MultiTenant-Platform" / "backend"
CRM_BACKEND = WORKSPACE / "Product" / "aadi-crm" / "backend"
PRESERVED = (
    "aadi_platform_",
    "aadi_crm_",
    "aadi_platform_test",
    "aadi_platform_onboarding_test",
)
PURPOSES = {
    "aadi_platform": "Control Plane development database. Candidate for recreation only after exact approval.",
    "aadi_crm_dev": "CRM development database. Candidate for recreation only after exact approval.",
    "aadi_platform_": "Preserved local database. Not a bootstrap target.",
    "aadi_crm_": "Preserved local database. Not a bootstrap target.",
    "aadi_platform_test": "Preserved Control Plane test database. Bootstrap and these tests do not migrate it.",
    "aadi_platform_onboarding_test": "Preserved onboarding test database. Bootstrap and these tests do not migrate it.",
}
APP_ROLES = {
    "aadi_platform": "aadi_platform_app",
    "aadi_crm_dev": "aadi_crm_app",
}
MIGRATOR_ROLES = {
    "aadi_platform": "aadi_platform_migrator",
    "aadi_crm_dev": "aadi_crm_migrator",
}
PROJECT_CODES = ("PRESCHOOL", "PANEERWALA", "SPACE-VIEW", "HIRING")


def fail(message: str) -> None:
    text_value = " ".join(message.split())
    lowered = text_value.lower()
    if "://" in text_value or "password" in lowered or "secret" in lowered:
        print("FAILED The check stopped. Details were withheld because they included a secret or connection string.")
    else:
        print(f"FAILED {text_value}")
    raise SystemExit(1)


def line(key: str, value: object) -> None:
    rendered = str(value)
    if "://" in rendered or "password=" in rendered.lower():
        fail(f"{key} produced a connection string. It was not printed.")
    print(f"{key}={value}")


def load_databases():
    path = DEV / "scripts" / "databases.py"
    spec = importlib.util.spec_from_file_location("dev_databases", path)
    if spec is None or spec.loader is None:
        fail("Could not load databases.py.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def username_of(url_text: str, label: str) -> str:
    try:
        parsed = make_url(url_text)
    except Exception as exc:
        fail(f"{label} could not be read ({type(exc).__name__}).")
    if not parsed.username:
        fail(f"{label} has no database user.")
    return parsed.username


def alembic_head() -> str:
    revisions: dict[str, str | None] = {}
    parents: set[str] = set()
    for path in (CONTROL_BACKEND / "migrations" / "versions").glob("*.py"):
        revision = None
        down = None
        for raw in path.read_text(encoding="utf-8").splitlines():
            if raw.startswith("revision"):
                revision = raw.split("=", 1)[1].strip().strip('"').strip("'")
            elif raw.startswith("down_revision"):
                down = raw.split("=", 1)[1].strip()
        if revision:
            revisions[revision] = down
            if down and down not in {"None", "none"}:
                parents.add(down.strip('"').strip("'"))
    heads = [revision for revision in revisions if revision not in parents]
    if len(heads) != 1:
        fail("Control Plane migrations do not have one head.")
    return heads[0]


def scalar(connection, statement: str, **params: object) -> int:
    value = connection.execute(text(statement), params).scalar()
    return int(value or 0)


def inspect_control_plane(connection, tenant_name: str, email: str) -> None:
    organization = scalar(
        connection,
        """
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema = 'public'
          AND lower(table_name) IN ('organization', 'organizations')
        """,
    )
    workspace = scalar(
        connection,
        """
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema = 'public'
          AND lower(table_name) IN ('workspace', 'workspaces')
        """,
    )
    entitlement = scalar(
        connection,
        """
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema = 'public' AND lower(table_name) LIKE '%entitlement%'
        """,
    )
    line("organization_tables", organization)
    line("workspace_tables", workspace)
    line("entitlement_tables", entitlement)
    line("count organization_tables", organization)
    line("count workspace_tables", workspace)
    if organization or workspace:
        names = [
            row[0]
            for row in connection.execute(
                text(
                    """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND (
                        lower(table_name) LIKE '%organization%'
                        OR lower(table_name) LIKE '%workspace%'
                      )
                    ORDER BY table_name
                    """
                )
            )
        ]
        line("schema_note", ",".join(names) or "none")

    line("identity_count", scalar(connection, "SELECT count(*) FROM users WHERE lower(email) = :email", email=email))
    line("count identity", scalar(connection, "SELECT count(*) FROM users WHERE lower(email) = :email", email=email))
    line(
        "tenant_count",
        scalar(connection, "SELECT count(*) FROM tenants WHERE name = :name", name=tenant_name),
    )
    line("count tenant", scalar(connection, "SELECT count(*) FROM tenants WHERE name = :name", name=tenant_name))
    line("product_crm_count", scalar(connection, "SELECT count(*) FROM products WHERE key = 'crm'"))
    line("count product_crm", scalar(connection, "SELECT count(*) FROM products WHERE key = 'crm'"))
    line(
        "plan_count",
        scalar(
            connection,
            """
            SELECT count(*) FROM plans pl
            JOIN products p ON p.id = pl.product_id
            WHERE p.key = 'crm' AND pl.key = 'crm-development'
            """,
        ),
    )
    line(
        "count plan",
        scalar(
            connection,
            """
            SELECT count(*) FROM plans pl
            JOIN products p ON p.id = pl.product_id
            WHERE p.key = 'crm' AND pl.key = 'crm-development'
            """,
        ),
    )
    line(
        "subscription_active_count",
        scalar(
            connection,
            """
            SELECT count(*) FROM product_subscriptions s
            JOIN tenants t ON t.id = s.tenant_id
            JOIN products p ON p.id = s.product_id
            WHERE t.name = :name AND p.key = 'crm' AND s.status = 'active'
            """,
            name=tenant_name,
        ),
    )
    line(
        "count subscription_active",
        scalar(
            connection,
            """
            SELECT count(*) FROM product_subscriptions s
            JOIN tenants t ON t.id = s.tenant_id
            JOIN products p ON p.id = s.product_id
            WHERE t.name = :name AND p.key = 'crm' AND s.status = 'active'
            """,
            name=tenant_name,
        ),
    )
    line(
        "membership_count",
        scalar(
            connection,
            """
            SELECT count(*) FROM tenant_memberships m
            JOIN users u ON u.id = m.user_id
            JOIN tenants t ON t.id = m.tenant_id
            WHERE lower(u.email) = :email AND t.name = :name AND m.status = 'active'
            """,
            email=email,
            name=tenant_name,
        ),
    )
    line(
        "count membership",
        scalar(
            connection,
            """
            SELECT count(*) FROM tenant_memberships m
            JOIN users u ON u.id = m.user_id
            JOIN tenants t ON t.id = m.tenant_id
            WHERE lower(u.email) = :email AND t.name = :name AND m.status = 'active'
            """,
            email=email,
            name=tenant_name,
        ),
    )
    line(
        "role_count",
        scalar(
            connection,
            """
            SELECT count(*) FROM roles r
            JOIN tenants t ON t.id = r.tenant_id
            WHERE t.name = :name AND r.key = 'crm_development'
            """,
            name=tenant_name,
        ),
    )
    line(
        "count role_crm_development",
        scalar(
            connection,
            """
            SELECT count(*) FROM roles r
            JOIN tenants t ON t.id = r.tenant_id
            WHERE t.name = :name AND r.key = 'crm_development'
            """,
            name=tenant_name,
        ),
    )
    features = [
        row[0]
        for row in connection.execute(
            text(
                """
                SELECT f.key
                FROM plan_features pf
                JOIN plans pl ON pl.id = pf.plan_id
                JOIN products p ON p.id = pl.product_id
                JOIN features f ON f.id = pf.feature_id
                WHERE p.key = 'crm' AND pl.key = 'crm-development'
                ORDER BY f.key
                """
            )
        )
    ]
    line("plan_features", ",".join(features))
    permissions = {
        row[0]
        for row in connection.execute(
            text(
                """
                SELECT DISTINCT perm.key
                FROM role_assignments ra
                JOIN users u ON u.id = ra.user_id
                JOIN tenants t ON t.id = ra.tenant_id
                JOIN role_permissions rp ON rp.role_id = ra.role_id
                JOIN permissions perm ON perm.id = rp.permission_id
                WHERE lower(u.email) = :email AND t.name = :name
                """
            ),
            {"email": email, "name": tenant_name},
        )
    }
    for key in ("crm.lead_management.read", "crm.project_management.manage", "roles.manage"):
        line(f"permission {key}", "present" if key in permissions else "missing")
    line("count granted_permissions", len(permissions))


def option_pairs(config_json: str) -> list[tuple[str, str]]:
    try:
        parsed = json.loads(config_json or "{}")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, dict):
        return []
    options = parsed.get("options") or []
    pairs = []
    for item in options:
        if isinstance(item, dict):
            pairs.append((str(item.get("value")), str(item.get("label"))))
    return pairs


def currency_code(config_json: str) -> str | None:
    try:
        parsed = json.loads(config_json or "{}")
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and isinstance(parsed.get("currency_code"), str):
        return parsed["currency_code"]
    return None


def inspect_crm(crm_url: str, sslmode: str, catalog: dict, tenant_id: str) -> None:
    import psycopg

    try:
        connection = psycopg.connect(crm_url, sslmode=sslmode or "verify-full", connect_timeout=5)
    except Exception as exc:
        fail(f"Could not connect to the CRM development database ({type(exc).__name__}).")
    try:
        applied = {row[0] for row in connection.execute("SELECT version FROM crm_schema_migrations")}
        expected = sorted(path.name for path in (CRM_BACKEND / "migrations" / "postgres").glob("*.sql"))
        line("crm_migration_count", len(applied))
        line("crm_migration_expected", len(expected))
        line("crm_migration_match", applied == set(expected))
        for version in expected:
            line(f"crm_migration {version}", "applied" if version in applied else "missing")

        for code in PROJECT_CODES:
            projects = connection.execute(
                "SELECT id, tenant_id FROM projects WHERE code = %s ORDER BY id",
                (code,),
            ).fetchall()
            line(f"count projects_{code}", len(projects))
            if len(projects) != 1:
                line(f"project_tenant code={code} match", False)
                line(f"field_order code={code} match", False)
                continue
            project_id, project_tenant = projects[0]
            line(f"project_tenant code={code} match", project_tenant == tenant_id)
            forms = connection.execute(
                "SELECT id, name FROM form_definitions WHERE project_id = %s ORDER BY name",
                (project_id,),
            ).fetchall()
            line(f"count forms_{code}", len(forms))
            project = next(item for item in catalog["projects"] if item["code"] == code)
            named = [item for item in forms if item[1] == project["form_name"]]
            if len(named) != 1:
                line(f"field_order code={code} match", False)
                line(f"dropdowns code={code} match", False)
                continue
            rows = connection.execute(
                """
                SELECT position, field_key, label, field_type, required, config_json
                FROM form_fields
                WHERE form_id = %s
                ORDER BY position, field_key
                """,
                (named[0][0],),
            ).fetchall()
            expected_fields = list(catalog["common_fields"]) + list(project["extra_fields"])
            match = len(rows) == len(expected_fields)
            dropdowns = True
            if match:
                for index, spec in enumerate(expected_fields):
                    position, field_key, label, field_type, required, config_json = rows[index]
                    if position != index or field_key != spec["field_key"] or label != spec["label"]:
                        match = False
                        break
                    if field_type != spec["field_type"] or bool(required) != bool(spec["required"]):
                        match = False
                        break
                    if spec.get("options") and option_pairs(config_json) != [tuple(item) for item in spec["options"]]:
                        dropdowns = False
                    if spec.get("currency_code") and currency_code(config_json) != spec["currency_code"]:
                        match = False
                        break
            line(f"field_order code={code} match", match)
            line(f"dropdowns code={code} match", dropdowns and match)
            line(f"count fields_{code}", len(rows))
            records = connection.execute(
                """
                SELECT display_name FROM records
                WHERE project_id = %s AND deleted_at IS NULL
                """,
                (project_id,),
            ).fetchall()
            names = {row[0] for row in records}
            line(f"count records_{code}", len(records))
            for record in project["records"]:
                display_name = record["values"]["contact_record_name"]
                line(f"record {record['seed_key']}", "present" if display_name in names else "missing")
                if record.get("follow_up"):
                    found = connection.execute(
                        """
                        SELECT count(*) FROM follow_ups f
                        JOIN records r ON r.id = f.record_id
                        WHERE r.project_id = %s AND r.display_name = %s AND f.summary = %s
                        """,
                        (project_id, display_name, record["follow_up"]["summary"]),
                    ).fetchone()
                    line(f"follow_up {record['seed_key']}", "present" if found and found[0] == 1 else "missing")
            fixture = catalog.get("import_fixture") or {}
            if fixture.get("project_code") == code:
                imported = fixture["row"]["contact_record_name"]
                line("import_record", "present" if imported in names else "missing")
            members = connection.execute(
                """
                SELECT count(*) FROM project_memberships
                WHERE project_id = %s AND status = 'active'
                """,
                (project_id,),
            ).fetchone()
            line(f"count project_members_{code}", int(members[0] if members else 0))
    finally:
        connection.close()


def main() -> None:
    databases = load_databases()
    settings = databases.load_control_plane()
    databases.assert_development(settings)
    control_name = make_url(settings.database_url).database or ""
    if control_name != "aadi_platform":
        fail("Control Plane database is not aadi_platform. Nothing was changed.")
    host, port, crm_name, sslmode = databases.crm_target_from_env()
    line("crm_database", crm_name)
    line("crm_host_loopback", host in databases.LOOPBACK)
    line("crm_port", port)
    if crm_name != "aadi_crm_dev":
        fail("CRM database is not aadi_crm_dev. Nothing was changed.")
    if host not in databases.LOOPBACK:
        fail("CRM database host is not loopback.")
    line("databases_distinct", control_name != crm_name)
    line("recreation_policy", "explicit-names-only")
    line("wildcard_cleanup", "disabled")

    local = read_env(DEV / "config" / "dev.local.env")
    public = read_env(DEV / "config" / "dev.env.example")
    tenant_name = local.get("TENANT_NAME") or public.get("TENANT_NAME") or "Aadi CRM Development"
    email = (local.get("CRM_ADMIN_EMAIL") or public.get("CRM_ADMIN_EMAIL") or "crm.admin@example.test").lower()
    state_path = DEV / "config" / "seed-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    tenant_id = str(state.get("tenant_id") or "")
    line("seed_state", "present" if tenant_id else "missing")
    if tenant_id:
        line("development_tenant_id", tenant_id)

    engine = databases.maintenance_engine(settings)
    try:
        with engine.connect() as connection:
            names = databases.database_names(connection)
            for name in names:
                lowered = name.lower()
                if "aadi" not in lowered and "platform" not in lowered and "crm" not in lowered:
                    continue
                if name in {"aadi_platform", "aadi_crm_dev"}:
                    marker = "target"
                elif name in PRESERVED:
                    marker = "preserved"
                else:
                    marker = "unclassified"
                owner = connection.execute(
                    text("SELECT pg_catalog.pg_get_userbyid(datdba) FROM pg_database WHERE datname = :name"),
                    {"name": name},
                ).scalar()
                count = databases.table_count(settings, name)
                rendered_count = "unreadable" if count is None else count
                purpose = PURPOSES.get(name, "Not approved for deletion or recreation.")
                line(f"database class={marker} name={name} owner={owner} tables={rendered_count} purpose", purpose)
                line(f"count tables_{name}", rendered_count)
            roles = list(APP_ROLES.values()) + list(MIGRATOR_ROLES.values())
            found_roles = {
                row[0]: (bool(row[1]), bool(row[2]), bool(row[3]))
                for row in connection.execute(
                    text(
                        """
                        SELECT rolname, rolsuper, rolcreatedb, rolcreaterole
                        FROM pg_roles
                        WHERE rolname IN (:app_cp, :mig_cp, :app_crm, :mig_crm)
                        """
                    ),
                    {
                        "app_cp": "aadi_platform_app",
                        "mig_cp": "aadi_platform_migrator",
                        "app_crm": "aadi_crm_app",
                        "mig_crm": "aadi_crm_migrator",
                    },
                )
            }
            for role in roles:
                flags = found_roles.get(role)
                if flags is None:
                    line(f"role {role}", "missing")
                    continue
                line(
                    f"role {role}",
                    f"superuser={flags[0]} createdb={flags[1]} createrole={flags[2]}",
                )
    finally:
        engine.dispose()

    control_env = read_env(CONTROL_BACKEND / ".env")
    crm_env = read_env(CRM_BACKEND / ".env")
    runtime_control = username_of(control_env.get("DATABASE_URL", ""), "Control Plane runtime URL")
    runtime_crm = username_of(crm_env.get("CRM_DATABASE_URL", ""), "CRM runtime URL")
    migration_control = username_of(
        local.get("CONTROL_PLANE_MIGRATOR_DATABASE_URL", ""),
        "Control Plane migration URL",
    )
    migration_crm = username_of(local.get("CRM_MIGRATOR_DATABASE_URL", ""), "CRM migration URL")
    line("runtime_role_control_plane", runtime_control)
    line("migration_role_control_plane", migration_control)
    line("runtime_role_crm", runtime_crm)
    line("migration_role_crm", migration_crm)
    line("roles_separate_control_plane", runtime_control != migration_control)
    line("roles_separate_crm", runtime_crm != migration_crm)

    control_engine = create_engine(settings.database_url)
    try:
        with control_engine.connect() as connection:
            versions = [row[0] for row in connection.execute(text("SELECT version_num FROM alembic_version"))]
            head = alembic_head()
            line("control_plane_revision", ",".join(versions) or "missing")
            line("control_plane_head", head)
            line("control_plane_revision_match", versions == [head])
            for database, migrator in MIGRATOR_ROLES.items():
                owners = [
                    row[0]
                    for row in connection.execute(
                        text(
                            """
                            SELECT r.rolname
                            FROM pg_class c
                            JOIN pg_namespace n ON n.oid = c.relnamespace
                            JOIN pg_roles r ON r.oid = c.relowner
                            WHERE n.nspname = 'public' AND c.relkind = 'r' AND current_database() = :database
                            GROUP BY r.rolname
                            ORDER BY r.rolname
                            """
                        ),
                        {"database": database},
                    )
                ] if database == control_name else []
                if database == control_name:
                    line(f"table_owners database={database}", ",".join(owners) or "none")
                    line(f"table_owners database={database} match", owners == [migrator])
            try:
                inspect_control_plane(connection, tenant_name, email)
            except Exception as exc:
                line("control_plane_catalog", f"unavailable {type(exc).__name__}")
    finally:
        control_engine.dispose()

    crm_engine = create_engine(make_url(settings.database_url).set(database=crm_name))
    try:
        with crm_engine.connect() as connection:
            owners = [
                row[0]
                for row in connection.execute(
                    text(
                        """
                        SELECT r.rolname
                        FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        JOIN pg_roles r ON r.oid = c.relowner
                        WHERE n.nspname = 'public' AND c.relkind = 'r'
                        GROUP BY r.rolname
                        ORDER BY r.rolname
                        """
                    )
                )
            ]
            line("table_owners database=aadi_crm_dev", ",".join(owners) or "none")
            line("table_owners database=aadi_crm_dev match", owners == [MIGRATOR_ROLES["aadi_crm_dev"]])
    except Exception as exc:
        line("table_owners database=aadi_crm_dev", f"unavailable {type(exc).__name__}")
    finally:
        crm_engine.dispose()

    catalog = json.loads((DEV / "seeds" / "crm_seed.json").read_text(encoding="utf-8"))
    if not tenant_id:
        line("crm_catalog", "skipped-no-tenant")
    else:
        try:
            inspect_crm(crm_env["CRM_DATABASE_URL"], crm_env.get("CRM_DATABASE_SSLMODE", sslmode), catalog, tenant_id)
        except SystemExit:
            raise
        except Exception as exc:
            line("crm_catalog", f"unavailable {type(exc).__name__}")
    line("RESULT", "ok")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        fail(f"{type(exc).__name__}")
