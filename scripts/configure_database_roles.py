"""Create least-privilege development roles for the two target databases.

The existing superuser is left in place and is not modified. Preserved databases
are not opened, granted, revoked, or reassigned. Passwords are written only to
the gitignored local env file and are not printed.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from sqlalchemy.engine.url import make_url

WORKSPACE = Path(__file__).resolve().parents[2]
LOCAL_ENV = WORKSPACE / "dev-environment" / "config" / "dev.local.env"
CONTROL_ENV = WORKSPACE / "MultiTenant" / "Aadi-MultiTenant-Platform" / "backend" / ".env"
CRM_ENV = WORKSPACE / "Product" / "aadi-crm" / "backend" / ".env"
LOOPBACK = {"localhost", "127.0.0.1", "::1"}
OPENED_DATABASES = frozenset({"postgres", "aadi_platform", "aadi_crm_dev"})
RUNTIME_DATABASES = frozenset({"aadi_platform", "aadi_crm_dev"})
TARGETS = {
    "control_plane": {
        "database": "aadi_platform",
        "env_path": CONTROL_ENV,
        "env_key": "DATABASE_URL",
        "app_role": "aadi_platform_app",
        "migrator_role": "aadi_platform_migrator",
        "admin_key": "CONTROL_PLANE_ADMIN_DATABASE_URL",
        "app_key": "CONTROL_PLANE_APP_DATABASE_URL",
        "migrator_key": "CONTROL_PLANE_MIGRATOR_DATABASE_URL",
    },
    "crm": {
        "database": "aadi_crm_dev",
        "env_path": CRM_ENV,
        "env_key": "CRM_DATABASE_URL",
        "app_role": "aadi_crm_app",
        "migrator_role": "aadi_crm_migrator",
        "admin_key": "CRM_ADMIN_DATABASE_URL",
        "app_key": "CRM_APP_DATABASE_URL",
        "migrator_key": "CRM_MIGRATOR_DATABASE_URL",
    },
}


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


def replace_env_url(path: Path, key: str, username: str, password: str) -> str:
    original_lines = path.read_text(encoding="utf-8").splitlines()
    replaced = False
    rewritten: list[str] = []
    for raw in original_lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            rewritten.append(raw)
            continue
        current_key, current_value = stripped.split("=", 1)
        if current_key.strip() != key:
            rewritten.append(raw)
            continue
        current = make_url(current_value.strip().strip('"').strip("'"))
        updated = current.set(username=username, password=password)
        if (updated.host, updated.port, updated.database) != (current.host, current.port, current.database):
            fail(f"{key} host, port, or database would change. The file was not written.")
        rewritten.append(f"{key}={updated.render_as_string(hide_password=False)}")
        replaced = True
    if not replaced:
        fail(f"{path.name} has no {key} assignment.")
    path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    return "updated"


def assert_target(url_text: str, database: str) -> None:
    parsed = make_url(url_text)
    if (parsed.host or "") not in LOOPBACK:
        fail("Refusing a database host that is not loopback.")
    if parsed.database != database:
        fail(f"Refusing a database other than {database}.")


def role_password(local: dict[str, str], key: str) -> tuple[str, str]:
    existing = local.get(key, "")
    if existing:
        return existing, "present"
    return secrets.token_urlsafe(24), "generated"


def configure(connection, target: dict, local: dict[str, str]) -> None:
    from psycopg import sql

    database = target["database"]
    app_role = target["app_role"]
    migrator_role = target["migrator_role"]
    owners = [
        row[0]
        for row in connection.execute(
            """
            SELECT DISTINCT r.rolname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_roles r ON r.oid = c.relowner
            WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'S')
            ORDER BY 1
            """
        )
    ]
    allowed = {"postgres", migrator_role}
    unexpected = [owner for owner in owners if owner not in allowed]
    if unexpected:
        fail(f"{database} has objects owned by {', '.join(unexpected)}. Ownership was not changed.")
    relations = connection.execute(
        """
        SELECT c.relkind, c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_roles r ON r.oid = c.relowner
        WHERE n.nspname = 'public'
          AND r.rolname = 'postgres'
          AND c.relkind IN ('r', 'p', 'v', 'm', 'S')
        ORDER BY 1, 2
        """
    ).fetchall()
    for relkind, relname in relations:
        statement = "ALTER SEQUENCE public.{} OWNER TO {}" if relkind == "S" else "ALTER TABLE public.{} OWNER TO {}"
        connection.execute(
            sql.SQL(statement).format(sql.Identifier(relname), sql.Identifier(migrator_role))
        )
    line(f"{database}_ownership", f"transferred:{len(relations)}" if relations else "unchanged")
    functions = connection.execute(
        """
        SELECT p.oid::regprocedure::text
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_roles r ON r.oid = p.proowner
        WHERE n.nspname = 'public' AND r.rolname = 'postgres'
        ORDER BY 1
        """
    ).fetchall()
    for (signature,) in functions:
        safe = signature
        for char in "() ,_.":
            safe = safe.replace(char, "")
        if any(char in signature for char in ";-\"'") or not safe.isalnum():
            fail(f"{database} function signature was not transferred.")
        qualified = signature if "." in signature else f"public.{signature}"
        connection.execute(
            sql.SQL("ALTER FUNCTION {} OWNER TO {}").format(
                sql.SQL(qualified), sql.Identifier(migrator_role)
            )
        )
    if functions:
        line(f"{database}_functions", f"transferred:{len(functions)}")
    for role in (app_role, migrator_role):
        connection.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(database), sql.Identifier(role)
            )
        )
        connection.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role))
        )
    connection.execute(
        sql.SQL("GRANT CREATE ON SCHEMA public TO {}").format(sql.Identifier(migrator_role))
    )
    connection.execute(
        sql.SQL(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}"
        ).format(sql.Identifier(app_role))
    )
    connection.execute(
        sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(
            sql.Identifier(app_role)
        )
    )
    connection.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
        ).format(sql.Identifier(migrator_role), sql.Identifier(app_role))
    )
    connection.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
            "GRANT USAGE, SELECT ON SEQUENCES TO {}"
        ).format(sql.Identifier(migrator_role), sql.Identifier(app_role))
    )


def ensure_role(connection, role: str, password: str) -> str:
    from psycopg import sql

    exists = connection.execute(
        "SELECT rolsuper, rolcreatedb FROM pg_roles WHERE rolname = %s",
        (role,),
    ).fetchone()
    if exists:
        if exists[0] or exists[1]:
            fail(f"Role {role} exists with superuser or createdb. It was not changed.")
        return "reused"
    connection.execute(
        sql.SQL(
            "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE"
        ).format(sql.Identifier(role), sql.Literal(password))
    )
    return "created"


def connect(url_text: str, database: str):
    if database not in OPENED_DATABASES:
        fail(
            f"Refusing to open {database}. Role checks open only aadi_platform, "
            "aadi_crm_dev, and the maintenance database."
        )
    import psycopg

    parsed = make_url(url_text).set(drivername="postgresql", database=database)
    if (parsed.host or "") not in LOOPBACK:
        fail("Refusing a database host that is not loopback.")
    return psycopg.connect(
        parsed.render_as_string(hide_password=False),
        sslmode="disable",
        connect_timeout=5,
        autocommit=True,
    )


def assert_runtime(app_url: str, migrator_url: str, database: str) -> None:
    """Check least privilege on one development database.

    The runtime role must not be a superuser and must not be able to create a
    table. The migrator role must be able to create a table, and that probe is
    rolled back. Preserved databases are not part of this check.
    """

    if database not in RUNTIME_DATABASES:
        fail(f"Runtime checks apply only to aadi_platform and aadi_crm_dev, not {database}.")
    with connect(app_url, database) as connection:
        superuser = connection.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()
        if superuser[0]:
            fail(f"{database} runtime role is still a superuser.")
        connection.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
        try:
            connection.execute("CREATE TABLE dev_role_probe (id integer)")
        except Exception as exc:
            if "permission denied" not in str(exc).lower() and "InsufficientPrivilege" not in type(exc).__name__:
                fail(f"{database} runtime role failed for an unexpected reason during the create probe.")
        else:
            connection.execute("DROP TABLE dev_role_probe")
            fail(f"{database} runtime role was able to create a table.")
    with connect(migrator_url, database) as connection:
        connection.execute("BEGIN")
        connection.execute("CREATE TABLE dev_role_probe (id integer)")
        connection.execute("ROLLBACK")


def main() -> None:
    local = read_env(LOCAL_ENV)
    updates: dict[str, str] = {}
    control_url = local.get("CONTROL_PLANE_ADMIN_DATABASE_URL", read_env(CONTROL_ENV).get("DATABASE_URL", ""))
    if not control_url:
        fail("Control Plane database URL is missing.")
    assert_target(control_url, "aadi_platform")
    admin = connect(control_url, "postgres")
    try:
        current = admin.execute(
            "SELECT current_user, rolsuper FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
        line("admin_role", current[0])
        line("admin_is_superuser", bool(current[1]))
        if not current[1]:
            fail("The configured Control Plane role cannot create roles. No role was changed.")
        for target in TARGETS.values():
            source = read_env(target["env_path"]).get(target["env_key"], "")
            if not source:
                fail(f"{target['env_key']} is missing.")
            assert_target(source, target["database"])
            if target["admin_key"] not in local and make_url(source).username == "postgres":
                updates[target["admin_key"]] = source
            app_password, app_state = role_password(local, target["app_key"] + "_PASSWORD")
            migrator_password, migrator_state = role_password(local, target["migrator_key"] + "_PASSWORD")
            if app_state == "generated":
                updates[target["app_key"] + "_PASSWORD"] = app_password
            if migrator_state == "generated":
                updates[target["migrator_key"] + "_PASSWORD"] = migrator_password
            local.update(updates)
            line(target["app_role"], ensure_role(admin, target["app_role"], app_password))
            line(target["migrator_role"], ensure_role(admin, target["migrator_role"], migrator_password))
    finally:
        admin.close()

    if updates:
        upsert_env(LOCAL_ENV, updates)

    local = read_env(LOCAL_ENV)
    for name, target in TARGETS.items():
        source = read_env(target["env_path"])[target["env_key"]]
        admin_url = local.get(target["admin_key"], source)
        assert_target(admin_url, target["database"])
        with connect(admin_url, target["database"]) as connection:
            configure(connection, target, local)
        app_url = make_url(source).set(
            username=target["app_role"],
            password=local[target["app_key"] + "_PASSWORD"],
        ).render_as_string(hide_password=False)
        migrator_url = make_url(source).set(
            username=target["migrator_role"],
            password=local[target["migrator_key"] + "_PASSWORD"],
        ).render_as_string(hide_password=False)
        assert_target(app_url, target["database"])
        assert_target(migrator_url, target["database"])
        assert_runtime(app_url, migrator_url, target["database"])
        current_user = make_url(read_env(target["env_path"])[target["env_key"]]).username
        if current_user != target["app_role"]:
            replace_env_url(
                target["env_path"],
                target["env_key"],
                target["app_role"],
                local[target["app_key"] + "_PASSWORD"],
            )
            line(f"{name}_env", "runtime-role")
        else:
            line(f"{name}_env", "unchanged")
        upsert_env(
            LOCAL_ENV,
            {target["app_key"]: app_url, target["migrator_key"]: migrator_url},
        )
        line(f"{name}_runtime_role", target["app_role"])
        line(f"{name}_migration_role", target["migrator_role"])
    line("preserved_databases_opened", "none")
    line("RESULT", "ok")


if __name__ == "__main__":
    main()
