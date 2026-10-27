# Open the development tenant and confirm CRM access

**Audience:** A person learning the Aadi Control Plane and Aadi CRM.

**Duration:** About 3 minutes (185.2 seconds in the file).

**Video file:** `dev-environment/videos/recordings/01-tenant-onboarding-and-crm-access.mp4`

**Learning objective:** A learner can see the existing Aadi CRM Development tenant, walk the onboarding steps without creating anything, and confirm that CRM is available.

## What the recording shows

1. This lesson uses the tenant that is already set up, Aadi CRM Development. We will look at product onboarding and CRM access. We will not create a tenant, a product, a plan, or a subscription. Sign in to the Control Plane. The password stays hidden.
2. The Control Plane home shows Aadi CRM Development under tenant context. On these screens, the word organization means this tenant. The product does not keep a separate organization record.
3. Open product onboarding. This page is for a platform administrator. It has seven steps. Step one lists tenants that already exist.
4. Select Aadi CRM Development. The page says that no new tenant was created. The create form is still on the page. Leave it empty.
5. Go to the product step. Select the CRM product that is already registered. The page says the existing product was selected. No second product is registered.
6. The features step shows declared feature keys and the commercial feature catalogue. These are catalog definitions. A commercial feature is not the same as a tenant entitlement. We do not save any feature changes.
7. The plan step shows the CRM Development plan. A plan has no price and no billing cycle. Select the existing plan. The create plan form stays empty, and we do not save plan features.
8. The subscription step shows the open subscription for this tenant and CRM. Assigning another subscription is blocked. The status control is on the page. We do not change it.
9. The entitlements step can load a signed result from the platform. That result includes a signature, so this recording does not press Load entitlements. Entitlements are calculated from the active subscription. They are not stored in their own table.
10. The review names the selected tenant, product, and plan. Entitlements stay unloaded, so no signature is on screen.
11. Open the tenant. The status is active. This page says that creating a tenant does not create an account. We do not add an account.
12. The same page shows the CRM product already assigned to this tenant. We do not press Assign a product.
13. Open CRM from the Control Plane. The page says CRM is available, and it names the organization Aadi CRM Development. This page only checks access. It is not the CRM workspace.
14. Open the CRM application. On localhost, this browser is already signed in, so CRM does not ask again. The overview says CRM is available in this organization.

## UI limitations

- The onboarding page can create a tenant, product, feature, plan, or subscription. This recording does not submit those forms.
- Step six can load a signed entitlement. The signature is not loaded or shown.
- The Control Plane page that says CRM is available only checks access. It does not open the CRM workspace.
- On localhost, CRM accepts the Control Plane session. Signing out closes that shared session. localhost and 127.0.0.1 still do not share a session.
- The word organization on these screens is the tenant. There is no separate organization record.

## How this file was recorded

Chromium opened the local Control Plane at http://localhost:5173 and CRM at http://localhost:5174. Playwright recorded the browser viewport while the script clicked, typed, and scrolled. Narration was spoken by the Windows voice Microsoft Zira Desktop and mixed into the MP4. The development password was typed only into a masked password field.

The screenshots in `dev-environment/evidence/browser/` were not used as frames in this video.

No tenant, user, subscription, project, form, record, or follow-up was created or edited.
