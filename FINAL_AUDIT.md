Final verification completed on 13 September 2026 using the project's existing Python 3.11.4 environment and Django 5.2.17. The existing Bootstrap design and application structure were preserved. No packages were installed.

1. **Features confirmed working.** Client registration, login, POST logout, dashboard, campaign requests, owned campaign list/detail, separate progress tracking, deliverable viewing/review, reports and profile editing; administrator login, statistics, campaign review, approval/rejection, assignment, employee creation/editing/deactivation, task creation and reports; employee login, dashboard, assigned campaigns/tasks, campaign progress, task updates, deliverable uploads/history and profile editing. The workflow test now also checks tracking and final campaign completion. Browser PDF generation was verified.

2. **Bugs found**, and 3. **fixes applied:**

| Problem | Final behavior |
| --- | --- |
| Track Campaigns opened the ordinary list. | `/client/campaigns/track/` provides a separate tracking page using the existing view/template, with ownership filtering, progress bars, employee names and completed/total tasks. |
| Completed could override invalid progress before validation. | Progress must be an integer from 0 to 100 before completion normalizes a valid value to 100. |
| Administrator completion left progress below 100. | Marking a campaign Completed sets campaign progress to 100. |
| Invalid progress appeared on the detail page as though saved. | Saved campaign information is reloaded after invalid submissions; the form keeps its errors and submitted input. |
| Reassignment left tasks with the previous employee, exposing stale task data. | Assignment and task transfer are saved together. Employee task access checks both the task's assignee and the campaign's current assignee. |
| Tasks could be assigned before the campaign had an employee. | Task creation requires the campaign's active assigned employee and shows an explanatory error otherwise. |
| Starting work prevented further task creation/reassignment. | Approved and In Progress campaigns support these existing administrator operations. |
| Employees could resume rejected/pending work using direct POSTs. | Progress changes, task updates and deliverable uploads are blocked until approval. |
| Empty POSTs became unbound forms with no required-field messages. | Empty submissions now show validation errors. |
| Both administrator forms validated when only one was submitted. | Only the submitted status or assignment form is bound. |
| Negative budgets were accepted. | A useful budget validation error is shown; zero remains valid. |
| Employee profile emails could exceed the User model's 254-character limit. | Employee and administrator employee-edit forms enforce that limit. |
| Login could redirect users to the wrong dashboard, a login page, an unknown page, or a POST-only action. | Dashboard redirects follow the authenticated role; unsuitable `next` destinations fall back to the dashboard. Django's external-redirect protection remains active. |
| Error messages used Bootstrap's nonexistent `alert-error` style. | Errors use `alert-danger`. |
| Report accessibility text could escape responsive tables and cause page-wide scrolling. | Report table wrappers contain their positioned text; narrow layouts remain within the viewport. |
| `.gitignore` contained `media/git status`. | The rule is corrected to `media/`. Existing tracked uploads were retained. |

4. **Files changed.**

| File | Purpose |
| --- | --- |
| `.gitignore` | Correct media ignore rule. |
| `campaign_planner/settings.py` | Map error messages to Bootstrap danger styling. |
| `campaigns/forms.py` | Progress, completion, budget, email and assignment/task validation. |
| `campaigns/views.py` | Tracking context, ownership checks, assignment consistency, form binding and blocked-work checks. |
| `campaigns/urls.py` | Tracking route and corrected login redirects. |
| `campaigns/templates/campaigns/base.html` | Client tracking navigation. |
| `campaigns/templates/campaigns/client_dashboard.html` | Correct tracking destination. |
| `campaigns/templates/campaigns/client_campaign_list.html` | Reuse the existing template for tracking; show appropriate columns and empty state. |
| `campaigns/templates/campaigns/administrator_campaign_detail.html` | Explain task transfer, display the assigned employee, allow task creation during progress, wrap header controls. |
| `campaigns/static/campaigns/css/report.css` | Prevent report-wide horizontal overflow. |
| `campaigns/test_audit.py` | Extend route/workflow coverage and replace the obsolete tracking-link expectation with the correct destination. No test was deleted or weakened. |
| `campaigns/test_final_verification.py` | 19 regression tests for discovered gaps, including rendered links/forms and validation/security cases. |
| `FINAL_AUDIT.md` | This report, manual test instructions and viva guide. |

Audit evidence is retained in `.dist/final-verification/`: `browser-results.json`, `campaign-report.pdf`, and `report-1440.png`. These use synthetic test records. Temporary browser helpers, HTML snapshots and intermediate screenshots were removed.

5. **Database changes: none.** No manual records were changed or deleted. The database retains 6 users, 2 employee profiles, 2 campaigns, 0 tasks and 2 deliverables. Both campaigns are In Progress. Both uploaded files exist. SQLite integrity and foreign-key checks passed; no invalid progress, completed/progress mismatch, reversed dates, negative budget or stale task assignment was found in the existing records. Test writes and uploaded test files used isolated test databases and temporary media directories.

The database SHA-256 before and after the audit is `40760fbdbfe6d812985227746b6ebdf6193de9c335eeb5162a962eb8c8018c5f`. The two original uploaded files remain unchanged.

6. **Migration status.** `makemigrations --check --dry-run` reports `No changes detected`. All existing migrations are applied, including campaigns 0001 through 0006. No models or migration files were changed, and no migration was created.

7. **Django check.** `manage.py check` reports `System check identified no issues (0 silenced).`

8. **Automated tests.** The baseline suite passed 97 tests. The final complete suite passes **116 tests: 116 passed, 0 failed, 0 errors, 0 skipped**, in **58.350 seconds**. All 97 original tests remain, with 19 added regression tests. Run it with:

```powershell
.\venv\Scripts\python.exe manage.py test --verbosity 1
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

9. **Security checks performed.** Role restrictions were exercised for anonymous users, clients, employees and administrators. Tests cover owned campaigns/tracking/reports, mismatched campaign/deliverable IDs, other employees' campaigns/tasks/uploads, assignment revocation, employee deactivation, forged profile/ownership fields, protected media URLs, path traversal, missing files, escaped report content, POST-only actions, missing-CSRF rejection and safe login redirects. Rendered forms include CSRF tokens, and an additional check successfully submitted a task update with CSRF enforcement enabled. Built-in Django admin index, password page and all six registered model lists were checked for superuser access and client/employee exclusion; its logout also requires POST.

10. **Remaining limits.** No known application defect remains from this audit. Browser checks used HTML rendered from isolated fixtures; the complete authenticated workflow was exercised with Django's test client. Chrome checks at 1440px and 390px passed for the report, tracking, administrator dashboard and employee dashboard, including mobile menu behavior and no page-wide horizontal overflow. Print styling and generation of a sample PDF passed. A physical printer, your personal browser's Save as PDF dialog and other browser engines still need your final manual check. These are verification limits, not missing application features.

This remains a local college/demo configuration with `DEBUG=True`, a development secret key and Bootstrap loaded from a CDN. Internet access is needed for the existing Bootstrap assets. A production deployment configuration was outside this audit. File uploads validate required/nonempty files and permitted extensions; this is not file-content or antivirus scanning.

11. **Exact final manual testing steps.**

Use a new, clearly named demonstration campaign so you can preserve your existing records. Use separate browser profiles for the three roles, or log out between roles.

1. From the project folder run `.\venv\Scripts\python.exe manage.py runserver`, then open `http://127.0.0.1:8000/`.
2. Choose Client, register an unused username/email and a strong password. Log out and log back in. Open Profile, change your name/email, save and reopen it.
3. Request a campaign named `Final Viva Demo`. Enter a description, Social Media as campaign type, budget `5000`, and a valid start/end date pair. Submit and check that it appears as Pending with 0% progress in My Campaigns and Track Progress. Keep its campaign ID from the detail URL.
4. Sign in as administrator through `/administrator/login/`. Confirm Total and Pending each increased by one relative to the previous counts. Open the new request and approve it: Pending decreases by one and Approved increases by one.
5. Open Employees. Create a demonstration employee if needed, then assign an active employee to the approved campaign. Click Add Task, enter `Prepare campaign content`, a valid due date and the assigned employee; submit. Confirm Pending task status.
6. Sign in as that employee. Confirm the campaign appears on the dashboard. Open it, set progress to `65` and status to In Progress. Save. Confirm the dashboard and details show 65%.
7. Open My Tasks. Change the task from Pending to In Progress, then to Completed. Reopen it after each save. The administrator can still add further tasks while the campaign is In Progress.
8. Upload two permitted files with distinct titles, such as `Final Creative` and `Alternative Creative`. Confirm they appear under previous deliverables and Open file works.
9. Sign in as the owning client. Open Track Progress: expect 65% campaign progress and `1 / 1` completed tasks if you created only one task. Open details and both files. Approve the first deliverable and reject the second. Their review buttons disappear after review.
10. Open View Campaign Report. Verify the campaign, client, employee, dates, budget, 65% campaign progress, completed task and two deliverables. Expect task counts total 1/completed 1 and deliverable counts total 2/approved 1/rejected 1. Click Print / Save as PDF, select Save as PDF, save and reopen it. Navigation and action buttons should be absent from print output.
11. Sign in as the employee and mark the campaign Completed. Confirm progress becomes 100%. Sign in as administrator, reopen its report and confirm Completed/100% and the same task/deliverable records. Compare dashboard counts with the visible campaign rows.
12. To check rejection, submit a second demo request and reject it as administrator. The client should see Rejected. To check reassignment, use an Approved or In Progress demo campaign with a task, change its employee and confirm the task transfers while the previous employee loses access.
13. On the employee-management page deactivate only a demonstration employee. Confirm its existing session loses access and login fails. Reactivate it if you want to continue using that account.
14. Sign in as a second client. Changing the campaign ID to another client's ID in detail/report URLs should return 404; tracking should list only this client's campaigns. A second employee should likewise receive 404 for another employee's campaign/task/file. Client/employee attempts to open administrator pages should redirect to the appropriate login.
15. Try a negative budget, reversed dates, progress `101`, invalid email and a disallowed `.txt` upload. Expect useful errors and unchanged saved data. At 390px in browser device mode, check the menu, cards, horizontal scrolling inside tables and report print preview. Use the Logout button, then revisit a protected page: it should ask you to log in.

12. **Submission readiness.** The project is ready for a local college submission/demo on the verified scope. Complete the manual rehearsal above with your demonstration credentials and confirm your college's separate documentation requirements. No new feature work was started after this audit.

The beginner explanation follows the actual implementation.

**Client → campaign request → admin approval → employee assignment → task creation → employee progress → deliverable upload → client review → campaign report.** A client describes the work. The administrator decides whether it should proceed, assigns an employee and creates tasks. The employee records progress, completes tasks and uploads files. The client reviews the files. Both client and administrator can read a report generated from current saved records. Client approval changes a deliverable's review status; it does not automatically complete the campaign.

| Part or term | Meaning in this project |
| --- | --- |
| `models.py` | Defines the stored data: EmployeeProfile, Campaign, Task and Deliverable. Django also supplies the User model. |
| `forms.py` | Chooses which fields each user can submit and validates them before saving. ModelForm connects a form to a model; Bootstrap classes style its widgets. |
| `urls.py` | Maps an address to a view and names routes so templates can link using `{% url %}` instead of hardcoded paths. The project URL file includes the campaigns routes, Django admin and protected media handler. |
| `views.py` | Receives the request, checks the role and ownership, validates POST data, reads/saves records, and returns HTML or a redirect. |
| Templates | HTML with Django variables/loops/conditions. Pages extend `base.html` to share Bootstrap, navigation and footer. `status_badge.html` provides consistent badges. |
| `ForeignKey` | A many-to-one relationship. Many campaigns can belong to one client; many tasks and deliverables can belong to one campaign. Each campaign currently has at most one assigned employee. |
| `OneToOneField` | One EmployeeProfile belongs to one User account. It adds employee-specific job title and phone fields. |
| `request.user` | The account Django identifies from the current login session. The request-creation view uses it to set ownership; it does not trust a posted client ID. |
| Authentication | Checking identity, such as verifying username/password and establishing a session. Passwords are hashed by Django. |
| Role authorization | Checking what that identity can do. Staff/superuser accounts use administrator pages, EmployeeProfile accounts use employee pages, and ordinary nonstaff accounts without an employee profile use client pages. Ownership checks then limit individual records. |
| GET | Reads a page or file. Opening a report, list or detail URL does not change campaign data. |
| POST | Submits a change, such as creating a campaign, changing progress, reviewing a deliverable or logging out. |
| CSRF | Protection against another site submitting an unwanted action through your logged-in browser. `{% csrf_token %}` supplies a form token and Django's middleware checks it. |
| `get_object_or_404` | Returns an object from the allowed query, or a 404 if no match exists. Combining `pk=campaign_id` with `client=request.user` prevents ID manipulation from exposing another client's campaign. |
| Migrations | Versioned instructions that create/change database tables. `makemigrations` detects model changes; `migrate` applies migration operations. This audit required neither new migration files nor database updates. |

Campaign progress is stored in `Campaign.progress_percentage`. An authorized employee submits an integer from 0 to 100 and an allowed status. Completed normalizes valid progress to 100. Client list/detail/tracking pages and reports read the same saved value. They show updates when the page is loaded/refreshed; this is not a live push system.

Task management uses the Task model's campaign, assigned employee, title, optional description, due date and status. Administrators create tasks for the campaign's active employee after approval or during progress. Employees can see and update tasks only when both task and campaign are assigned to them. Pending, In Progress and Completed are the allowed task statuses. Reassigning a campaign transfers its tasks while preserving task status.

Campaign progress and task completion are separate measurements. If one of two tasks is completed, task completion is 50%, while the employee might have recorded overall campaign progress as 65%. The report deliberately displays both. It does not silently change campaign progress when a task changes status.

Deliverable files are stored beneath `media/deliverables/`, while their paths and metadata are stored in the database. Permitted extensions are PDF, DOCX, JPG, JPEG and PNG. Each deliverable records its campaign, uploader, title, description, timestamp and review status. Its original media URL goes through `deliverable_file`, which checks that the requester is the owner, the campaign's current assigned employee or an administrator before returning a FileResponse.

Reports use `campaign_report_context()` in `reports.py`. The calling view first obtains a campaign the user is allowed to see. The helper reads related tasks/deliverables, counts records by status using database aggregation, computes completed tasks divided by total tasks (zero when there are none), and supplies a generated timestamp. `campaign_report.html` renders this context. Print / Save as PDF calls the browser's `window.print()`; `report.css` supplies print formatting. The application does not store a separate report model or generate a server-side PDF.

Fifteen likely viva questions and short answers:

1. **What problem does your project solve?** It keeps a client's campaign request, assigned work, progress, files and approvals together so all three roles can follow the same campaign.
2. **Who uses it?** Clients request and review work, administrators approve and coordinate it, and marketing employees carry out assigned work.
3. **Why did you use Django?** It provides database models, forms, authentication, templates and security middleware in one framework, which fits this workflow well.
4. **What are the main models?** Campaign, EmployeeProfile, Task and Deliverable, plus Django's built-in User model.
5. **Where is ForeignKey used?** A campaign links to its client and assigned employee; tasks and deliverables link to their campaign. This connects related records without copying their details.
6. **Why use an EmployeeProfile?** It extends a User account with employee-specific details such as job title and phone using a one-to-one relationship.
7. **How do you stop a client seeing another client's campaign?** I filter by both campaign ID and `request.user`. If the campaign is outside that client's allowed records, the view returns 404.
8. **How is login different from permission checking?** Login confirms who the user is. Permission checks decide which role pages and records that user can access.
9. **Why do you use forms instead of saving request data directly?** Forms validate required fields, dates, ranges and choices, and restrict the fields users may edit.
10. **Why must approve and reject use POST?** They change data. A normal link or page visit should not apply a decision, and the POST form also uses CSRF protection.
11. **What happens when an employee completes a campaign?** The campaign status becomes Completed and its progress is set to 100 after the submitted progress passes validation.
12. **Does completing every task automatically complete the campaign?** No. Task completion is calculated separately; campaign progress and status are explicitly recorded by the authorized user.
13. **What happens when a campaign is reassigned?** Its tasks transfer to the selected employee, their statuses stay intact, and the previous employee loses access to that campaign's work.
14. **How do you generate a report and PDF?** The report reads current database records and calculates counts. The browser's print function can save that HTML report as a PDF using the print stylesheet.
15. **How did you verify the project?** I ran Django checks and the full 116-test suite, checked role and ownership restrictions, exercised the entire workflow, and verified responsive pages and PDF output in Chrome.
