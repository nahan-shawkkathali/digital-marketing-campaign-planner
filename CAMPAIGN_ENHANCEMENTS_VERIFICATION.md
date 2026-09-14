# Campaign requirements and employee upload verification

## Root cause and upload fix

The Marketing Employee Dashboard's Choose Campaign button pointed to `#assigned-campaigns`, an anchor in the same dashboard. That general table offered View Details rather than a direct upload choice. The secure upload form already existed and worked, but the dashboard did not provide a clear selection step for it.

Choose Campaign now opens a dedicated page headed **Choose Campaign to Upload Deliverable**. It shows campaign title, client, deadline, status, progress, and a direct Upload Deliverable button. The list is scoped to the logged-in user's employee profile and follows the existing upload eligibility rules: Approved, In Progress, and Completed campaigns are available; Pending, Rejected, unassigned, and other employees' campaigns are excluded. Completed campaigns have a clearly labelled Completed badge. When nothing is eligible, the page displays: “No campaigns are currently available for deliverable upload.”

The upload and review systems are reused. No duplicate model, upload form, upload handler, report generator, or approval handler was created.

| Step | URL | URL name |
| --- | --- | --- |
| Employee dashboard | `/employee/dashboard/` | `employee_dashboard` |
| Choose Campaign | `/employee/deliverables/` | `employee_deliverable_campaigns` |
| Upload Deliverable | `/employee/campaigns/<campaign_id>/deliverables/upload/` | `employee_deliverable_upload` |
| Successful upload returns to campaign details | `/employee/campaigns/<campaign_id>/` | `employee_campaign_detail` |
| Owning client reviews uploaded work | `/client/deliverables/` | `client_deliverables` |

The existing upload form uses multipart POST with CSRF protection. The view sets the campaign from the ownership-checked URL and the uploader from the logged-in employee profile; forged submitted IDs are ignored. The initial approval status stays Pending Review. Success redirects to the employee campaign detail page with a confirmation message. Uploads still use the existing media storage and protected file handler. The upload endpoint now explicitly accepts only GET for the form and POST for submissions.

## Campaign fields and display

No equivalent fields existed in Campaign. The following optional fields were added to that model:

| Field | Definition | Form presentation |
| --- | --- | --- |
| `platforms` | `CharField(max_length=255, blank=True)` | Platforms, with the example “Instagram, Facebook, YouTube”. |
| `campaign_goal` | `TextField(blank=True)` | Campaign Goal, with a four-row textarea and example objective placeholder. |

All existing request fields remain. The existing Bootstrap form styling, budget validation, and start/end date validation are preserved. Submissions that omit the new fields still work.

Platforms and Campaign Goal display on the client, administrator, and employee campaign detail pages, plus the existing client and administrator campaign reports. Goal line breaks are preserved, long values wrap, and user content is HTML-escaped. Empty values show **Not specified**. The long requirements were not added to compact campaign lists.

## Migration and existing data

Created and applied `campaigns/migrations/0007_campaign_campaign_goal_campaign_platforms.py`. It depends on `0006_task` and contains only two AddField operations. No old migration was edited.

Executed successfully:

```powershell
.\venv\Scripts\python.exe manage.py makemigrations
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe manage.py test --verbosity 1
```

- Migration 0007 is marked applied by `showmigrations campaigns`.
- Django system check: no issues.
- Migration consistency check: `No changes detected`.
- Targeted new regression tests: **26 passed**.
- Complete test suite: **169 passed, 0 failed, 0 errors, 0 skipped**, in 73.856 seconds (the existing 143 plus 26 new tests).
- `git diff --check`: passed.

Before migration, hashes and row counts were captured for every existing application/authentication table and hashes for every uploaded file. The same comparison after migration matched exactly when excluding the two new columns and Django's migration-history table. All three existing campaigns have blank values for both new fields. Existing campaign values, related records, user accounts, and files were preserved. SQLite integrity reports `ok`, with zero foreign-key violations.

## Security and compatibility checks

Automated checks cover:

- The selector only exposes campaigns assigned to the logged-in employee, including when query parameters try to change the employee/campaign ID.
- Other employees' campaigns, unassigned campaigns, and nonexistent campaign IDs return 404 for uploads.
- Pending/Rejected campaigns reject direct POST uploads without saving records or files.
- Reassignment after opening a form revokes the previous employee's upload access.
- Clients and nonemployee staff/superuser accounts cannot use the employee selector or upload pages; anonymous users are redirected to employee login.
- Missing or invalid CSRF tokens return 403, while a valid CSRF-protected multipart upload succeeds.
- GET does not save a file; PUT/PATCH/DELETE are rejected.
- Forged campaign, uploader, and approval-status values cannot change the server-selected associations or initial Pending Review status.
- Uploaded work appears only for the owning client; another client cannot open its protected file URL.
- The existing approval/rejection handler works for new uploads and refuses subsequent reviews.
- New campaign requirements save with all existing request fields, preserve validation and ownership rules, display safely across all required pages, and fall back correctly when blank.
- The new selector participates in the pre-existing route, role, rendered-link, and CSRF-form audit tests.

No existing test was removed or weakened. Existing uncommitted changes from earlier tasks were preserved. No new package, authentication pattern, media configuration, or visual theme was introduced.

## Files changed in this task

| File | Purpose |
| --- | --- |
| `campaigns/models.py` | Add the two optional Campaign fields. |
| `campaigns/forms.py` | Extend the existing CampaignRequestForm with labels, example text, and goal textarea. |
| `campaigns/views.py` | Add the employee campaign selector; restrict existing upload view to GET/POST. |
| `campaigns/urls.py` | Add `employee_deliverable_campaigns`. |
| `campaigns/migrations/0007_campaign_campaign_goal_campaign_platforms.py` | Add the fields without modifying old migrations. |
| `campaigns/templates/campaigns/employee_dashboard.html` | Connect Choose Campaign to the selector. |
| `campaigns/templates/campaigns/employee_deliverable_campaigns.html` | New responsive campaign-selection table. |
| `campaigns/templates/campaigns/campaign_request.html` | Render field help text using the existing form styling. |
| `campaigns/templates/campaigns/includes/campaign_requirements.html` | Shared Platforms/Goal display and blank-value fallbacks for detail pages. |
| `campaigns/templates/campaigns/client_campaign_detail.html` | Display client requirements. |
| `campaigns/templates/campaigns/administrator_campaign_detail.html` | Display requirements before approval/assignment. |
| `campaigns/templates/campaigns/employee_campaign_detail.html` | Display requirements to the assigned employee. |
| `campaigns/templates/campaigns/campaign_report.html` | Include requirements in the existing client/admin report. |
| `campaigns/test_audit.py` | Add selector to the existing route audit. |
| `campaigns/test_campaign_enhancements.py` | Add 26 regression tests for both improvements. |
| `CAMPAIGN_ENHANCEMENTS_VERIFICATION.md` | This report and manual testing sequence. |

## Exact manual testing steps

Use demonstration records and separate browser profiles for the roles, or log out between them.

1. Start `.\venv\Scripts\python.exe manage.py runserver` and open `http://127.0.0.1:8000/client/login/`.
2. Sign in as a client. Open `/client/campaigns/request/`. Enter `Campaign Requirements Demo`, a description, campaign type, target audience, budget `5000`, and a valid start/end date pair. Enter Platforms as `Instagram, Facebook, YouTube` and Campaign Goal as `Build awareness for the new product, increase engagement, and generate enquiries and sales.` Submit.
3. Open the new campaign from My Campaigns. Confirm both new values appear on client details and record its campaign ID. Open its existing report and confirm both values appear there too.
4. Through `/administrator/login/`, sign in as administrator. Open the demo campaign, verify Platforms and Campaign Goal, approve the request, and assign an active employee using the existing workflow. Open the administrator report and verify the same requirements.
5. Through `/employee/login/`, sign in as that employee. From `/employee/dashboard/`, click Upload Deliverables → Choose Campaign. Confirm the URL is `/employee/deliverables/` and the heading is Choose Campaign to Upload Deliverable. Confirm the demo campaign row includes its client, deadline, Approved status, and 0% progress.
6. Click its Upload Deliverable button. Confirm the URL is `/employee/campaigns/<campaign_id>/deliverables/upload/` and the form names the selected campaign. Upload a permitted PDF/DOCX/JPG/JPEG/PNG titled `Demo Creative A` with a description. Confirm the success message and redirect to `/employee/campaigns/<campaign_id>/`. Verify the requirements and uploaded deliverable on that detail page. Upload a second file titled `Demo Creative B` using the same flow.
7. Return as the owning client to `/client/deliverables/?status=pending`. Confirm both new files appear with the correct campaign and uploader. Open their file links. Approve A and reject B. Check Approved/Rejected filters, correct badges, and the absence of further review buttons. Open the campaign report to confirm the same deliverables and requirements.
8. Sign in as another employee. Confirm the first employee's campaign is absent from `/employee/deliverables/`. Paste its upload URL: expect 404. An employee with no eligible assigned campaigns should see `No campaigns are currently available for deliverable upload.`
9. For demonstration Pending and Rejected campaigns, confirm they are excluded from selection. A direct POST upload to either must show the existing approval-required error and save nothing. Completed campaigns remain eligible under the existing rules and show Completed clearly.
10. As a client, visit `/employee/deliverables/` and the employee upload URL: expect a redirect to employee login. Log out and repeat to confirm anonymous redirects. As a second client, confirm the first client's deliverables are absent and their protected file URLs return 404.
11. Open an older campaign's details as client, administrator, and assigned employee, then its report. Confirm both fields show Not specified and the pre-existing campaign information remains intact. Submit another campaign with the new fields blank to confirm they are optional.
12. Try a negative budget and an end date before the start date while filling the new fields. Confirm the existing validation errors appear and entered requirements remain in the form for correction.
13. At desktop width and a 390px mobile viewport, check the request form, selector, detail pages, and report. Confirm the blue Bootstrap styling, wrapping goal text, accessible upload buttons, and table scrolling within its container. Use the existing Print / Save as PDF action to inspect the new report fields in print preview.

Browser viewport and print-dialog checks are included for manual verification; this task's automated checks exercised rendered HTML and authenticated Django requests.
