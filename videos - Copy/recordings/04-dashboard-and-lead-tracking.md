# Use project KPIs, follow-ups, and record status

**Audience:** A person learning the Aadi Control Plane and Aadi CRM.

**Duration:** About 3 minutes (172.0 seconds in the file).

**Video file:** `dev-environment/videos/recordings/04-dashboard-and-lead-tracking.mp4`

**Learning objective:** A learner can see what this CRM uses instead of a dashboard, and how a lead is tracked through record status and follow-up queues.

## What the recording shows

1. This lesson looks for a dashboard and for lead tracking. There is no page named Dashboard. The overview only says that CRM is available. Reporting is on Project KPIs. The Leads page does not list project records. Sign in to CRM. The password stays hidden.
2. Open Project KPIs and choose Preschool. The report does not load. The page says the request could not be completed. Press Retry. The same message comes back. The records are not changed.
3. The page still says that record dates use the UTC calendar day, and that follow-up dates use India Standard Time. It does not show a count of active records. Lead status is read from the record itself, after the follow-up queues.
4. Open Leads. The screen says that no leads are open in this shell. This is the real Leads page. It does not show the Preschool, Paneerwala, Space View, or Hiring records.
5. Open Follow-ups and choose Preschool. Queues use India Standard Time, and a follow-up is in one queue only. The page opens on today. On this date, no follow-up is due today.
6. Open the overdue queue. These follow-ups were due before today. Hillview Kids Campus is in this list. Its sample call was due on the first of October.
7. Open the upcoming queue. These follow-ups are due after today. Northside Learning Circle has a follow-up in November.
8. Open the Preschool record for Northside Learning Circle. Status, the next follow-up date, and the follow-up queues are how this CRM tracks a lead. There is no separate lead pipeline beyond those fields. We do not edit the record.

## UI limitations

- There is no page named Dashboard. The overview only confirms that CRM is available.
- Project KPIs for Preschool returns an error: the request could not be completed. Retry does not load the counts. The recording does not invent numbers.
- A successful KPI report would say that record status is not counted. That sentence stays hidden while the report is failing.
- The Leads page is empty. It does not list Preschool, Paneerwala, Space View, or Hiring records.
- Follow-up queues use India Standard Time. The today queue can be empty.
- The date fields remain on the failed KPI page. This recording does not apply a new period, because the report fails before it can show counts.

## How this file was recorded

Chromium opened the local Control Plane at http://localhost:5173 and CRM at http://localhost:5174. Playwright recorded the browser viewport while the script clicked, typed, and scrolled. Narration was spoken by the Windows voice Microsoft Zira Desktop and mixed into the MP4. The development password was typed only into a masked password field.

The screenshots in `dev-environment/evidence/browser/` were not used as frames in this video.

No tenant, user, subscription, project, form, record, or follow-up was created or edited.
