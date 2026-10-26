# Bootstrap execution report

Workspace: `AadiProduct`. No commits, pushes, or database drops were made. Product repository working trees stayed clean.

## Four learning tests

The developer lesson scripts under `videos/` are prepared. Those four lessons were not recorded as MP4 files. The separate user-training recordings are in the section below.

| Test | Procedure | Video script | Execution | Pass / fail / blocked | Evidence | Video recorded |
|---|---|---|---|---|---|---|
| 1. Environment and databases | `tests/01_environment_setup.ps1` | `videos/01_environment_setup.md` | Completed | 33 pass, 0 fail, 1 blocked | `evidence/01-environment-setup.log` | No |
| 2. Control Plane seed | `tests/02_control_plane_seed.ps1` | `videos/02_control_plane_seed.md` | Completed | 25 pass, 0 fail, 0 blocked | `evidence/02-control-plane-seed.log` | No |
| 3. CRM projects and forms | `tests/03_crm_seed.ps1` | `videos/03_crm_projects_and_forms.md` | Completed | 41 pass, 0 fail, 0 blocked | `evidence/03-crm-seed.log` | No |
| 4. Both applications | `tests/04_end_to_end.ps1` | `videos/04_end_to_end_developer_setup.md` | Completed with failures | 26 pass, 6 fail, 0 blocked | `evidence/04-end-to-end.log` | No |

The blocked check in test 1 is the recreation gate. `aadi_platform` and `aadi_crm_dev` were not dropped. Approval for those exact names was not given.

A separate browser run, after the locator fix, signed in and matched all four forms. Screenshots are in `evidence/browser/`. That follow-up is not part of the test 4 summary line above.

## Databases seen on this server

PostgreSQL 17.4 is on loopback port 5433. `ssl` is off. The inventory user is a superuser and can create databases. Runtime roles are not superusers and cannot create databases.

| Name | Class | Owner | Public tables | What happened |
|---|---|---|---|---|
| `aadi_platform` | Control Plane development target | `postgres` | 21 | Absent at the start of this session. Created because it was missing, then migrated to `f4a8c2e1b907`. Not dropped. |
| `aadi_crm_dev` | CRM development target | `postgres` | 13 | Absent at the start of this session. Created because it was missing, then all 8 CRM PostgreSQL migrations were applied. Not dropped. |
| `aadi_platform_` | Preserved | `postgres` | 21 | Left unchanged. Runtime read was denied. |
| `aadi_crm_` | Preserved | `postgres` | 13 | Left unchanged. Runtime read was denied. |
| `aadi_platform_test` | Preserved when present | — | — | Not on this server. Not created. |
| `aadi_platform_onboarding_test` | Preserved when present | — | — | Not on this server. Not created. |
| `tenant-subscription-platform` | Unclassified | `postgres` | unreadable | The hyphenated name was not opened. It was not dropped or granted. |

Table owners inside the two targets are `aadi_platform_migrator` and `aadi_crm_migrator`. The API env files use `aadi_platform_app` and `aadi_crm_app`. Those roles are `NOSUPERUSER`, `NOCREATEDB`, and `NOCREATEROLE`.

The Control Plane has no `organization` or `workspace` table. A screen that says "organization" is showing a tenant. Entitlements are evaluated from the subscription. There is no entitlement table.

## Seed that is now in the development databases

The development user is `crm.admin@example.test`. The tenant is **Aadi CRM Development**, id `32b4b86c-0103-463e-89c1-f951b3ff9a7c`. The previous id in `config/seed-state.json` was not in the empty database, so the supported seed created this tenant and wrote the new id. Counts are one user, one tenant, one CRM product, one `crm-development` plan, one active subscription, and one membership. Plan features are `lead_management`, `project_management`, and `records`. The user has `crm.lead_management.read`, `crm.project_management.manage`, and `roles.manage`.

CRM has one form for each of Preschool, Paneerwala, Space View, and Hiring. The ten shared fields are first. Record counts are 4, 3, 3, and 3, including the preschool import fixture. A second seed reused every project, form, record, and follow-up.

The second `bootstrap.ps1 -Apply` printed `RESULT ok` and did not create another copy. Preserved table counts and seeded row counts were unchanged. Both product git repositories were still clean.

## Test 4 failures from the executed summary

The script exited 1. These six checks failed in that run:

| Check | Result |
|---|---|
| Control Plane web port probe | Failed the IPv4 connect. `http://localhost:5173/login` then returned HTTP 200. The page was up on localhost. |
| CRM web port probe | Same pattern. `http://localhost:5174/` returned HTTP 200. |
| Browser sign-in inside the script | Sign-in reached the tenant, then the locator matched the tenant name more than once. |
| Control Plane `pytest` | 456 passed, 14 failed, 15 errors. |
| `aadi_platform_test` present | Absent. Not created. |
| `aadi_platform_onboarding_test` present | Absent. Not created. |

Suites that passed in the same run:

| Suite | Result |
|---|---|
| `tests.test_seed_catalog` | 5 passed |
| Control Plane `tests/test_development_seed.py` | 2 passed |
| CRM `tests/test_development_seed.py` | 3 passed |
| CRM `pytest` with `CRM_DATABASE_URL` unset | 87 passed, 6 skipped |
| CRM `npm test` | 55 passed |
| Control Plane `npm test` | 213 passed |

The Control Plane backend failures are migration and audit tests that refuse to migrate `aadi_platform`, plus last-admin concurrency tests. They were not pointed at `aadi_platform_test`. Downgrades were not retried against the seeded database. After the suite, the second bootstrap still passed and the seed counts matched the snapshot taken before the suites.

API verification in the same run signed in, confirmed CRM access, and read all four projects, their fields, records, follow-ups, and the import fixture.

The browser follow-up opened the Control Plane, showed **CRM is available** for **Aadi CRM Development**, listed Preschool, Paneerwala, Space View, and Hiring, and matched each form's labels in order. The password was not printed and is not visible in the screenshots.

## User-training videos

Four user-journey MP4 files were recorded from the running local applications. Chromium was driven against the Control Plane at `http://localhost:5173` and CRM at `http://localhost:5174`. The picture is 1600×900 H.264, and the narration is AAC from the Windows voice Microsoft Zira Desktop. The development tenant **Aadi CRM Development** and the existing synthetic CRM records were used. Databases were not dropped or reseeded. No tenant, user, subscription, project, form, record, or follow-up was created or edited. Product code was not changed.

The password was typed only into a masked password field. A frame from the second video shows the email `crm.admin@example.test` and a row of dots in the password box. No password, token, or other secret is spoken or written in the narration scripts.

Screenshots in `evidence/browser/` were not used as video frames. The developer lesson scripts `videos/01_environment_setup.md`, `videos/02_control_plane_seed.md`, `videos/03_crm_projects_and_forms.md`, and `videos/04_end_to_end_developer_setup.md` are still not MP4 files.

The recorder allowed only login, logout, and session renew as non-GET requests. Each completed take reported no other writes. `videos/recordings/verification-summary.json` is the output of the last take, so it lists only the fourth video.

| Journey | Video | Narration script | Duration | Size | Recorder writes |
|---|---|---|---|---|---|
| Tenant onboarding and CRM access | `videos/recordings/01-tenant-onboarding-and-crm-access.mp4` | `videos/recordings/01-tenant-onboarding-and-crm-access.md` | 185.2 s | 4,513,143 bytes | None outside login, logout, and renew |
| User access and sign-in | `videos/recordings/02-user-access-and-sign-in.mp4` | `videos/recordings/02-user-access-and-sign-in.md` | 123.1 s | 2,830,264 bytes | None outside login, logout, and renew |
| Working with the four CRM projects | `videos/recordings/03-working-with-four-crm-projects.mp4` | `videos/recordings/03-working-with-four-crm-projects.md` | 221.2 s | 5,918,529 bytes | None outside login, logout, and renew |
| Dashboard and lead tracking | `videos/recordings/04-dashboard-and-lead-tracking.mp4` | `videos/recordings/04-dashboard-and-lead-tracking.md` | 172.0 s | 2,821,783 bytes | None outside login, logout, and renew |

Frame checks from the files:

- Video 1 shows the Control Plane home with tenant context **Aadi CRM Development**, the onboarding subscription step for the existing CRM Development subscription, and the message that assigning again is blocked. A later frame shows **CRM is available** for organization Aadi CRM Development. The entitlement signature was not loaded.
- Video 2 shows the Control Plane sign-in page, then the users directory. The membership row for `crm.admin@example.test` is active and lists CRM Development (`crm_development`). The access summary lists `crm.lead_management.read`, `crm.project_management.manage`, and `roles.manage`. After sign-out, the sign-in page is empty. CRM then lists **Aadi CRM Development** under Organizations, and CRM sign-out returns its own sign-in page. Sampled frames of the Roles page still said "Loading roles"; the role name is readable on the users page and in the access summary.
- Video 3 shows the published Preschool form, including Number of Students, Number of Branches, and Product of Interest. The published Paneerwala form says Expected Value is the opportunity and Order Amount is the order. The published Hiring form says Status, Recruitment Stage, and Recruitment Outcome are different fields. The Tara Menon record shows Status Converted, Recruitment Stage Hired, and Recruitment Outcome Hired. The recorder also required Riverside Tiny Steps, Northside Learning Circle, Evening Tiffin Co, and Maple Street Apartment to be visible before it continued. Some sampled list frames were still loading.
- Video 4 shows the CRM overview, which only says CRM is available. There is no page named Dashboard. Project KPIs for Preschool shows "The request could not be completed" with Retry, and the same message remains. The Leads page says "No leads are open in this shell." Preschool follow-ups due today say "No follow-ups are due today" and "Showing 0 of 0". The overdue queue shows Hillview Kids Campus, due 2026-10-01, "Showing 1 of 1". The upcoming queue shows Northside Learning Circle, due 2026-11-20, "Showing 1 of 1". The Preschool record PRESCHOOL-0001 shows Status New and Next Follow-up Date 2026-11-20. No KPI count was invented.

UI limits that the recordings show, and do not work around:

- On localhost, the Control Plane and CRM share the sign-in session. Video 1 opens CRM already signed in. Video 2 signs out of the Control Plane first, and CRM then asks for the password. `localhost` and `127.0.0.1` do not share that session.
- The word organization on these screens is the tenant. There is no separate organization record.
- Onboarding can create a tenant, product, plan, or subscription. The recording selects the existing ones and does not submit those forms. Load entitlements was not pressed, because that result includes a signature.
- Creating a new global account is not available. The recording does not add a user or change a role.
- The form builder and record pages can edit or archive data. The recording only reads the published forms and records.
- There is no Dashboard page. The Leads page does not list the four projects' records.
- Preschool Project KPIs fails on screen. Retry does not show counts. The sentence that record status is not counted appears only on a successful report, so it is not in the video.
- Follow-up queues use India Standard Time. On 25 October 2026 the today queue for Preschool is empty.

## Outstanding blockers

- Database recreation is still waiting for written approval of the exact names `aadi_platform` and `aadi_crm_dev`. No other name can be approved by that file.
- The Control Plane backend suite is not green while `DATABASE_URL` names `aadi_platform` and the runtime role.
- The four developer lesson scripts in `dev-environment/videos/` still have no MP4 files. The four user-training videos in `dev-environment/videos/recordings/` are recorded.
- `tenant-subscription-platform` is an extra local database. It was not identified as a bootstrap target and was not modified.

## Earlier report

An earlier run on this workspace reported a seeded `aadi_platform` and the preserved test databases `aadi_platform_test` and `aadi_platform_onboarding_test`. At the start of this session those three names were not on PostgreSQL 17.4 port 5433. `aadi_platform_` and `aadi_crm_` were present and were left alone. This session did not drop the missing names. It created only the two approved development targets because they were absent.
