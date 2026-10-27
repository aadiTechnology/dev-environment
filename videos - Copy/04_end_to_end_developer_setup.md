# Video 4 — End-to-end developer experience

**Title:** Run both Aadi applications and prove the seed still holds

**Learning objective:** A new developer can start the Control Plane and CRM, sign in, open the four projects and their forms, call the CRM API as that tenant, run the test suites, and run the bootstrap a second time without losing the development databases.

**Intended audience:** A new Aadi developer.

**Duration:** About 6 minutes on camera. The test suites take longer than that. Show their summary lines, not every passing test.

**Video file:** Not recorded in this workspace. Record this script as its own video. A green API check is not a substitute for this recording.

## Prerequisites

- Videos 1 through 3 are done.
- Use `localhost` for the pages and both APIs. `localhost` and `127.0.0.1` do not share the session cookie.
- Ports: Control Plane API `8000`, CRM API `8001`, Control Plane web `5173`, CRM web `5174`.
- The development password stays in the gitignored local file. The person recording types it into the password box, which must stay masked.

## Narration

> This is the path a developer uses after the databases are seeded. We start the two APIs and the two web applications with the documented commands. We sign in as the fictional development user, open Aadi CRM Development, and look at all four projects. We then run the automated checks, including the suites that are allowed to fail, and we run the bootstrap again. A second bootstrap reuses the seed. It does not drop a database.

## Actions and what should appear

1. From `AadiProduct`, start the recording and run `.\dev-environment\tests\04_end_to_end.ps1`.
   - Leave this running. Switch to the browser for the next steps while the suites run, or record the browser pass that the script saves under `dev-environment/evidence/browser/`.
2. Show the health lines when they appear.
   - **On screen:** `CHECK pass control-plane-health`, `CHECK pass control-plane-ready`, `CHECK pass crm-openapi`, `CHECK pass control-plane-web`, and `CHECK pass crm-web`.
3. In the browser, open `http://localhost:5173/login`.
   - **On screen:** The heading "Sign in" and the fields Email and Password.
   - Type `crm.admin@example.test`. Type the password from the local file. Do not read it aloud and do not reveal the characters.
   - **On screen:** The Control Plane home lists **Aadi CRM Development**.
4. Open `http://localhost:5173/tenants/<tenant_id>/products/crm`, using the tenant id printed by the test as `development_tenant_id`.
   - **On screen:** "CRM is available" and the organization name **Aadi CRM Development**. The word organization on this page is the tenant.
5. Open `http://localhost:5174/tenants/<tenant_id>/projects`.
   - If CRM asks you to sign in again, use the same email and masked password.
   - **On screen:** Preschool, Paneerwala, Space View, and Hiring.
6. Open Forms for each project and show the canvas.
   - **On screen for every project:** Contact / Record Name through Notes, in that order.
   - **Then only the extra fields for that project:** Preschool's student and branch fields, Paneerwala's variant and order amount, Space View's service fields, or Hiring's position, stage, and outcome.
7. Return to the terminal and show the API result.
   - **On screen:** `verified product-access`, `verified permissions`, `verified projects 4`, one `verified project` line for each code, and `verified bootstrap`.
8. Show each suite summary. Read the counts exactly. Do not call a failed suite a pass.
   - **On screen:** `SUITE dev-environment-catalog`, `SUITE control-plane-seed-tests`, `SUITE crm-seed-tests`, `SUITE crm-backend`, `SUITE control-plane-backend`, `SUITE crm-frontend`, and `SUITE control-plane-frontend`.
   - The full logs are in `dev-environment/evidence/04-*.log`.
9. Show the second bootstrap.
   - **On screen:** `RESULT ok`, `CHECK pass bootstrap-second-run`, and `CHECK pass bootstrap-idempotent`.
   - **On screen:** the preserved databases still have their table counts, and `aadi_platform` and `aadi_crm_dev` are still present.
10. Show the final `SUMMARY`. If `fail` is not zero, say which checks failed. Do not describe the run as fully successful while a suite or the browser check is failed or blocked.

## Expected successful result

Both applications are reachable on localhost. The development user can see the tenant, the CRM product, the four projects, and the form fields. The CRM API accepts the session. The focused seed tests pass. The second bootstrap reuses the seed and leaves every named database in place.

The full Control Plane backend suite is expected to report failures while it is pointed at `aadi_platform`. That is an outstanding blocker, not a reason to run it against `aadi_platform_test`.

## Troubleshooting

- **The browser stays on the login page.** Use `localhost`, not `127.0.0.1`. Confirm the API on port 8000 is the Control Plane.
- **CRM says the product is not available.** Return to video 2. Do not create a second tenant.
- **A project or field is missing.** Return to video 3. Do not add a field in the form builder during this lesson.
- **`browser-sign-in` is blocked.** From the Control Plane frontend, run `npx playwright install chromium`, then run the test again. Until Chromium is installed, record the browser steps by hand. Do not claim the browser passed.
- **Control Plane `pytest` fails.** Record the failed and error counts from the suite line. Leave `aadi_platform_test` and `aadi_platform_onboarding_test` untouched.
- **The second bootstrap prints `created`.** The seed was not idempotent. Keep the log and do not drop the database.
- **A preserved table count changes.** Stop and report it. The bootstrap is not allowed to write to those databases.

## Closing

> You can now set up the local Control Plane and CRM, prove the seed, and run the same checks again. Database recreation stays behind an explicit approval of `aadi_platform` and `aadi_crm_dev` only.

## Recording checklist

- Record this test by itself. Four short videos are easier to follow than one long one.
- Mask the password. Do not paste it into the terminal.
- Crop the recording if a network panel shows a cookie or an authorization header.
- Visit all four projects. A screenshot of the project list is not enough for the video.
- Show the suite summary even when the Control Plane backend suite fails.
- Show that no database was dropped.
- Evidence to show:
  - `dev-environment/evidence/04-end-to-end.log`
  - `dev-environment/evidence/04-control-plane-backend-pytest.log`
  - `dev-environment/evidence/04-crm-backend-pytest.log`
  - `dev-environment/evidence/04-control-plane-frontend-vitest.log`
  - `dev-environment/evidence/04-crm-frontend-vitest.log`
  - `dev-environment/evidence/browser/` when the browser check ran
  - `dev-environment/evidence/git-status-after-test-04.txt`
- An MP4 was not generated by the automated run.
