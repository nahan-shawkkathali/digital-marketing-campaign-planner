# Final post-enhancement verification

Verified on 15 September 2026.

**READY FOR COLLEGE SUBMISSION** for the requested local college/demo scope. The complete project suite, supplemental workflow rehearsal, migration checks, access-control checks, and browser layout checks passed. No application defect was found and no application code was changed.

## 1. Final Django check

Command: `.\venv\Scripts\python.exe manage.py check`

Result: `System check identified no issues (0 silenced).` Exit code: 0.

## 2. Database and migrations

Commands:

```powershell
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe manage.py showmigrations --plan
```

Results:

- `No migrations to apply.`
- `No changes detected` (exit code 0).
- Every listed migration is applied, including campaigns 0001 through 0007.
- `campaigns/migrations/0007_campaign_campaign_goal_campaign_platforms.py` correctly depends on `0006_task` and adds optional `campaign_goal` (TextField) and `platforms` (CharField, maximum 255 characters).
- The actual database has both columns with matching types. The complete suite also successfully applied all migrations to a fresh in-memory test database.
- No migration was created or modified.
- SQLite integrity check: `ok`. Foreign-key violations: 0. Invalid campaign progress, dates or budgets: 0. Stale task assignments: 0.

The database, both original uploads and every migration file have identical SHA-256 hashes before and after verification. The original media file set is unchanged. Existing records remain: **6 users, 2 employee profiles, 3 campaigns, 1 task, 2 deliverables**. Both uploaded files exist.

## 3. Exact complete automated test result

Command: `.\venv\Scripts\python.exe manage.py test --verbosity 2 --noinput`

| Result | Count |
| --- | ---: |
| Total tests | 169 |
| Passed | 169 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 0 |

Result: `Ran 169 tests in 79.158s` followed by `OK`. Exit code: 0. The suite used Django's in-memory test database; upload tests used temporary media directories. No existing test was modified, deleted, skipped or weakened.

The supplemental workflow rehearsal and browser checks below are separate checks and are **not added to the 169-test total**.

## 4. Client features verified

Registration; login and POST logout; dashboard; Request Campaign; saved Platforms and Campaign Goal; owned campaign list and detail; separate progress tracking; deliverable list, filters and file access; approve/reject and repeat-review protection; report selection and detailed report; print support; profile viewing and editing.

All six dashboard destinations are distinct and resolve correctly:

| Function | Destination |
| --- | --- |
| Request Campaign | `/client/campaigns/request/` |
| View Campaigns | `/client/campaigns/` |
| Track Campaign Progress | `/client/campaigns/track/` |
| Review Deliverables | `/client/deliverables/` |
| View Reports | `/client/reports/` |
| Manage Profile | `/client/profile/` |

## 5. Administrator features verified

Administrator login and POST logout; dashboard totals and all campaign status counts; campaign request/detail viewing; Platforms and Campaign Goal display; campaign approval/rejection; employee assignment/reassignment; task creation and task information; employee creation, editing and deactivation; campaign and report information.

Tests verify that deactivation ends access through an existing employee session and prevents login, and that reassignment transfers tasks while revoking the previous employee's access.

## 6. Employee features verified

Employee login and POST logout; dashboard and assigned campaigns; campaign detail; Platforms and Campaign Goal display; own task list and detail; task status updates; campaign progress updates; profile management; campaign selection and deliverable upload.

## 7. Deliverable workflow and combined rehearsal

The one-off rehearsal used a fresh in-memory database, temporary uploaded files, actual registration/login POSTs, and `Client(enforce_csrf_checks=True)` for all three roles. It completed:

1. Client registered, logged out/in, edited the profile, and requested a campaign with Platforms and a multiline Campaign Goal.
2. Administrator opened the request, verified requirements and dashboard counts, approved it, created an employee, assigned the campaign, and created its task.
3. Employee logged in, saw the assigned campaign and requirements, opened the task, changed it to In Progress then Completed, and set campaign progress to 65% / In Progress.
4. Employee followed the campaign selector to the upload form and uploaded two files. Both records had the correct campaign, correct `uploaded_by` employee, and initial Pending Review status.
5. Client saw 65% progress and 1 / 1 completed tasks, opened both protected uploaded files and received their exact contents, then approved one and rejected one through Review Deliverables.
6. Client and administrator reports showed the same campaign and requirements, 65% campaign progress, 100% task completion, and two deliverables: one approved and one rejected.
7. All three roles logged out successfully.

Only eligible campaigns assigned to the employee appear in Choose Campaign. The existing enhancement tests cover other employees' campaigns, unassigned campaigns, forged posted IDs, missing IDs, Pending/Rejected campaigns and assignment revocation. Direct upload GET/POST requests to another employee's or unassigned campaign return 404 and save nothing. The supplemental rehearsal independently confirmed upload access is revoked after reassignment.

## 8. Platforms and Campaign Goal

- Both fields save correctly with the campaign and persist through approval, assignment, progress updates, uploads and reports.
- Client, administrator and employee details show the saved values; client and administrator reports show them too.
- Campaign Goal preserves multiline text. User-supplied HTML is escaped.
- Platforms enforces its 255-character limit. The existing tests cover long goals, blank/omitted values and legacy campaigns.
- Fields remain optional; missing values display `Not specified` on details/reports.
- Request form fields have no hint/example help text, no placeholders and no prefilled examples.

## 9. Reports

Verified database-backed campaign title, description, campaign type, target audience, Platforms, Campaign Goal, client, assigned employee, budget, dates, status, progress, tasks, task completion, deliverables and their approval statuses.

`campaign_report_context()` reads the selected campaign's related tasks/deliverables and calculates summaries from database queries. Tests verify live refresh, exclusion of another campaign's records, zero budgets, empty campaigns, missing optional information and every campaign status. No Report model or hardcoded campaign data is used.

Browser checks confirmed that the Print / Save as PDF button invokes `window.print()`, print CSS hides navigation/footer/action controls while keeping the report visible, and Chrome generates a valid 97,384-byte PDF. A sample is saved at `.dist/post-enhancement-verification/campaign-report.pdf`.

## 10. Security

Passed the existing tests and code inspection for:

- Client ownership checks on campaign lists/details, tracking, report lists/details, deliverables, reviews and uploaded files.
- Employee assignment checks on campaigns, tasks, upload selection/forms and files, including both task and current campaign assignee.
- Cross-role exclusion from client, employee and administrator pages; anonymous redirects to login.
- Manipulated URL IDs, mismatched campaign/deliverable IDs and forged owner/assignee/uploader fields.
- POST-only decisions, task updates and logout; GET requests do not apply submitted update parameters.
- CSRF middleware remains enabled; rendered forms have tokens; missing/invalid tokens are rejected. The combined rehearsal successfully submitted valid tokens throughout.
- Protected original media URLs, missing/unregistered files and path traversal; unauthorized exact file URLs return 404. Former uploaders lose file access after campaign reassignment.
- Safe login return destinations, output escaping, and employee deactivation.

## 11. UI/navigation and bugs

The complete suite checks rendered links, fragments, form destinations, role redirects, dashboard destinations and required empty-state messages. Expected 404s for unauthorized/missing records are security successes; no broken application navigation was found.

Chrome rendered **34 current HTML snapshots at each of 1440px, 390px and 320px: 102 page/viewport checks**. These include all three roles, the new client pages, the selector/upload form, both reports, and empty states. Checks found no page-wide horizontal overflow, confirmed Bootstrap loaded, and verified the mobile menu expands and collapses on every page at both narrow widths. There were no browser JavaScript/resource errors. Desktop/mobile report screenshots and the mobile selector were visually inspected; narrow tables use their existing horizontal scroll containers.

**Application bugs found: none. Fixes applied: none.** No redesign, feature, package, model or refactoring was introduced.

## 12. Files changed

**Existing application, test, configuration, migration, database, uploaded-file and prior verification-report files changed: none.** `git diff --stat` is empty for existing tracked files.

Added only:

- `POST_ENHANCEMENT_VERIFICATION.md` (this report).
- `.dist/post-enhancement-verification/` (command logs, before/after preservation results, supplemental workflow/browser verification scripts, JSON results, 34 synthetic HTML snapshots, four screenshots and one sample PDF).

The exact evidence file list is `.dist/post-enhancement-verification/artifact-inventory.txt`. The temporary Chrome profile was removed after Chrome closed. Synthetic workflow uploads were removed by the temporary-directory cleanup. Your original media files were not touched.

## 13. Anything incomplete

No known application work remains in the requested scope.

Verification limits: authenticated workflows and security were exercised with Django's test client. Browser checks rendered captured HTML from those isolated records; they did not submit the full workflow through browser controls. Actual touch-device interaction, your personal browser's native Save as PDF dialog and physical printing remain manual checks. These are the final rehearsal steps below.

## 14. Exact manual checks

Use new demonstration records, separate browser profiles for the three roles (or log out between roles), and preserve your existing records.

1. Run `.\venv\Scripts\python.exe manage.py runserver` from the project folder and open `http://127.0.0.1:8000/`.
2. Register an unused client username/email with a strong password. Log out, log back in, update your name/email under Manage Profile, save and reopen it.
3. Open each of the six dashboard functions and compare the address bar with the destination table above. A new client should see useful empty messages on Campaigns, Track Progress, Review Deliverables and Reports.
4. Request `Final Submission Demo`: description `Launch a local product`, type `Social Media`, Platforms `Instagram, Facebook, YouTube`, Campaign Goal `Build launch awareness` followed by a second line `Generate 25 enquiries`, budget `5000`, start `2026-10-01`, end `2026-10-31`. Confirm both new fields begin blank without examples. Submit, reopen details, and check Pending / 0% and the exact saved requirements.
5. Log in at `/administrator/login/`. Confirm the request and dashboard counts. Open its details, check Platforms/Goal, approve it, assign an active demonstration employee, and add `Prepare launch content` with due date `2026-10-15`.
6. Log in as that employee at `/employee/login/`. Open the assigned campaign and verify its requirements. In My Tasks, change the task to In Progress and then Completed, reopening after each save. Set campaign progress to 65% and status In Progress. Edit/save/reopen the employee profile.
7. From Employee Dashboard choose Upload Deliverables -> Choose Campaign. Confirm only this employee's eligible campaigns appear. Choose `Final Submission Demo`, upload two small permitted files named/titled `Final Creative` and `Alternative Creative`, and confirm both are attached to that campaign. On a narrow screen, horizontally scroll the selector table to reach Upload Deliverable.
8. Return as the owning client. Track Progress should show 65% and 1 / 1 completed tasks. Review Deliverables should show both uploads. Open each file, approve Final Creative and reject Alternative Creative. Check the Approved/Rejected filters and confirm review buttons disappear for reviewed files.
9. Open View Reports -> this campaign's report. Verify its requirements, client, employee, budget/dates, 65% progress, completed task, and one approved plus one rejected deliverable. Click Print / Save as PDF, choose Save as PDF, save/reopen the document, and inspect all pages for cut-off text/tables. Navigation and action buttons should be absent. Try a physical printer if your submission requires a printed report.
10. Reopen the administrator report and compare it with the client's. As employee, mark the campaign Completed and confirm it becomes 100% on the client/admin views.
11. Using only additional demonstration data, reject a second campaign request and verify its client status. Edit/deactivate a demonstration employee and verify its existing session loses access and login fails; reactivate it when needed.
12. With a second client/employee account, replace an owned campaign/task/upload/report ID with another account's ID: expect 404. Exact uploaded-file URLs must also be denied. Try the other role's dashboard: expect a login redirect. Log out and revisit protected pages: expect login.
13. On your actual phone or browser device mode at 390px and 320px, open/close the menu, follow links and scroll wide tables to reach actions. Check the report and upload form. Try a negative budget, an end date before the start, progress 101 and a disallowed `.txt` upload: expect validation errors without saving invalid values.

## 15. Final result

**READY FOR COLLEGE SUBMISSION**

Reason: all 169 project tests passed with zero failures, errors or skips; all migrations are applied and models match; the enhanced workflow, record connections, reports, access restrictions and browser layouts passed verification; original records/files remain unchanged; no application bug or missing requested feature was identified. Complete the personal-browser rehearsal above before presenting.

No implementation work follows this result.
