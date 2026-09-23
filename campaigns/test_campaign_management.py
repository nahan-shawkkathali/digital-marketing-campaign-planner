from datetime import timedelta
from unittest.mock import patch

from django.test import Client
from django.urls import reverse
from django.utils import timezone

from .forms import CampaignAssignmentForm, CampaignRequestForm
from .models import Campaign, Deliverable, Task
from .test_audit import AuditFixtures


class PendingCampaignEditTests(AuditFixtures):
    def setUp(self):
        super().setUp()
        self.campaign.status = Campaign.Status.PENDING
        self.campaign.save(update_fields=("status",))
        self.client.force_login(self.owner)
        self.url = reverse("client_campaign_edit", args=(self.campaign.pk,))

    def data(self, **overrides):
        return {"name": "Corrected Campaign", "description": "Corrected requirements",
                "campaign_type": "Social", "product_service_name": "Serum", "budget": "123.00",
                "target_audience": "Shoppers", "platforms": "Instagram", "campaign_goal": "Awareness",
                "start_date": timezone.localdate().isoformat(),
                "end_date": (timezone.localdate() + timedelta(days=30)).isoformat(), **overrides}

    def test_owner_can_edit_all_request_fields_without_changing_protected_fields(self):
        response = self.client.get(self.url)
        self.assertIsInstance(response.context["form"], CampaignRequestForm)
        self.assertEqual(response.context["form"]["name"].value(), self.campaign.name)
        response = self.client.post(self.url, self.data(client=self.other_client.pk,
            status="approved", assigned_employee=self.other_employee.pk, progress_percentage=100))
        self.assertRedirects(response, reverse("client_campaign_detail", args=(self.campaign.pk,)))
        self.campaign.refresh_from_db()
        for field, value in self.data().items():
            self.assertEqual(str(getattr(self.campaign, field)), value)
        self.assertEqual(self.campaign.client, self.owner)
        self.assertEqual(self.campaign.status, Campaign.Status.PENDING)
        self.assertEqual(self.campaign.assigned_employee, self.employee)
        self.assertEqual(self.campaign.progress_percentage, 0)

    def test_other_client_and_nonexistent_ids_cannot_be_edited(self):
        self.client.force_login(self.other_client)
        for url in (self.url, reverse("client_campaign_edit", args=(999999,))):
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, self.data()).status_code, 404)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.name, "Audit Campaign")

    def test_every_nonpending_status_is_locked_and_has_no_edit_links(self):
        for status in Campaign.Status.values:
            if status == Campaign.Status.PENDING:
                continue
            with self.subTest(status=status):
                Campaign.objects.filter(pk=self.campaign.pk).update(status=status)
                self.assertEqual(self.client.get(self.url).status_code, 403)
                self.assertEqual(self.client.post(self.url, self.data()).status_code, 403)
                for page, args in (("client_campaign_list", ()), ("client_campaign_detail", (self.campaign.pk,))):
                    self.assertNotContains(self.client.get(reverse(page, args=args)), self.url)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.name, "Audit Campaign")

    def test_pending_edit_links_are_visible(self):
        for page, args in (("client_campaign_list", ()), ("client_campaign_detail", (self.campaign.pk,))):
            self.assertContains(self.client.get(reverse(page, args=args)), self.url)

    def test_invalid_budget_dates_and_required_fields_do_not_save(self):
        for changes, field in (({"budget": "-1"}, "budget"), ({"end_date": (timezone.localdate() - timedelta(days=1)).isoformat()}, "end_date"),
                               ({"name": ""}, "name")):
            response = self.client.post(self.url, self.data(**changes))
            self.assertIn(field, response.context["form"].errors)
            self.campaign.refresh_from_db()
            self.assertEqual(self.campaign.name, "Audit Campaign")

    def test_approval_during_form_validation_cannot_be_overwritten(self):
        validate = CampaignRequestForm.is_valid
        def approve_then_validate(form):
            Campaign.objects.filter(pk=self.campaign.pk).update(status=Campaign.Status.APPROVED)
            return validate(form)
        with patch.object(CampaignRequestForm, "is_valid", approve_then_validate):
            self.assertEqual(self.client.post(self.url, self.data()).status_code, 403)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, Campaign.Status.APPROVED)
        self.assertEqual(self.campaign.name, "Audit Campaign")

    def test_role_method_and_csrf_restrictions(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        self.assertEqual(browser.post(self.url, self.data()).status_code, 403)
        for method in ("put", "patch", "delete"):
            self.assertEqual(getattr(self.client, method)(self.url).status_code, 405)
        for user in (None, self.employee_user, self.staff, self.superuser):
            self.client.logout()
            if user:
                self.client.force_login(user)
            for method in ("get", "post"):
                self.assertRedirects(getattr(self.client, method)(self.url),
                                     f'{reverse("login")}?next={self.url}')


class CampaignArchiveTests(AuditFixtures):
    def setUp(self):
        super().setUp()
        self.url = reverse("administrator_campaign_archive", args=(self.campaign.pk,))
        self.client.force_login(self.staff)

    def archive(self):
        return self.client.post(self.url, {"confirm": "yes"})

    def test_archive_confirmation_and_get_preserve_campaign(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Confirm Archive")
        self.assertContains(response, "1 task")
        self.assertContains(response, "1 deliverable")
        self.assertEqual(self.client.post(self.url).status_code, 400)
        self.campaign.refresh_from_db()
        self.assertFalse(self.campaign.is_archived)
        self.assertEqual(self.client.get(reverse("administrator_campaign_decision", args=(self.campaign.pk, "delete"))).status_code, 405)
        self.assertTrue(Campaign.objects.filter(pk=self.campaign.pk).exists())

    def test_archive_preserves_related_records_files_and_reports(self):
        before_tasks = list(Task.objects.values())
        before_deliverables = list(Deliverable.objects.values())
        path = self.media_root / self.deliverable.uploaded_file.name
        path.parent.mkdir(parents=True)
        path.write_bytes(b"original file")
        self.assertRedirects(self.archive(), reverse("administrator_campaign_detail", args=(self.campaign.pk,)))
        self.campaign.refresh_from_db()
        self.assertTrue(self.campaign.is_archived)
        self.assertEqual(self.campaign.status, Campaign.Status.APPROVED)
        self.assertEqual(self.campaign.assigned_employee, self.employee)
        self.assertEqual(list(Task.objects.values()), before_tasks)
        self.assertEqual(list(Deliverable.objects.values()), before_deliverables)
        self.assertEqual(path.read_bytes(), b"original file")
        self.assertContains(self.client.get(reverse("administrator_dashboard")), self.campaign.name)
        for user, name in ((self.staff, "administrator_campaign_report"), (self.owner, "client_campaign_report")):
            self.client.force_login(user)
            response = self.client.get(reverse(name, args=(self.campaign.pk,)))
            self.assertContains(response, "Archived campaign")
            self.assertContains(response, self.task.title)
            self.assertContains(response, self.deliverable.title)
            file_response = self.client.get(self.deliverable.uploaded_file.url)
            self.assertEqual(b"".join(file_response.streaming_content), b"original file")

    def test_archived_work_is_hidden_from_employee_active_lists(self):
        self.archive()
        self.client.force_login(self.employee_user)
        for page in ("employee_dashboard", "employee_deliverable_campaigns", "employee_task_list"):
            self.assertNotContains(self.client.get(reverse(page)), self.campaign.name)
        detail = self.client.get(reverse("employee_campaign_detail", args=(self.campaign.pk,)))
        self.assertContains(detail, "Archived campaign")
        self.assertNotContains(detail, "Update campaign progress")
        self.assertNotContains(detail, "Upload Deliverable")
        task = self.client.get(reverse("employee_task_detail", args=(self.task.pk,)))
        self.assertNotContains(task, ">Update Status</button>")

    def test_archived_campaign_blocks_assignment_status_task_creation_and_employee_writes(self):
        self.archive()
        for data in ({"update_assignment": "1", "assignment-assigned_employee": self.other_employee.pk},
                     {"update_status": "1", "status-status": "pending"}):
            self.assertEqual(self.client.post(reverse("administrator_campaign_detail", args=(self.campaign.pk,)), data).status_code, 403)
        self.assertEqual(self.client.post(reverse("administrator_task_create", args=(self.campaign.pk,))).status_code, 404)
        self.assertEqual(self.client.post(reverse("administrator_campaign_decision", args=(self.campaign.pk, "approve"))).status_code, 404)
        self.campaign.refresh_from_db()
        form = CampaignAssignmentForm({"assigned_employee": self.other_employee.pk}, instance=self.campaign)
        self.assertFalse(form.is_valid())
        self.client.force_login(self.employee_user)
        self.assertEqual(self.client.post(reverse("employee_campaign_detail", args=(self.campaign.pk,)), {
            "progress_percentage": 99, "status": "in_progress",
        }).status_code, 403)
        self.assertEqual(self.client.post(reverse("employee_task_status_update", args=(self.task.pk,)), {"status": "completed"}).status_code, 404)
        self.assertEqual(self.client.post(reverse("employee_deliverable_upload", args=(self.campaign.pk,))).status_code, 404)
        self.campaign.refresh_from_db()
        self.task.refresh_from_db()
        self.assertEqual(self.campaign.progress_percentage, 0)
        self.assertEqual(self.task.status, Task.Status.PENDING)

    def test_archived_pending_campaign_cannot_be_edited_or_reviewed(self):
        Campaign.objects.filter(pk=self.campaign.pk).update(status=Campaign.Status.PENDING)
        self.archive()
        self.client.force_login(self.owner)
        url = reverse("client_campaign_edit", args=(self.campaign.pk,))
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertNotContains(self.client.get(reverse("client_campaign_detail", args=(self.campaign.pk,))), url)
        self.assertEqual(self.client.post(reverse("client_deliverable_decision", args=(self.campaign.pk, self.deliverable.pk, "approve"))).status_code, 404)

    def test_archive_role_csrf_and_method_restrictions(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.staff)
        self.assertEqual(browser.post(self.url, {"confirm": "yes"}).status_code, 403)
        for method in ("put", "patch", "delete"):
            self.assertEqual(getattr(self.client, method)(self.url).status_code, 405)
        for user in (None, self.owner, self.other_client, self.employee_user):
            self.client.logout()
            if user:
                self.client.force_login(user)
            for method in ("get", "post"):
                self.assertRedirects(getattr(self.client, method)(self.url, {"confirm": "yes"} if method == "post" else {}),
                                     f'{reverse("administrator_login")}?next={self.url}')
        self.campaign.refresh_from_db()
        self.assertFalse(self.campaign.is_archived)

    def test_archive_is_idempotent_and_does_not_archive_other_campaigns(self):
        other = Campaign.objects.create(client=self.other_client, name="Other", description="Other")
        self.archive()
        self.archive()
        other.refresh_from_db()
        self.assertFalse(other.is_archived)
        self.assertEqual(Campaign.objects.count(), 2)


class AdministratorTaskManagementTests(AuditFixtures):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)
        self.edit_url = reverse("administrator_task_edit", args=(self.campaign.pk, self.task.pk))
        self.delete_url = reverse("administrator_task_delete", args=(self.campaign.pk, self.task.pk))

    def data(self, **overrides):
        return {"title": "Updated task", "description": "Updated brief", "due_date": "2026-10-15",
                "assigned_employee": self.employee.pk, **overrides}

    def test_admin_can_edit_task_without_changing_status_or_campaign(self):
        self.task.status = Task.Status.IN_PROGRESS
        self.task.save(update_fields=("status",))
        response = self.client.get(self.edit_url)
        self.assertEqual(response.context["form"]["title"].value(), self.task.title)
        self.assertNotIn("status", response.context["form"].fields)
        response = self.client.post(self.edit_url, self.data(status="completed", campaign=999999))
        self.assertRedirects(response, reverse("administrator_campaign_detail", args=(self.campaign.pk,)))
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, "Updated task")
        self.assertEqual(self.task.description, "Updated brief")
        self.assertEqual(str(self.task.due_date), "2026-10-15")
        self.assertEqual(self.task.status, Task.Status.IN_PROGRESS)
        self.assertEqual(self.task.campaign, self.campaign)

    def test_task_edit_preserves_employee_assignment_and_validation_rules(self):
        for data, field in ((self.data(assigned_employee=self.other_employee.pk), "assigned_employee"),
                             (self.data(due_date="invalid"), "due_date"), (self.data(title=""), "title")):
            response = self.client.post(self.edit_url, data)
            self.assertIn(field, response.context["form"].errors)
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, "Audit Task")
        self.assertEqual(self.task.assigned_employee, self.employee)

    def test_delete_requires_confirmation_and_only_removes_intended_task(self):
        other_campaign = Campaign.objects.create(client=self.other_client, name="Other", description="Other")
        other = Task.objects.create(campaign=other_campaign, title="Keep", due_date="2026-10-01")
        self.assertContains(self.client.get(self.delete_url), "Confirm Delete")
        self.assertTrue(Task.objects.filter(pk=self.task.pk).exists())
        self.assertEqual(self.client.post(self.delete_url).status_code, 400)
        self.assertTrue(Task.objects.filter(pk=self.task.pk).exists())
        self.assertRedirects(self.client.post(self.delete_url, {"confirm": "yes", "task_id": other.pk}),
                             reverse("administrator_campaign_detail", args=(self.campaign.pk,)))
        self.assertFalse(Task.objects.filter(pk=self.task.pk).exists())
        self.assertTrue(Task.objects.filter(pk=other.pk).exists())
        self.assertTrue(Deliverable.objects.filter(pk=self.deliverable.pk).exists())
        report = self.client.get(reverse("administrator_campaign_report", args=(self.campaign.pk,)))
        self.assertEqual(report.context["task_summary"]["total"], 0)

    def test_task_urls_require_matching_campaign_and_task_ids(self):
        other = Campaign.objects.create(client=self.other_client, name="Other", description="Other")
        for name in ("administrator_task_edit", "administrator_task_delete"):
            url = reverse(name, args=(other.pk, self.task.pk))
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, {"confirm": "yes", **self.data()}).status_code, 404)
        self.assertTrue(Task.objects.filter(pk=self.task.pk).exists())

    def test_archived_tasks_cannot_be_edited_or_deleted(self):
        Campaign.objects.filter(pk=self.campaign.pk).update(is_archived=True)
        for url in (self.edit_url, self.delete_url):
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, {"confirm": "yes", **self.data()}).status_code, 404)
        self.assertTrue(Task.objects.filter(pk=self.task.pk).exists())

    def test_task_management_is_admin_only(self):
        for user in (None, self.owner, self.other_client, self.employee_user, self.other_employee_user):
            self.client.logout()
            if user:
                self.client.force_login(user)
            for url in (self.edit_url, self.delete_url):
                self.assertRedirects(self.client.get(url), f'{reverse("administrator_login")}?next={url}')
                self.assertRedirects(self.client.post(url, {"confirm": "yes", **self.data()}),
                                     f'{reverse("administrator_login")}?next={url}')
        self.assertTrue(Task.objects.filter(pk=self.task.pk).exists())

    def test_task_management_requires_csrf_and_supported_methods(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.staff)
        for url in (self.edit_url, self.delete_url):
            self.assertEqual(browser.post(url, {"confirm": "yes", **self.data()}).status_code, 403)
            for method in ("put", "patch", "delete"):
                self.assertEqual(getattr(self.client, method)(url).status_code, 405)

    def test_employee_can_still_update_task_after_admin_edit(self):
        self.client.post(self.edit_url, self.data())
        self.client.force_login(self.employee_user)
        self.assertContains(self.client.get(reverse("employee_task_detail", args=(self.task.pk,))), "Updated task")
        self.client.post(reverse("employee_task_status_update", args=(self.task.pk,)), {"status": "completed"})
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.COMPLETED)
