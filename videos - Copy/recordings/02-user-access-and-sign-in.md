# Sign in and review user access

**Audience:** A person learning the Aadi Control Plane and Aadi CRM.

**Duration:** About 2 minutes (123.1 seconds in the file).

**Video file:** `dev-environment/videos/recordings/02-user-access-and-sign-in.mp4`

**Learning objective:** A learner can sign in to the Control Plane and to CRM, see the development user and role, and sign out of each application.

## What the recording shows

1. This lesson shows sign-in and user access for the development account. We do not create an account, and we do not change a role. The Control Plane sign-in page asks for an email and a password. The password box hides every character.
2. Sign in as crm.admin@example.test. After sign-in, that email appears at the top of the page.
3. Open Aadi CRM Development. The tenant administrator section says you can assign an existing account and a tenant role. Creating a new global account is not available.
4. Open View users. The development account is already a member. The note says creating a new global account is not available. The form adds an existing account by email. Leave that form blank. We do not press Add to tenant, and we do not remove anyone.
5. Press View access. This reads the permissions already on the role. It does not change them. The development role can read leads and manage projects.
6. Open View roles. The CRM Development role is listed. We do not rename it, assign it, or remove it.
7. Open the account menu, then sign out. The sign-in page comes back, and the Control Plane session is closed.
8. After signing out, open CRM. The shared localhost session is closed, so CRM asks for the email and password again. Use the same email. The password stays hidden.
9. CRM lists the tenant as an organization. Choose Aadi CRM Development. The workspace shows the signed-in email. Leads and Projects are available for this sign-in.
10. Sign out of CRM as well. Each application closes its own session. The CRM sign-in page returns.

## UI limitations

- Creating a new global account is not available. An existing account can be added by email. This recording does not add or remove anyone.
- Role assignment controls are on the users page. This recording does not assign or remove a role.
- Control Plane sign-out is inside the account menu.
- On localhost, CRM and the Control Plane share the sign-in session. Signing out of the Control Plane closes that session, so CRM asks for the password again. localhost and 127.0.0.1 do not share a session.

## How this file was recorded

Chromium opened the local Control Plane at http://localhost:5173 and CRM at http://localhost:5174. Playwright recorded the browser viewport while the script clicked, typed, and scrolled. Narration was spoken by the Windows voice Microsoft Zira Desktop and mixed into the MP4. The development password was typed only into a masked password field.

The screenshots in `dev-environment/evidence/browser/` were not used as frames in this video.

No tenant, user, subscription, project, form, record, or follow-up was created or edited.
