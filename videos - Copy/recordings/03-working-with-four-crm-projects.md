# Work with Preschool, Paneerwala, Space View, and Hiring

**Audience:** A person learning the Aadi Control Plane and Aadi CRM.

**Duration:** About 4 minutes (221.2 seconds in the file).

**Video file:** `dev-environment/videos/recordings/03-working-with-four-crm-projects.mp4`

**Learning objective:** A learner can open the four CRM projects, read each published form, and open one sample record in each project.

## What the recording shows

1. This lesson opens the four CRM projects: Preschool, Paneerwala, Space View, and Hiring. The sample people and phone numbers are fictional. We will not create a project, edit a form, or change a record. Sign in to CRM. The password stays hidden.
2. All four projects are active. Preschool is for school enquiries. Paneerwala is for paneer orders. Space View is for interior and space planning. Hiring is for candidates.
3. Open Preschool. The description says Expected Value is the opportunity amount. The project is active.
4. Open the Preschool form. The form builder lists the fields and shows buttons to edit or remove a field. We do not press them. Then open the published form. Every project starts with the same ten fields: Contact or Record Name, Contact Person, Phone Number, Lead Source, Status, Priority, Last Contact Date, Next Follow-up Date, Expected Value, and Notes. Phone Number uses the mobile field. Preschool then adds Number of Students, Number of Branches, and Product of Interest.
5. Preschool has four records. Riverside Tiny Steps came from the import file. Open Northside Learning Circle. The status is New, and the product of interest is Preschool ERP. We do not edit or archive the record.
6. Open Paneerwala. Expected Value is the opportunity. Order Amount is a separate field for the order. The published form adds Product or Variant, Quantity, Order Amount, and Payment Status. The variants are Fresh Paneer, Malai Paneer, and Other.
7. Paneerwala has three records. Open Evening Tiffin Co. The status is In Progress, the variant is Malai Paneer, and Order Amount is separate from Expected Value.
8. Open Space View. The extra fields are Service Type, Service Location, and Requirement Details. The service types are Interior Design, Space Planning, and Other.
9. Space View has three records. Open Maple Street Apartment. The service type is Interior Design, and the service location is Pune.
10. Open Hiring. Status, Recruitment Stage, and Recruitment Outcome are three different fields. Positions include Sales Resource, Accountant, Accounting and Sales, and Interior Designer.
11. Hiring has three records. Open Tara Menon. The status is Converted, the recruitment stage is Hired, and the recruitment outcome is Hired. Those three values answer different questions. The four projects and their sample records stay as they were.

## UI limitations

- The form builder can edit, move, or remove fields. This recording opens the published form and does not press those buttons.
- Records can be edited or archived from the record page. This recording only reads them.
- Sample people and phone numbers are fictional. Notes are marked as seed data.
- No project, form, or record is created.

## How this file was recorded

Chromium opened the local Control Plane at http://localhost:5173 and CRM at http://localhost:5174. Playwright recorded the browser viewport while the script clicked, typed, and scrolled. Narration was spoken by the Windows voice Microsoft Zira Desktop and mixed into the MP4. The development password was typed only into a masked password field.

The screenshots in `dev-environment/evidence/browser/` were not used as frames in this video.

No tenant, user, subscription, project, form, record, or follow-up was created or edited.
