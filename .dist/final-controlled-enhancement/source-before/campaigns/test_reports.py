from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from .models import Campaign, Deliverable, EmployeeProfile, Task


class CampaignReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            "reportclient", email="client@example.com", first_name="Anita", last_name="Rao",
        )
        cls.other_client = User.objects.create_user("otherreportclient")
        cls.staff = User.objects.create_user("reportadmin", is_staff=True)
        cls.superuser = User.objects.create_user("reportsuperuser", is_superuser=True)
        cls.employee_user = User.objects.create_user(
            "reportemployee", email="employee@example.com", first_name="Maya", last_name="Singh",
        )
        cls.employee = EmployeeProfile.objects.create(
            user=cls.employee_user, job_title="Campaign Specialist",
        )
        cls.campaign = Campaign.objects.create(
            client=cls.owner,
            assigned_employee=cls.employee,
            name="Autumn Launch",
            description="Introduce the autumn collection.",
            campaign_type="Social Media",
            target_audience="Local shoppers",
            budget="25000.00",
            start_date=date(2026, 9, 10),
            end_date=date(2026, 10, 10),
            status=Campaign.Status.IN_PROGRESS,
            progress_percentage=40,
        )
        for index, status in enumerate((
            Task.Status.PENDING, Task.Status.IN_PROGRESS,
            Task.Status.COMPLETED, Task.Status.COMPLETED, Task.Status.COMPLETED,
        ), start=1):
            Task.objects.create(
                campaign=cls.campaign,
                assigned_employee=cls.employee,
                title=f"Campaign task {index}",
                description=f"Task instructions {index}.",
                due_date=date(2026, 9, 15),
                status=status,
            )
        for index, status in enumerate((
            Deliverable.ApprovalStatus.PENDING,
            Deliverable.ApprovalStatus.APPROVED, Deliverable.ApprovalStatus.APPROVED,
            Deliverable.ApprovalStatus.REJECTED, Deliverable.ApprovalStatus.REJECTED,
            Deliverable.ApprovalStatus.REJECTED,
        ), start=1):
            Deliverable.objects.create(
                campaign=cls.campaign,
                uploaded_by=cls.employee,
                title=f"Creative version {index}",
                description=f"Deliverable notes {index}.",
                # A stored path exercises link rendering without writing test files.
                uploaded_file=f"deliverables/report-creative-{index}.pdf",
                approval_status=status,
            )

    def report_url(self, role="client", campaign=None):
        return reverse(f"{role}_campaign_report", args=((campaign or self.campaign).pk,))

    def report_audiences(self):
        return (("administrator", self.staff), ("client", self.owner))

    def test_staff_can_view_campaign_report(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.report_url("administrator"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "campaigns/campaign_report.html")
        self.assertEqual(response.context["campaign"], self.campaign)

    def test_superuser_without_staff_flag_can_view_admin_report(self):
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(self.report_url("administrator")).status_code, 200)

    def test_client_can_view_own_campaign_report(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.report_url())
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "campaigns/campaign_report.html")

    def test_client_cannot_view_another_clients_campaign_report(self):
        self.client.force_login(self.other_client)
        response = self.client.get(self.report_url())
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, self.campaign.name, status_code=404)
        self.assertNotContains(response, "Creative version 1", status_code=404)

    def test_employee_cannot_view_client_report_even_if_campaign_owner(self):
        Campaign.objects.filter(pk=self.campaign.pk).update(client=self.employee_user)
        self.client.force_login(self.employee_user)
        url = self.report_url()
        self.assertRedirects(self.client.get(url), f'{reverse("login")}?next={url}')

    def test_staff_and_superuser_cannot_view_client_report(self):
        for user in (self.staff, self.superuser):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                url = self.report_url()
                self.assertRedirects(self.client.get(url), f'{reverse("login")}?next={url}')

    def test_non_admins_cannot_view_admin_report(self):
        for user in (self.owner, self.other_client, self.employee_user):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                url = self.report_url("administrator")
                self.assertRedirects(
                    self.client.get(url), f'{reverse("administrator_login")}?next={url}',
                )

    def test_anonymous_users_redirect_to_role_login(self):
        for role, login_name in (("administrator", "administrator_login"), ("client", "login")):
            with self.subTest(role=role):
                url = self.report_url(role)
                self.assertRedirects(self.client.get(url), f'{reverse(login_name)}?next={url}')

    def test_missing_campaign_returns_404(self):
        for role, user in self.report_audiences():
            with self.subTest(role=role):
                self.client.force_login(user)
                url = reverse(f"{role}_campaign_report", args=(999999,))
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_reports_are_get_only(self):
        for role, user in self.report_audiences():
            self.client.force_login(user)
            for method in ("post", "put", "patch", "delete", "head", "options"):
                with self.subTest(role=role, method=method):
                    response = getattr(self.client, method)(self.report_url(role))
                    self.assertEqual(response.status_code, 405)
                    self.assertEqual(response.headers["Allow"], "GET")

    def test_reports_show_campaign_client_and_employee_details(self):
        for role, user in self.report_audiences():
            with self.subTest(role=role):
                self.client.force_login(user)
                response = self.client.get(self.report_url(role))
                for value in (
                    "Autumn Launch", "Introduce the autumn collection.", "Social Media",
                    "Local shoppers", "25000.00", "Sep 10, 2026", "Oct 10, 2026",
                    "In Progress", "40%", "reportclient", "Anita Rao", "client@example.com",
                    "Maya Singh", "Campaign Specialist", "employee@example.com",
                ):
                    self.assertContains(response, value)

    def test_reports_show_correct_task_counts_and_percentage(self):
        for role, user in self.report_audiences():
            with self.subTest(role=role):
                self.client.force_login(user)
                response = self.client.get(self.report_url(role))
                self.assertEqual(response.context["task_summary"], {
                    "total": 5, "pending": 1, "in_progress": 1, "completed": 3,
                })
                self.assertEqual(response.context["task_completion_percentage"], 60)
                self.assertContains(response, "3 of 5 tasks completed")
                self.assertContains(response, "60%")
                self.assertContains(response, 'aria-label="Campaign progress" aria-valuenow="40"')
                self.assertContains(response, 'aria-label="Task completion" aria-valuenow="60"')

    def test_reports_show_each_task_and_deliverable(self):
        for role, user in self.report_audiences():
            with self.subTest(role=role):
                self.client.force_login(user)
                response = self.client.get(self.report_url(role))
                for task in self.campaign.tasks.all():
                    for value in (task.title, task.description, task.get_status_display(), "Sep 15, 2026"):
                        self.assertContains(response, value)
                for deliverable in self.campaign.deliverables.all():
                    for value in (
                        deliverable.title, deliverable.description,
                        deliverable.get_approval_status_display(), deliverable.uploaded_file.url,
                        date_format(timezone.localtime(deliverable.uploaded_at), "M j, Y, H:i T"),
                    ):
                        self.assertContains(response, value)
                self.assertContains(response, "Maya Singh")

    def test_reports_show_correct_deliverable_approval_counts(self):
        for role, user in self.report_audiences():
            with self.subTest(role=role):
                self.client.force_login(user)
                response = self.client.get(self.report_url(role))
                self.assertEqual(response.context["deliverable_summary"], {
                    "total": 6, "pending": 1, "approved": 2, "rejected": 3,
                })
                self.assertContains(response, "2 approved, 1 pending review, 3 rejected")

    def test_reports_exclude_other_campaigns_tasks_and_deliverables(self):
        for owner in (self.owner, self.other_client):
            other_campaign = Campaign.objects.create(
                client=owner, name="Unrelated campaign", description="Other campaign details",
            )
            Task.objects.create(
                campaign=other_campaign, title="Unrelated task", due_date=date(2026, 10, 1),
                status=Task.Status.COMPLETED,
            )
            Deliverable.objects.create(
                campaign=other_campaign, uploaded_by=self.employee,
                title="Unrelated deliverable", uploaded_file="deliverables/unrelated.pdf",
                approval_status=Deliverable.ApprovalStatus.APPROVED,
            )
        for role, user in self.report_audiences():
            with self.subTest(role=role):
                self.client.force_login(user)
                response = self.client.get(self.report_url(role))
                for value in ("Unrelated campaign", "Unrelated task", "Unrelated deliverable", "unrelated.pdf"):
                    self.assertNotContains(response, value)
                self.assertEqual(response.context["task_summary"]["total"], 5)
                self.assertEqual(response.context["task_summary"]["completed"], 3)
                self.assertEqual(response.context["deliverable_summary"]["total"], 6)
                self.assertEqual(response.context["deliverable_summary"]["approved"], 2)

    def test_empty_campaign_has_zero_summaries_and_missing_data_fallbacks(self):
        empty_campaign = Campaign.objects.create(client=self.other_client, name="Empty report", description="Empty")
        for role, user in (("administrator", self.staff), ("client", self.other_client)):
            with self.subTest(role=role):
                self.client.force_login(user)
                response = self.client.get(self.report_url(role, empty_campaign))
                self.assertEqual(response.context["task_completion_percentage"], 0)
                self.assertEqual(response.context["task_summary"], {
                    "total": 0, "pending": 0, "in_progress": 0, "completed": 0,
                })
                self.assertEqual(response.context["deliverable_summary"], {
                    "total": 0, "pending": 0, "approved": 0, "rejected": 0,
                })
                for value in (
                    "0 of 0 tasks completed", "No tasks have been created",
                    "No deliverables have been uploaded", "No employee assigned.",
                    "Not specified", "Not provided", "otherreportclient",
                ):
                    self.assertContains(response, value)

    def test_unassigned_task_and_missing_file_do_not_crash(self):
        self.campaign.tasks.update(assigned_employee=None, description="")
        self.campaign.deliverables.update(uploaded_file="", description="")
        self.employee.job_title = ""
        self.employee.save(update_fields=("job_title",))
        self.employee_user.email = ""
        self.employee_user.save(update_fields=("email",))
        self.client.force_login(self.owner)
        response = self.client.get(self.report_url())
        for value in ("Unassigned", "No file available", "No description", "Not provided"):
            self.assertContains(response, value)
        self.assertNotContains(response, "Open file")

    def test_zero_budget_is_displayed_as_zero(self):
        Campaign.objects.filter(pk=self.campaign.pk).update(budget=0)
        self.client.force_login(self.owner)
        response = self.client.get(self.report_url())
        self.assertContains(response, '<dd class="col-sm-8">0.00</dd>', html=True)

    def test_fractional_task_percentage_is_rounded(self):
        # Keep three tasks: one pending, one in progress, one completed.
        self.campaign.tasks.filter(title__in=("Campaign task 4", "Campaign task 5")).delete()
        self.client.force_login(self.owner)
        response = self.client.get(self.report_url())
        self.assertEqual(response.context["task_completion_percentage"], 33.3)
        self.assertContains(response, "33.3%")

    def test_reports_refresh_from_current_data(self):
        self.client.force_login(self.owner)
        self.client.get(self.report_url())
        self.campaign.tasks.update(status=Task.Status.COMPLETED)
        self.campaign.deliverables.update(approval_status=Deliverable.ApprovalStatus.APPROVED)
        Campaign.objects.filter(pk=self.campaign.pk).update(progress_percentage=85)
        response = self.client.get(self.report_url())
        self.assertEqual(response.context["task_summary"]["completed"], 5)
        self.assertEqual(response.context["task_completion_percentage"], 100)
        self.assertEqual(response.context["deliverable_summary"]["approved"], 6)
        self.assertEqual(response.context["deliverable_summary"]["pending"], 0)
        self.assertEqual(response.context["deliverable_summary"]["rejected"], 0)
        self.assertContains(response, "85%")

    def test_get_and_rejected_post_do_not_change_campaign_data(self):
        models = (Campaign, Task, Deliverable)
        before = [list(model.objects.values()) for model in models]
        for role, user in self.report_audiences():
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.report_url(role)).status_code, 200)
            response = self.client.post(self.report_url(role), {
                "status": Campaign.Status.COMPLETED, "client": self.other_client.pk,
                "progress_percentage": 100,
            })
            self.assertEqual(response.status_code, 405)
        self.assertEqual([list(model.objects.values()) for model in models], before)

    def test_campaign_detail_buttons_and_report_back_links(self):
        for role, user in self.report_audiences():
            with self.subTest(role=role):
                self.client.force_login(user)
                detail_url = reverse(f"{role}_campaign_detail", args=(self.campaign.pk,))
                detail = self.client.get(detail_url)
                self.assertContains(detail, f'href="{self.report_url(role)}"')
                report = self.client.get(self.report_url(role))
                self.assertContains(report, f'href="{detail_url}"')
                self.assertContains(report, "Print / Save as PDF")
                self.assertContains(report, 'onclick="window.print()"')
                self.assertContains(report, "campaigns/css/report.css")

    def test_user_content_is_html_escaped(self):
        Campaign.objects.filter(pk=self.campaign.pk).update(description='<script>alert("campaign")</script>')
        self.campaign.tasks.update(description="<script>task()</script>")
        self.campaign.deliverables.update(title="<script>deliverable()</script>")
        self.client.force_login(self.owner)
        response = self.client.get(self.report_url())
        self.assertContains(response, "&lt;script&gt;alert(&quot;campaign&quot;)&lt;/script&gt;")
        self.assertContains(response, "&lt;script&gt;task()&lt;/script&gt;")
        self.assertContains(response, "&lt;script&gt;deliverable()&lt;/script&gt;")

    def test_reports_support_every_campaign_status(self):
        for status in Campaign.Status:
            Campaign.objects.filter(pk=self.campaign.pk).update(status=status)
            for role, user in self.report_audiences():
                with self.subTest(status=status, role=role):
                    self.client.force_login(user)
                    self.assertContains(self.client.get(self.report_url(role)), status.label)
