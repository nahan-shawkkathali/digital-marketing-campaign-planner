import tempfile
from datetime import timedelta
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Campaign, Deliverable, EmployeeProfile, Task


class AuditFixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("auditclient", email="client@example.com")
        cls.other_client = User.objects.create_user("otherclient")
        cls.staff = User.objects.create_user("auditadmin", is_staff=True)
        cls.superuser = User.objects.create_user("auditsuper", is_superuser=True)
        cls.employee_user = User.objects.create_user(
            "auditemployee", first_name="Maya", email="employee@example.com",
        )
        cls.employee = EmployeeProfile.objects.create(user=cls.employee_user)
        cls.other_employee_user = User.objects.create_user("otheremployee")
        cls.other_employee = EmployeeProfile.objects.create(user=cls.other_employee_user)
        cls.campaign = Campaign.objects.create(
            client=cls.owner, assigned_employee=cls.employee,
            name="Audit Campaign", description="Existing campaign", campaign_type="Social Media",
            status=Campaign.Status.APPROVED, budget=0,
        )
        cls.task = Task.objects.create(
            campaign=cls.campaign, assigned_employee=cls.employee,
            title="Audit Task", description="Prepare campaign content", due_date="2026-10-01",
        )
        cls.deliverable = Deliverable.objects.create(
            campaign=cls.campaign, uploaded_by=cls.employee,
            title="Audit Deliverable", uploaded_file="deliverables/audit.pdf",
        )

    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        self.media_root = Path(media.name)
        media_settings = override_settings(MEDIA_ROOT=media.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)

    def role_routes(self):
        campaign_id, task_id = self.campaign.pk, self.task.pk
        return {
            "client": [
                ("client_dashboard", ()), ("client_profile", ()), ("campaign_request", ()),
                ("client_campaign_list", ()), ("client_campaign_tracking", ()),
                ("client_deliverables", ()), ("client_reports", ()),
                ("client_campaign_detail", (campaign_id,)),
                ("client_campaign_report", (campaign_id,)),
            ],
            "administrator": [
                ("administrator_dashboard", ()), ("administrator_employee_list", ()),
                ("administrator_employee_create", ()),
                ("administrator_employee_edit", (self.employee.pk,)),
                ("administrator_campaign_detail", (campaign_id,)),
                ("administrator_task_create", (campaign_id,)),
                ("administrator_campaign_report", (campaign_id,)),
            ],
            "employee": [
                ("employee_dashboard", ()), ("employee_profile", ()), ("employee_task_list", ()),
                ("employee_deliverable_campaigns", ()),
                ("employee_task_detail", (task_id,)),
                ("employee_campaign_detail", (campaign_id,)),
                ("employee_deliverable_upload", (campaign_id,)),
            ],
        }


class FinalWorkflowAuditTests(AuditFixtures):
    def test_role_pages_render_and_wrong_roles_are_redirected(self):
        users = {"client": self.owner, "administrator": self.staff, "employee": self.employee_user}
        logins = {"client": "login", "administrator": "administrator_login", "employee": "employee_login"}
        for role, routes in self.role_routes().items():
            for name, args in routes:
                url = reverse(name, args=args)
                for audience, user in users.items():
                    with self.subTest(page=name, audience=audience):
                        self.client.force_login(user)
                        response = self.client.get(url)
                        if audience == role:
                            self.assertEqual(response.status_code, 200)
                        else:
                            self.assertRedirects(response, f'{reverse(logins[role])}?next={url}')

    def test_anonymous_pages_redirect_to_correct_login(self):
        logins = {"client": "login", "administrator": "administrator_login", "employee": "employee_login"}
        for role, routes in self.role_routes().items():
            for name, args in routes:
                with self.subTest(page=name):
                    url = reverse(name, args=args)
                    self.assertRedirects(self.client.get(url), f'{reverse(logins[role])}?next={url}')

    def test_client_dashboard_actions_lead_to_owned_campaign_reports(self):
        other = Campaign.objects.create(client=self.other_client, name="Private Campaign", description="Private")
        self.client.force_login(self.owner)
        dashboard = self.client.get(reverse("client_dashboard"))
        for label, destination in (
            ("View Campaigns", "client_campaign_list"),
            ("Track Campaigns", "client_campaign_tracking"),
            ("View Reports", "client_reports"), ("Review Deliverables", "client_deliverables"),
        ):
            self.assertContains(
                dashboard,
                f'<a class="btn btn-outline-primary" href="{reverse(destination)}">{label}</a>',
                html=True,
            )
        campaigns = self.client.get(reverse("client_reports"))
        self.assertContains(campaigns, f'href="{reverse("client_campaign_report", args=(self.campaign.pk,))}"')
        self.assertNotContains(campaigns, f'href="{reverse("client_campaign_report", args=(other.pk,))}"')

    def test_role_navigation_uses_existing_destinations(self):
        for user, dashboard, destinations in (
            (self.owner, "client_dashboard", ("client_dashboard", "client_campaign_list", "client_profile")),
            (self.staff, "administrator_dashboard", ("administrator_dashboard", "administrator_employee_list")),
            (self.employee_user, "employee_dashboard", ("employee_dashboard", "employee_task_list", "employee_profile")),
        ):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse(dashboard))
                navigation = response.content.decode().split("<nav", 1)[1].split("</nav>", 1)[0]
                for destination in destinations:
                    self.assertIn(f'href="{reverse(destination)}"', navigation)
                    self.assertEqual(self.client.get(reverse(destination)).status_code, 200)
                if user == self.staff:
                    self.assertIn(f'href="{reverse(dashboard)}#campaigns"', navigation)
                    self.assertContains(response, 'id="campaigns"')
                if user == self.employee_user:
                    self.assertIn(f'href="{reverse(dashboard)}#assigned-campaigns"', navigation)
                    self.assertContains(response, 'id="assigned-campaigns"')

    def test_administrator_counts_cover_all_campaign_statuses(self):
        for index, status in enumerate(Campaign.Status, start=1):
            for number in range(index):
                Campaign.objects.create(client=self.owner, name=f"{status}-{number}", description="Counts", status=status)
        self.client.force_login(self.staff)
        response = self.client.get(reverse("administrator_dashboard"))
        expected = {"pending_campaigns": 1, "approved_campaigns": 3, "rejected_campaigns": 3,
                    "in_progress_campaigns": 4, "completed_campaigns": 5}
        for key, value in expected.items():
            self.assertEqual(response.context[key], value)
        self.assertEqual(response.context["total_campaigns"], sum(expected.values()))
        self.assertContains(response, "In Progress Campaigns")
        self.assertContains(response, "Rejected Campaigns")

    def test_campaign_detail_pages_show_saved_progress_and_zero_budget(self):
        for user, role in ((self.owner, "client"), (self.staff, "administrator"), (self.employee_user, "employee")):
            with self.subTest(role=role):
                self.client.force_login(user)
                response = self.client.get(reverse(f"{role}_campaign_detail", args=(self.campaign.pk,)))
                self.assertContains(response, "0%")
                self.assertContains(response, "0.00")
                self.assertContains(response, "Social Media")

    def test_get_requests_do_not_apply_update_parameters(self):
        cases = [
            (self.staff, "administrator_campaign_detail", (self.campaign.pk,),
             {"status-status": "completed", "update_status": "1"}),
            (self.staff, "administrator_campaign_detail", (self.campaign.pk,),
             {"assignment-assigned_employee": self.other_employee.pk, "update_assignment": "1"}),
            (self.employee_user, "employee_campaign_detail", (self.campaign.pk,),
             {"progress_percentage": 100, "status": "completed"}),
            (self.staff, "administrator_task_create", (self.campaign.pk,),
             {"title": "GET task", "due_date": "2026-10-01", "assigned_employee": self.employee.pk}),
            (self.owner, "client_profile", (), {"first_name": "Changed", "email": "changed@example.com"}),
            (self.employee_user, "employee_profile", (), {"first_name": "Changed", "email": "changed@example.com"}),
            (self.employee_user, "employee_deliverable_upload", (self.campaign.pk,), {"title": "GET upload"}),
        ]
        models = (Campaign, Task, Deliverable, EmployeeProfile)
        before = [list(model.objects.values()) for model in models]
        for user, name, args, data in cases:
            with self.subTest(page=name, data=data):
                self.client.force_login(user)
                self.assertEqual(self.client.get(reverse(name, args=args), data).status_code, 200)
        self.assertEqual([list(model.objects.values()) for model in models], before)
        self.owner.refresh_from_db()
        self.employee_user.refresh_from_db()
        self.assertEqual(self.owner.email, "client@example.com")
        self.assertEqual(self.employee_user.email, "employee@example.com")

    def test_actions_require_post_and_anonymous_actions_require_login(self):
        actions = [
            (self.staff, "administrator_login", "administrator_campaign_decision", (self.campaign.pk, "approve")),
            (self.staff, "administrator_login", "administrator_campaign_decision", (self.campaign.pk, "reject")),
            (self.employee_user, "employee_login", "employee_task_status_update", (self.task.pk,)),
            (self.owner, "login", "client_deliverable_decision", (self.campaign.pk, self.deliverable.pk, "approve")),
            (self.owner, "login", "client_deliverable_decision", (self.campaign.pk, self.deliverable.pk, "reject")),
        ]
        for user, login, name, args in actions:
            with self.subTest(action=name, args=args):
                url = reverse(name, args=args)
                self.client.force_login(user)
                self.assertEqual(self.client.get(url).status_code, 405)
                self.client.logout()
                self.assertRedirects(self.client.get(url), f'{reverse(login)}?next={url}')
                self.assertRedirects(self.client.post(url), f'{reverse(login)}?next={url}')

    def test_update_endpoints_reject_posts_without_csrf(self):
        browser = Client(enforce_csrf_checks=True)
        cases = [
            (self.staff, "administrator_campaign_decision", (self.campaign.pk, "approve")),
            (self.staff, "administrator_campaign_detail", (self.campaign.pk,)),
            (self.staff, "administrator_task_create", (self.campaign.pk,)),
            (self.staff, "administrator_employee_create", ()),
            (self.staff, "administrator_employee_edit", (self.employee.pk,)),
            (self.employee_user, "employee_campaign_detail", (self.campaign.pk,)),
            (self.employee_user, "employee_task_status_update", (self.task.pk,)),
            (self.employee_user, "employee_deliverable_upload", (self.campaign.pk,)),
            (self.employee_user, "employee_profile", ()),
            (self.owner, "client_deliverable_decision", (self.campaign.pk, self.deliverable.pk, "approve")),
            (self.owner, "client_profile", ()), (self.owner, "campaign_request", ()),
            (self.owner, "logout", ()),
        ]
        for user, name, args in cases:
            with self.subTest(action=name):
                browser.force_login(user)
                self.assertEqual(browser.post(reverse(name, args=args), {}).status_code, 403)

    def test_other_employee_cannot_post_progress_or_deliverables(self):
        self.client.force_login(self.other_employee_user)
        self.assertEqual(self.client.post(reverse("employee_campaign_detail", args=(self.campaign.pk,)), {
            "progress_percentage": 100, "status": Campaign.Status.COMPLETED,
        }).status_code, 404)
        self.assertEqual(self.client.post(reverse("employee_deliverable_upload", args=(self.campaign.pk,)), {
            "title": "Unauthorized", "uploaded_file": SimpleUploadedFile("private.pdf", b"private"),
        }).status_code, 404)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.progress_percentage, 0)
        self.assertFalse(Deliverable.objects.filter(title="Unauthorized").exists())

    def test_deliverable_campaign_id_mismatch_cannot_change_approval(self):
        other = Campaign.objects.create(client=self.owner, name="Second campaign", description="Other")
        self.client.force_login(self.owner)
        response = self.client.post(reverse("client_deliverable_decision", args=(other.pk, self.deliverable.pk, "approve")))
        self.assertEqual(response.status_code, 404)
        self.deliverable.refresh_from_db()
        self.assertEqual(self.deliverable.approval_status, Deliverable.ApprovalStatus.PENDING)

    def test_admin_can_deactivate_employee_and_active_session_loses_access(self):
        employee_browser = Client()
        employee_browser.force_login(self.employee_user)
        self.client.force_login(self.staff)
        response = self.client.post(reverse("administrator_employee_edit", args=(self.employee.pk,)), {
            "first_name": "Maya", "last_name": "Singh", "email": "employee@example.com",
            "job_title": "Campaign Specialist", "phone": "12345",
        })
        self.assertRedirects(response, reverse("administrator_employee_list"))
        self.employee_user.refresh_from_db()
        self.assertFalse(self.employee_user.is_active)
        self.assertContains(self.client.get(reverse("administrator_employee_list")), "Inactive")
        url = reverse("employee_dashboard")
        self.assertRedirects(employee_browser.get(url), f'{reverse("employee_login")}?next={url}')

    def test_employee_profile_updates_only_own_account(self):
        self.client.force_login(self.employee_user)
        response = self.client.post(reverse("employee_profile"), {
            "first_name": "Updated", "last_name": "Employee", "email": "UPDATED@example.com",
            "job_title": "SEO Specialist", "phone": "55555", "user_id": self.other_employee_user.pk,
            "username": "forgedname", "is_staff": True,
        })
        self.assertRedirects(response, reverse("employee_profile"))
        self.employee_user.refresh_from_db()
        self.employee.refresh_from_db()
        self.other_employee_user.refresh_from_db()
        self.assertEqual(self.employee_user.get_full_name(), "Updated Employee")
        self.assertEqual(self.employee_user.email, "updated@example.com")
        self.assertEqual(self.employee.job_title, "SEO Specialist")
        self.assertEqual(self.employee_user.username, "auditemployee")
        self.assertFalse(self.employee_user.is_staff)
        self.assertEqual(self.other_employee_user.first_name, "")

    def test_complete_client_admin_employee_client_workflow(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("campaign_request"), {
            "name": "Submission Demo", "description": "Launch campaign", "campaign_type": "Social Media",
            "budget": "5000.00", "start_date": timezone.localdate().isoformat(),
            "end_date": (timezone.localdate() + timedelta(days=30)).isoformat(),
            "client": self.other_client.pk, "status": Campaign.Status.COMPLETED,
        })
        self.assertRedirects(response, reverse("client_campaign_list"))
        campaign = Campaign.objects.get(name="Submission Demo")
        self.assertEqual(campaign.client, self.owner)
        self.assertEqual(campaign.status, Campaign.Status.PENDING)

        self.client.force_login(self.staff)
        admin_detail = reverse("administrator_campaign_detail", args=(campaign.pk,))
        self.assertRedirects(self.client.post(reverse("administrator_campaign_decision", args=(campaign.pk, "approve"))), admin_detail)
        self.assertRedirects(self.client.post(admin_detail, {
            "assignment-assigned_employee": self.employee.pk, "update_assignment": "1",
        }), admin_detail)
        self.assertRedirects(self.client.post(reverse("administrator_task_create", args=(campaign.pk,)), {
            "title": "Demo Task", "description": "Prepare demo", "due_date": "2026-10-01",
            "assigned_employee": self.employee.pk,
        }), admin_detail)
        task = campaign.tasks.get()

        self.client.force_login(self.employee_user)
        self.assertContains(self.client.get(reverse("employee_dashboard")), "Submission Demo")
        employee_detail = reverse("employee_campaign_detail", args=(campaign.pk,))
        self.assertRedirects(self.client.post(employee_detail, {
            "progress_percentage": 65, "status": Campaign.Status.IN_PROGRESS,
        }), employee_detail)
        for status in (Task.Status.IN_PROGRESS, Task.Status.COMPLETED):
            self.assertRedirects(self.client.post(reverse("employee_task_status_update", args=(task.pk,)), {
                "status": status,
            }), reverse("employee_task_detail", args=(task.pk,)))
            task.refresh_from_db()
            self.assertEqual(task.status, status)
        for title in ("Final Creative", "Alternative Creative"):
            self.assertRedirects(self.client.post(reverse("employee_deliverable_upload", args=(campaign.pk,)), {
                "title": title, "uploaded_file": SimpleUploadedFile("creative.pdf", b"demo file content"),
            }), employee_detail)

        self.client.force_login(self.owner)
        client_detail = reverse("client_campaign_detail", args=(campaign.pk,))
        self.assertContains(self.client.get(client_detail), "65%")
        tracking = self.client.get(reverse("client_campaign_tracking"))
        self.assertContains(tracking, "65%")
        self.assertContains(tracking, "1 / 1")
        for title, decision in (("Final Creative", "approve"), ("Alternative Creative", "reject")):
            deliverable = campaign.deliverables.get(title=title)
            file_response = self.client.get(deliverable.uploaded_file.url)
            self.assertEqual(file_response.status_code, 200)
            self.assertEqual(b"".join(file_response.streaming_content), b"demo file content")
            file_response.close()
            self.assertRedirects(self.client.post(reverse("client_deliverable_decision", args=(campaign.pk, deliverable.pk, decision))), client_detail)
        self.assertRedirects(self.client.post(reverse("client_profile"), {
            "first_name": "Anita", "last_name": "Rao", "email": "anita@example.com", "username": "cannotchange",
        }), reverse("client_profile"))
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.username, "auditclient")
        for user, role in ((self.owner, "client"), (self.staff, "administrator")):
            self.client.force_login(user)
            report = self.client.get(reverse(f"{role}_campaign_report", args=(campaign.pk,)))
            self.assertEqual(report.context["task_summary"]["completed"], 1)
            self.assertEqual(report.context["task_completion_percentage"], 100)
            self.assertEqual(report.context["deliverable_summary"], {"total": 2, "pending": 0, "approved": 1, "rejected": 1})
            self.assertContains(report, "65%")
            self.assertContains(report, "Anita Rao")
            self.assertContains(report, "window.print()")

        self.client.force_login(self.employee_user)
        self.assertRedirects(self.client.post(employee_detail, {
            "progress_percentage": 65, "status": Campaign.Status.COMPLETED,
        }), employee_detail)
        self.client.force_login(self.staff)
        final_report = self.client.get(reverse("administrator_campaign_report", args=(campaign.pk,)))
        self.assertEqual(final_report.context["campaign"].status, Campaign.Status.COMPLETED)
        self.assertEqual(final_report.context["campaign"].progress_percentage, 100)


class ProtectedDeliverableFileTests(AuditFixtures):
    def setUp(self):
        super().setUp()
        self.deliverable.uploaded_file.save("audit.pdf", SimpleUploadedFile("audit.pdf", b"private campaign file"))
        self.url = self.deliverable.uploaded_file.url

    def test_owner_assigned_employee_staff_and_superuser_can_open_existing_file_url(self):
        for user in (self.owner, self.employee_user, self.staff, self.superuser):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(self.url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "application/pdf")
                self.assertEqual(response["Cache-Control"], "private, no-store")
                self.assertEqual(b"".join(response.streaming_content), b"private campaign file")
                response.close()

    def test_anonymous_file_access_redirects_to_login(self):
        self.assertRedirects(self.client.get(self.url), f'{reverse("login")}?next={self.url}')

    def test_other_client_and_employee_cannot_open_file_even_with_exact_url(self):
        for user in (self.other_client, self.other_employee_user):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_original_uploader_loses_access_after_campaign_reassignment(self):
        Campaign.objects.filter(pk=self.campaign.pk).update(assigned_employee=self.other_employee)
        self.client.force_login(self.employee_user)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.force_login(self.other_employee_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_missing_file_returns_404(self):
        self.client.force_login(self.owner)
        Deliverable.objects.filter(pk=self.deliverable.pk).update(uploaded_file="deliverables/missing.pdf")
        self.assertEqual(self.client.get("/media/deliverables/missing.pdf").status_code, 404)

    def test_unregistered_media_and_path_traversal_are_not_served(self):
        (self.media_root / "unregistered.pdf").write_bytes(b"not a deliverable")
        self.client.force_login(self.staff)
        for url in ("/media/unregistered.pdf", "/media/../manage.py", "/media/%2e%2e/manage.py"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_files_allow_only_get_and_head(self):
        self.client.force_login(self.owner)
        response = self.client.head(self.url)
        self.assertEqual(response.status_code, 200)
        response.close()
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(self.url).status_code, 405)

    @override_settings(DEBUG=False)
    def test_file_permissions_remain_active_without_debug_mode(self):
        self.client.force_login(self.other_client)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        response.close()
