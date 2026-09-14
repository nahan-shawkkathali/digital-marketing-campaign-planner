# Client module UX verification

The client dashboard now has six distinct destinations. The four campaign-related functions have separate responsibilities and interfaces over the existing records.

| Dashboard button | URL | URL name | Purpose |
| --- | --- | --- | --- |
| Request Campaign | `/client/campaigns/request/` | `campaign_request` | Existing campaign request form. |
| View Campaigns | `/client/campaigns/` | `client_campaign_list` | My Campaigns: overview table with title, submitted date, deadline, status, recorded progress, and View Details. |
| Track Campaigns | `/client/campaigns/track/` | `client_campaign_tracking` | Track Campaign Progress: assignments, deadlines, status, recorded campaign progress, completed/total tasks, separate progress bars, and View Details. |
| Review Deliverables | `/client/deliverables/` | `client_deliverables` | Review uploaded files and approve/reject pending deliverables. |
| View Reports | `/client/reports/` | `client_reports` | Select a campaign report using cards showing current campaign, employee, task, and deliverable summaries. |
| Manage Profile | `/client/profile/` | `client_profile` | Existing client profile form. |

Dashboard: `/client/dashboard/`. Campaign details remain at `/client/campaigns/<campaign_id>/`. Detailed reports remain at `/client/campaigns/<campaign_id>/report/`, using `campaign_report_context()` and the existing report template and printing behavior.

The existing review endpoint remains `/client/campaigns/<campaign_id>/deliverables/<deliverable_id>/<decision>/`, with `approve` or `reject` as the decision. Forms from the review list return to that list and preserve the selected status filter. Existing campaign-detail forms continue to return to campaign details. Return destinations are fixed locally, not taken from arbitrary URLs.

Deliverable filters use `/client/deliverables/`, `?status=pending`, `?status=approved`, and `?status=rejected`. Missing or invalid filter values show All. Pending rows have POST forms with CSRF tokens. Approved rows show a green badge, rejected rows a red badge, and neither has review buttons. Empty lists display the requested empty-state messages.

My Campaigns and Track Campaign Progress no longer have report actions. Reports are selected from the dedicated report cards. The existing campaign detail page retains its report and review functionality. The blue Bootstrap theme and simple client navbar are retained. Tables use responsive scroll containers, filters wrap, and report cards stack on narrow screens.

## Files changed by this task

| File | Change |
| --- | --- |
| `campaigns/views.py` | Client-only deliverable/report lists, shared owned-campaign/task-count queries, safe return to the review list, and an atomic pending-only update in the existing review action. |
| `campaigns/urls.py` | Add `client_deliverables` and `client_reports`. |
| `campaigns/templates/campaigns/client_dashboard.html` | Correct review/report buttons and descriptions. |
| `campaigns/templates/campaigns/client_campaign_list.html` | Remove report actions, clarify each list's purpose, and add a task-completion bar to tracking. |
| `campaigns/templates/campaigns/client_deliverables.html` | New review table, status filters, file links, review badges, POST forms, and empty states. |
| `campaigns/templates/campaigns/client_reports.html` | New responsive report-selection cards and empty state. |
| `campaigns/test_audit.py` | Include both new routes in existing role/navigation checks and update obsolete dashboard/report-link expectations. |
| `campaigns/test_client_ux.py` | Add 27 regression tests. |
| `CLIENT_UX_VERIFICATION.md` | This report and manual testing sequence. |

Pre-existing uncommitted audit changes were preserved. This task did not edit Admin/Employee workflows, models, migrations, shared navigation, stylesheets, dependencies, or settings. No existing test was removed; old link expectations were updated to match the requested new destinations.

## Database and verification

No migration is required. No packages, fields, models, or alternate report-generation system were added. The actual existing progress field is `Campaign.progress_percentage`; every page reads that field. Task percentages are computed for display from existing task counts. Distinct aggregate counts avoid inflated totals when tasks and deliverables are joined together for report cards.

The application database SHA-256 was unchanged before and after the code changes and test execution:

`40760fbdbfe6d812985227746b6ebdf6193de9c335eeb5162a962eb8c8018c5f`

Tests use Django's isolated test database and temporary test media directories.

Commands:

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe manage.py test --verbosity 1
```

- Django check: passed, no issues.
- Migration check: passed, `No changes detected`.
- Targeted client UX tests: 27 passed.
- Complete suite: **143 passed, 0 failed, 0 errors, 0 skipped**, in 77.584 seconds (the existing 116 tests plus 27 new tests).
- `git diff --check`: passed.

Security verification covers owned campaign/deliverable/report lists, forged query parameters, manually changed campaign and deliverable IDs, file ownership, employee/staff/superuser exclusion even when an account owns a campaign, anonymous redirects, POST-only reviews, missing/invalid CSRF rejection, successful approval/rejection with CSRF enforcement enabled, repeated review refusal, safe return destinations, read-only list methods, and escaped user content. The existing detailed reports and Admin/Employee regression tests remain included in the complete suite.

The new layouts were checked through rendered HTML and automated navigation/form tests. Browser viewport and print-dialog checks for this change are part of the manual sequence below; they were not performed in this task.

## Exact manual testing sequence

Use demonstration records and separate browser profiles for each role, or log out before changing roles.

1. Start the app with `.\venv\Scripts\python.exe manage.py runserver`. Open `http://127.0.0.1:8000/client/login/` and sign in as a client. Open `/client/dashboard/` and confirm the six button labels and destinations in the table above.
2. Click **Request Campaign**. Submit a campaign named `Client UX Demo`, a description, a valid start date, and a later deadline. Confirm the redirect to My Campaigns. Open **Manage Profile**, update the demonstration account's name/email, save, and return to the dashboard.
3. As administrator, use the existing workflow to approve `Client UX Demo`, assign an active employee, and create two tasks with valid due dates.
4. As that employee, set the campaign to In Progress with 25% progress, complete one of the two tasks, and upload two permitted files titled `Demo Creative A` and `Demo Creative B`.
5. As the owning client, click **View Campaigns**. Confirm `/client/campaigns/`, the My Campaigns heading, title, submitted date, deadline, In Progress status, 25%, and View Details. Confirm there are no View Report or Approve/Reject actions in this overview. Open View Details and record the campaign ID.
6. Return to the dashboard and click **Track Campaigns**. Confirm `/client/campaigns/track/`, the Track Campaign Progress heading, assigned employee, deadline, status, 25% campaign progress, and `1 / 2` tasks with 50% task completion. Confirm View Details works.
7. Return to the dashboard and click **Review Deliverables**. Confirm `/client/deliverables/`, both deliverable titles, campaign name, uploader, dates, Pending Review badges, and Open File links. Open each file. Select Pending and confirm `?status=pending`.
8. Approve `Demo Creative A`. Confirm the success message and return to the Pending filter with that row removed. Select Approved and confirm its green badge and absence of review controls. Return to Pending and reject `Demo Creative B`. Select Rejected and confirm its red badge and absence of review controls. Select All and confirm both reviewed rows remain visible.
9. To check a stale review, use a second client tab with a pending form loaded before step 8. Submit that stale form after the item is reviewed. Expect the already-reviewed message and the original decision to remain unchanged. Merely visiting the approve/reject URL with GET must return HTTP 405 without changing data.
10. Return to the dashboard and click **View Reports**. Confirm `/client/reports/`, the demo campaign card, In Progress, 25%, employee, `1 / 2 completed`, and `1 approved, 0 pending review, 1 rejected`. Click View Report and confirm the existing `/client/campaigns/<campaign_id>/report/` page shows the same records. Exercise Print / Save as PDF if desired.
11. As employee, complete the second task and change recorded campaign progress to 60%. As client, refresh tracking and reports. Expect 60% campaign progress and `2 / 2` completed tasks; tracking's task-completion bar should show 100%.
12. Sign in as a second client with no campaigns. Confirm the four list pages show their appropriate empty states. Paste the first client's campaign-detail URL, report URL, and uploaded-file URL: each must return 404. Confirm the other client's campaigns and deliverables never appear in any filter.
13. Sign in separately as an employee, a staff administrator, and a superuser. Visit `/client/campaigns/`, `/client/campaigns/track/`, `/client/deliverables/`, and `/client/reports/`: each must redirect to the client login. Log out and repeat to confirm anonymous redirects.
14. At desktop width and a 390px mobile viewport, revisit the dashboard and all four lists. Confirm cards stack, filters remain usable, table overflow scrolls within its container, review buttons remain reachable, and the navbar collapses. Confirm its client links remain Home, Dashboard, Campaigns, Track Progress, Profile, and Logout.
