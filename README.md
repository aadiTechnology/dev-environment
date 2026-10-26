# Aadi development bootstrap

This directory sits beside the Control Plane and CRM repositories. It creates the local development databases, applies each application's own migrations, and seeds a development tenant through the existing HTTP APIs.

```text
AadiProduct/
├── MultiTenant/Aadi-MultiTenant-Platform/   Control Plane
├── Product/aadi-crm/                        CRM
└── dev-environment/                         this bootstrap
```

The Control Plane owns identity, tenants, products, features, plans, subscriptions, entitlements, and permissions. CRM owns projects, forms, records, follow-ups, and imports. CRM calls the Control Plane APIs. It does not read the Control Plane database.

The Control Plane model has tenants. It does not have a separate organization or workspace table, so the bootstrap does not create those records.

## Prerequisites

- Python 3.11 or newer, Node.js, and npm
- PostgreSQL 17 listening on loopback
- The Control Plane `backend/.env` with `ENVIRONMENT=development` and a loopback `DATABASE_URL`
- The CRM `backend/.env` with `CRM_DATABASE_URL` and `CRM_DATABASE_SSLMODE`
- Backend virtual environments:

```text
cd MultiTenant\Aadi-MultiTenant-Platform\backend
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"

cd ..\..\..\Product\aadi-crm\backend
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
```

Frontend dependencies:

```text
cd MultiTenant\Aadi-MultiTenant-Platform\frontend
npm install

cd ..\..\..\Product\aadi-crm\frontend
npm install
```

`CRM_DATABASE_SSLMODE=disable` is accepted only for a loopback host. Do not use it for a remote server.

## One-command bootstrap

From `AadiProduct`:

```powershell
.\dev-environment\bootstrap.ps1
```

That run only validates tools, paths, and the local database settings. It does not create databases or write seed data.

This command creates the missing development databases, migrates, seeds, and verifies:

```powershell
.\dev-environment\bootstrap.ps1 -Apply
```

`-Apply` is explicit. It does not drop or truncate a database. These switches can also be used on their own:

| Switch | Effect |
|---|---|
| `-CreateDatabases` | Create `aadi_platform` and `aadi_crm_dev` when they are missing |
| `-Migrate` | Alembic for the Control Plane, then `python -m app.migrate` for CRM |
| `-SeedControlPlane` | Development tenant, CRM catalog, subscription, membership, and role |
| `-SeedCrm` | Four projects, forms, sample records, follow-ups, and one import fixture |
| `-Verify` | Database checks and a signed-in CRM tenant-context request |
| `-GenerateLocalPassword` | Write `IDENTITY_PASSWORD` into gitignored `config/dev.local.env` when it is empty |

The password is not printed. Sign in with `crm.admin@example.test` and the value of `IDENTITY_PASSWORD` in `dev-environment/config/dev.local.env`. If that identity already exists and rejects the password, the bootstrap stops. It does not reset the password.

`-Apply` also adds the development user to `PLATFORM_ADMIN_USER_IDS` in the gitignored Control Plane `backend/.env` when the id is absent. Existing ids are kept. If the API was already running when that line changes, stop it and run the bootstrap again.

## Databases

The Control Plane uses the database named by its `DATABASE_URL`. On this workspace that name is `aadi_platform`. CRM bootstrap uses `aadi_crm_dev`.

`aadi_platform_`, `aadi_crm_`, and the other local databases are inspected and left unchanged. `aadi_crm` is not dropped. When the gitignored CRM `.env` still names the missing `aadi_crm` database, `-CreateDatabases` changes that name to `aadi_crm_dev` and keeps the rest of the URL.

Runtime connections use `aadi_platform_app` and `aadi_crm_app`. Those roles can change rows in their own development database and cannot create tables there. Role setup checks those two databases only. It does not open preserved databases and does not change their privileges. Migrations use `aadi_platform_migrator` and `aadi_crm_migrator`. The existing `postgres` role remains available for creating databases and is not dropped. Role passwords are generated into gitignored `config/dev.local.env` and are not printed.

Migrations are commands. Neither API runs them on a request.

## Seed identity

| Item | Value |
|---|---|
| Email | `crm.admin@example.test` |
| Tenant | `Aadi CRM Development` |
| Product key | `crm` |
| Plan key | `crm-development` |
| Role key | `crm_development` |

The tenant administrator role is assigned with the Control Plane bootstrap-admin API. The CRM role receives `crm.lead_management.read`, `crm.project_management.access`, `crm.records.access`, and `crm.project_management.manage`. Product access comes from the active subscription and entitlement evaluation. A project assignment stores the member's current Control Plane membership id. Audit navigation uses platform `audit.read` and is not granted by the CRM role.

Commercial features on the development plan are `lead_management`, `project_management`, and `records`.

## CRM forms

Each project form starts with the same ten fields, in this order: Contact / Record Name, Contact Person, Phone Number, Lead Source, Status, Priority, Last Contact Date, Next Follow-up Date, Expected Value, Notes.

Phone Number uses the CRM `mobile` field type. Expected Value is the opportunity amount. Paneerwala's Order Amount is a separate field.

Hiring keeps three different values:

- Status is the shared CRM pipeline.
- Recruitment Stage is the hiring step.
- Recruitment Outcome is the hiring result.

A hired candidate is stored as Status Converted, Recruitment Stage Hired, and Recruitment Outcome Hired. Position options reuse the roles already defined by the CRM hiring template: Sales Resource, Accountant, Accounting & Sales, and Interior Designer.

Paneerwala product options are Fresh Paneer, Malai Paneer, and Other. The CRM schema does not have a separate product catalog for that project.

Sample records use fictional names and `9100000…` phone numbers. Notes contain `seed:<key>`. Follow-ups are real CRM follow-up rows. One preschool CSV fixture is imported with the idempotency key `dev-preschool-import-v1`.

There is no reset command. A reset would delete rows. Run the bootstrap again; matching records and configuration are reused, and a conflicting existing row stops that step.

## Start the applications

Use `localhost` for the page and both APIs. `localhost` and `127.0.0.1` do not share the session cookie.

Control Plane API:

```text
cd MultiTenant\Aadi-MultiTenant-Platform\backend
.venv\Scripts\uvicorn app.main:app --host localhost --port 8000
```

Control Plane web, in another terminal:

```text
cd MultiTenant\Aadi-MultiTenant-Platform\frontend
npm run dev
```

The Vite default is `http://localhost:5173`. Sign in at `http://localhost:5173/login`.

CRM API. The process does not load `.env` by itself. Load the two CRM variables, then start it:

```text
cd Product\aadi-crm\backend
Get-Content .env | ForEach-Object {
  if ($_ -match '^(CRM_DATABASE_URL|CRM_DATABASE_SSLMODE)=(.*)$') {
    Set-Item -Path "env:$($Matches[1])" -Value $Matches[2]
  }
}
$env:PLATFORM_API_BASE_URL = "http://localhost:8000"
.venv\Scripts\uvicorn app.main:app --host localhost --port 8001
```

CRM web:

```text
cd Product\aadi-crm\frontend
npm run dev
```

CRM web is `http://localhost:5174`. Open the tenant printed in `dev-environment/config/seed-state.json`:

```text
http://localhost:5174/tenants/<tenant_id>/projects
```

The Control Plane allowlist already includes port 5174 in this workspace. Do not commit a CORS change.

Health and readiness for the Control Plane:

```text
GET http://localhost:8000/health
GET http://localhost:8000/ready
```

## Run steps separately

Migrations:

```text
cd MultiTenant\Aadi-MultiTenant-Platform\backend
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m alembic current
```

```text
cd Product\aadi-crm\backend
.venv\Scripts\python -m app.migrate
```

The CRM command reads `CRM_DATABASE_URL` from the process environment. Use the same `.env` load shown above.

Control Plane seed, from `MultiTenant\Aadi-MultiTenant-Platform\backend`, after `IDENTITY_PASSWORD` is set:

```text
.venv\Scripts\python scripts\seed_development_tenant.py prepare --state ..\..\..\dev-environment\config\seed-state.json
.venv\Scripts\uvicorn app.main:app --host localhost --port 8000
.venv\Scripts\python scripts\seed_development_tenant.py apply --state ..\..\..\dev-environment\config\seed-state.json
```

CRM seed, from `Product\aadi-crm\backend`, after both APIs are running:

```text
.venv\Scripts\python scripts\seed_development_projects.py --catalog ..\..\..\dev-environment\seeds\crm_seed.json --state ..\..\..\dev-environment\config\seed-state.json --fixture ..\..\..\dev-environment\seeds\fixtures\preschool-dev-import.csv
```

Verification, from `AadiProduct`, after the APIs are running and `IDENTITY_PASSWORD` is loaded from the gitignored local file:

```text
MultiTenant\Aadi-MultiTenant-Platform\backend\.venv\Scripts\python dev-environment\scripts\verify_bootstrap.py
```

Tests:

```text
cd dev-environment
..\MultiTenant\Aadi-MultiTenant-Platform\backend\.venv\Scripts\python -m unittest tests.test_seed_catalog

cd Product\aadi-crm\backend
.venv\Scripts\python -m pytest tests\test_development_seed.py

cd MultiTenant\Aadi-MultiTenant-Platform\backend
.venv\Scripts\python -m pytest tests\test_development_seed.py
```

Leave `CRM_DATABASE_URL` unset for the full CRM suite. Those tests use temporary SQLite files.

```text
cd Product\aadi-crm\backend
.venv\Scripts\python -m pytest
```

```text
cd MultiTenant\Aadi-MultiTenant-Platform\backend
.venv\Scripts\python -m pytest
```

```text
cd Product\aadi-crm\frontend
npm test

cd MultiTenant\Aadi-MultiTenant-Platform\frontend
npm test
```

## Four learning tests

A new developer can follow four separate lessons. Each lesson has a script under `tests/` and a video script under `videos/`. The video scripts are the narration and recording checklist. They are not recorded MP4 files.

| Lesson | Run | Video script |
|---|---|---|
| Environment and databases | `.\dev-environment\tests\01_environment_setup.ps1` | `videos/01_environment_setup.md` |
| Control Plane seed | `.\dev-environment\tests\02_control_plane_seed.ps1` | `videos/02_control_plane_seed.md` |
| CRM projects and forms | `.\dev-environment\tests\03_crm_seed.ps1` | `videos/03_crm_projects_and_forms.md` |
| Both applications | `.\dev-environment\tests\04_end_to_end.ps1` | `videos/04_end_to_end_developer_setup.md` |

Run them from `AadiProduct`. The default commands do not drop a database. Test 1 creates `aadi_platform` or `aadi_crm_dev` only when that name is missing. Preserved databases stay out of every command.

Recreation is a separate switch, `-RecreateApprovedDatabases`, and it also requires `-ApprovedDatabaseNames aadi_platform,aadi_crm_dev` plus an approval file at `evidence/database-recreation-approval.txt` containing only:

```text
APPROVE aadi_platform
APPROVE aadi_crm_dev
```

Any other name is refused. Do not create that file until those two names have been approved for deletion.

Sanitized logs are written to `dev-environment/evidence/`. The overall result of a run belongs in `EXECUTION_REPORT.md`.

## Preserved local databases

PostgreSQL 17 on this machine listens on port 5433. The configured Control Plane database `aadi_platform` was not present before the bootstrap. `aadi_platform_` and `aadi_crm_` already contained rows and are not used. The server TLS setting and listen addresses are not changed.
