# Video 1 — Safe development environment and database setup

**Title:** Check the Aadi development databases before you migrate

**Learning objective:** A new developer can confirm the tools, name the Control Plane and CRM databases, leave preserved databases untouched, and apply migrations.

**Intended audience:** A new Aadi developer.

**Duration:** About 5 minutes.

**Video file:** Not recorded in this workspace. Record this script as its own video. Do not combine it with videos 2, 3, or 4.

## Prerequisites

- The `AadiProduct` workspace is on the machine.
- Python 3.11+, Node.js, npm, and PostgreSQL 17 on loopback are installed.
- Both backend virtual environments exist, as described in `dev-environment/README.md`.
- `dev-environment/config/dev.local.env` exists and is gitignored.
- You can see the terminal. You cannot see a password, token, or connection string.

## Narration

Start with the workspace open and no database tool pointed at a production server.

> This lesson shows how an Aadi developer prepares a local machine. We check the tools and the repository paths. We then name the only two databases the bootstrap may use. We do not delete anything. Preserved databases stay as they are. After the names are confirmed, we apply the Control Plane and CRM migrations and check that the application login is separate from the migration login.

## Actions and what should appear

1. In PowerShell, go to `AadiProduct`.
   - **On screen:** The prompt shows the workspace path.
2. Run `.\dev-environment\tests\01_environment_setup.ps1`.
   - Do not add `-RecreateApprovedDatabases`.
   - **On screen:** `STEP prerequisites`, then `verified python`, `verified node`, `verified npm`, and `RESULT ok`.
3. Leave the inventory on screen.
   - **On screen:** `control_plane_database=aadi_platform` and `crm_env_database=aadi_crm_dev`.
   - **On screen:** preserved databases that exist on this server, with table counts. On the current machine that includes `aadi_platform_` and `aadi_crm_`. If `aadi_platform_test` or `aadi_platform_onboarding_test` is not on this server, the check says it was absent and was not created.
   - **On screen:** `CHECK blocked database-recreation`.
   - Say: "Those preserved names are not targets. The script did not drop `aadi_platform` or `aadi_crm_dev`, because that needs a separate written approval of those exact names."
4. Scroll to the migration steps.
   - **On screen:** Alembic reports the Control Plane head. CRM prints `crm_migrations database=aadi_crm_dev`.
5. Scroll to the role and revision lines.
   - **On screen:** `runtime_role_control_plane=aadi_platform_app` and `migration_role_control_plane=aadi_platform_migrator`.
   - **On screen:** `runtime_role_crm=aadi_crm_app` and `migration_role_crm=aadi_crm_migrator`.
   - **On screen:** each role line contains `superuser=False createdb=False createrole=False`.
   - **On screen:** `control_plane_revision_match=True` and `crm_migration_match=True`.
   - **On screen:** `table_owners database=aadi_platform match=True` and `table_owners database=aadi_crm_dev match=True`.
6. Show the last summary line.
   - **On screen:** `CHECK pass git-unchanged` and `SUMMARY pass=... fail=0 blocked=1`.
   - The blocked item is the recreation gate. It is the expected result for this recording.

## Optional recreation, not part of the normal recording

Stop the recording before any drop. Recreation is allowed only when a lead has approved the exact names `aadi_platform` and `aadi_crm_dev`, and the approval file contains only these two lines:

```text
APPROVE aadi_platform
APPROVE aadi_crm_dev
```

The file path is `dev-environment/evidence/database-recreation-approval.txt`. The command also has to pass `-RecreateApprovedDatabases -ApprovedDatabaseNames aadi_platform,aadi_crm_dev`. Any other name, including `aadi_platform_`, `aadi_crm_`, `aadi_platform_test`, and `aadi_platform_onboarding_test`, is refused. There is no wildcard cleanup.

## Expected successful result

The default command finishes with no failed checks. The recreation check stays blocked. Both development databases are still present, migrated, and owned for tables by their migration roles. The product git repositories are unchanged.

## Troubleshooting

- **A tool is missing.** Install the tool named in the `FAILED` line. Do not continue to a database command.
- **The host is not loopback.** Stop. Do not point this script at a remote server.
- **A preserved database is missing from the inventory.** Stop and investigate. Do not create a replacement with a broader command.
- **The recreation check is not blocked.** You passed the recreate switch. Stop unless the approval file and the two exact names were supplied on purpose.
- **A revision does not match.** Read the migration output above the summary. Run the same test again after fixing the local database. Do not downgrade the seeded database on camera.
- **A runtime role is a superuser.** Stop and tell the team. Do not grant that role access to a preserved database.

## Closing

> You have seen the safe setup path. The development databases are `aadi_platform` and `aadi_crm_dev`. Everything else on this server stayed in place. The next video seeds the Control Plane tenant through the API.

## Recording checklist

- Record only this test. Save the video separately from the other three.
- Hide `backend/.env`, `config/dev.local.env`, and any window that could show a connection string.
- Do not run `echo`, `cat`, or an editor on the local env file.
- Do not pass `-RecreateApprovedDatabases` in the normal take.
- Keep the preserved database names readable.
- Show the final `SUMMARY` line long enough to read the counts.
- Evidence to point at after the take:
  - `dev-environment/evidence/01-environment-setup.log`
  - `dev-environment/evidence/git-status-before.txt`
  - `dev-environment/evidence/git-status-after-test-01.txt`
- This repository does not contain an MP4 for this lesson.
