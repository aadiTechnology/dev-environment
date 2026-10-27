# Video 3 — CRM projects, forms, and sample records

**Title:** Seed Preschool, Paneerwala, Space View, and Hiring

**Learning objective:** A new developer can see the four CRM projects, the shared ten fields, each project's own fields, the synthetic records, and a second seed that does not duplicate them.

**Intended audience:** A new Aadi developer.

**Duration:** About 6 minutes.

**Video file:** Not recorded in this workspace. Record this script as its own video.

## Prerequisites

- Videos 1 and 2 are done, or the Control Plane tenant from video 2 already exists.
- `aadi_crm_dev` is the CRM database. It is not `aadi_crm` and it is not `aadi_crm_`.
- The Control Plane API is on `http://localhost:8000` and the CRM API can use `http://localhost:8001`.
- The seed catalog is `dev-environment/seeds/crm_seed.json`. This lesson does not change it.

## Narration

> CRM stores projects, forms, and records in its own database. It asks the Control Plane for the tenant. It does not read the Control Plane tables. Each project form starts with the same ten fields. Preschool, Paneerwala, Space View, and Hiring then add only their own fields. The sample people and phone numbers are fictional. We seed twice. The second run finds the same forms and records.

## Actions and what should appear

1. From `AadiProduct`, run `.\dev-environment\tests\03_crm_seed.ps1`.
   - **On screen:** `crm_migrations database=aadi_crm_dev`.
   - **On screen:** both APIs are `reused` or `started`.
2. Show the first seed.
   - **On screen:** `verified crm-shell`.
   - **On screen:** `reused project PRESCHOOL`, `reused project PANEERWALA`, `reused project SPACE-VIEW`, and `reused project HIRING`, or `created` only when that project was absent.
   - **On screen:** `verified crm-seed`.
3. Show the second seed.
   - **On screen:** project, form, field, record, follow-up, and import lines say `reused`.
   - **On screen:** `CHECK pass crm-idempotent` and `CHECK pass crm-counts-unchanged`.
4. Read the shared field order for one project, then point out that every project reports the same match.
   - **On screen:** `field_order code=PRESCHOOL match=True`, and the same for `PANEERWALA`, `SPACE-VIEW`, and `HIRING`.
   - Say the ten shared labels in order: Contact / Record Name, Contact Person, Phone Number, Lead Source, Status, Priority, Last Contact Date, Next Follow-up Date, Expected Value, Notes.
   - Say: "Phone Number is the CRM mobile field. Expected Value is the opportunity amount."
5. Name the extra fields while their match lines are visible.
   - **Preschool:** Number of Students, Number of Branches, Product of Interest. Options include Preschool ERP, School ERP, and Other.
   - **Paneerwala:** Product / Variant, Quantity, Order Amount, Payment Status. Variants are Fresh Paneer, Malai Paneer, and Other. Order Amount is not Expected Value.
   - **Space View:** Service Type, Service Location, Requirement Details. Service types are Interior Design, Space Planning, and Other.
   - **Hiring:** Position Applied For, Recruitment Stage, Recruitment Outcome. Positions are Sales Resource, Accountant, Accounting & Sales, and Interior Designer.
   - Say: "Hiring keeps Status, Recruitment Stage, and Recruitment Outcome as three different fields. A hired candidate is Status Converted, Recruitment Stage Hired, and Recruitment Outcome Hired."
6. Show the counts.
   - **On screen:** one project and one form for each code.
   - **On screen:** `count records_PRESCHOOL=4`, `count records_PANEERWALA=3`, `count records_SPACE-VIEW=3`, `count records_HIRING=3`.
   - **On screen:** `import_record=present`. The fourth preschool record is the fictional import `Riverside Tiny Steps`.
   - **On screen:** `project_tenant code=PRESCHOOL match=True` and the same match for the other three codes.
   - **On screen:** follow-up lines for `preschool-01`, `preschool-02`, `paneerwala-02`, `space-view-01`, and `hiring-02` say `present`.
7. Show `SUMMARY` with `fail=0`.

## Expected successful result

All four projects belong to the Aadi CRM Development tenant. Each form has the ten shared fields first and only its own extra fields after them. Synthetic records and follow-ups are present. The import fixture is present once. The second seed creates nothing.

## Troubleshooting

- **CRM migrations name another database.** Stop. Do not retarget the URL by hand on camera. The supported target is `aadi_crm_dev`.
- **`field_order` is false.** The form already in the database does not match the catalog. The seed will not overwrite a conflicting form. Do not edit the form builder during this lesson.
- **A record count is higher than the catalog.** Someone added a row. Report the count. Do not delete records from the database with a broad SQL statement.
- **The second run prints `created`.** The idempotent seed missed an existing row. Stop and keep the log.
- **The shell cannot see the tenant.** Video 2 has not finished, or the API on port 8000 is not the Control Plane.

## Closing

> The CRM development data is ready. The next video starts both applications, signs in, and runs the test suites.

## Recording checklist

- Record this test by itself.
- You may show `seeds/crm_seed.json` and the fictional names. Do not show credentials.
- Pause on each project's field-order line.
- Keep the record counts and the idempotent check on screen.
- Evidence to show: `dev-environment/evidence/03-crm-seed.log`.
- This repository does not contain an MP4 for this lesson.
