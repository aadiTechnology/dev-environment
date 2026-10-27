# Video 2 — Control Plane bootstrap and seed

**Title:** Seed the Aadi CRM Development tenant

**Learning objective:** A new developer can see how the Control Plane seed creates or reuses the development user, tenant, CRM product, plan, subscription, membership, and permissions, and how a second run avoids duplicates.

**Intended audience:** A new Aadi developer.

**Duration:** About 5 minutes.

**Video file:** Not recorded in this workspace. Record this script as its own video.

## Prerequisites

- Video 1 has been watched, or `tests/01_environment_setup.ps1` has already passed.
- `aadi_platform` exists and is migrated.
- The Control Plane API can listen on `http://localhost:8000`.
- The gitignored local config contains the development password. Do not open that file on camera.

## Narration

> The Control Plane keeps identity, tenants, products, plans, subscriptions, and permissions. This product does not have a separate organization table or a workspace table. A page may say "organization" where the stored record is a tenant. The seed uses the HTTP API. We run it twice and the second run reuses the same rows.

## Actions and what should appear

1. From `AadiProduct`, run `.\dev-environment\tests\02_control_plane_seed.ps1`.
   - **On screen:** `CHECK pass identity-password present in this process only`. The password value does not appear.
2. Show the migration step.
   - **On screen:** Alembic is at the current head and the step exits 0.
3. Show the prepare and API lines.
   - **On screen:** `reused identity` or, on a brand-new database only, `created identity`.
   - **On screen:** `present platform-admin-allowlist` when the development user is already listed.
   - **On screen:** `reused control-plane api` or `started control-plane api`.
4. Show the first seed.
   - **On screen:** `reused` or `created` for the product, features, plan, tenant, subscription, and role, then `verified product-access` and `verified control-plane-seed`.
5. Show the second seed.
   - **On screen:** lines begin with `reused` or `verified`. There is no line that starts with `created`.
   - **On screen:** `CHECK pass control-plane-idempotent`.
6. Show the read-only counts.
   - **On screen:**
     - `organization_tables=0`
     - `workspace_tables=0`
     - `identity_count=1`
     - `tenant_count=1`
     - `product_crm_count=1`
     - `plan_count=1`
     - `subscription_active_count=1`
     - `membership_count=1`
     - `role_count=1`
     - `plan_features=lead_management,project_management,records`
     - `permission crm.lead_management.read=present`
     - `permission crm.project_management.manage=present`
     - `permission roles.manage=present`
     - `entitlement_tables=0`
   - Say: "Entitlements are calculated from the active subscription when the API is called. They are not a second copy of the plan."
7. Show `SUMMARY` with `fail=0`.

## Expected successful result

One development user, `crm.admin@example.test`, belongs to the tenant `Aadi CRM Development`. The CRM product, the `crm-development` plan, and one active subscription exist. The second seed does not insert another copy. No database was dropped.

## Troubleshooting

- **`RESTART_REQUIRED control-plane-api`.** The platform-admin allowlist changed while the API was already running. Stop that process yourself and run this test again. The test will not kill it.
- **Sign-in failed.** Confirm the local password file exists. Reset is not part of this lesson. Do not print the password.
- **A count is not 1.** Stop. A duplicate tenant, product, plan, or membership needs a person to look at the row. Do not delete the database to remove it.
- **`organization_tables` is not 0.** Stop. This seed must not invent an organization or workspace record.
- **The API port is busy for another project.** Stop. Do not change the port in a committed file during this lesson.

## Closing

> The platform configuration is in place, and running the seed again is safe. The next video creates the four CRM projects in the CRM database.

## Recording checklist

- Record this test by itself.
- Do not open `dev.local.env`, `backend/.env`, or a database console that shows a connection string.
- Keep the second seed visible long enough to show there is no `created` line.
- Keep `organization_tables=0` and `workspace_tables=0` readable.
- Evidence to show at the end: `dev-environment/evidence/02-control-plane-seed.log`.
- This repository does not contain an MP4 for this lesson.
