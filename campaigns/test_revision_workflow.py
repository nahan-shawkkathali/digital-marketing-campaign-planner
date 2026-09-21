from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from .models import Campaign, ClientProfile, Deliverable, DeliverableMessage, Task
from .test_audit import AuditFixtures


class RevisionReportTests(AuditFixtures):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        ClientProfile.objects.create(user=cls.owner, company_name="GlowCare Cosmetics")
        cls.campaign.product_service_name = "Vitamin C Serum"
        cls.campaign.save(update_fields=("product_service_name",))
        cls.deliverable.approval_status = Deliverable.ApprovalStatus.CHANGES_REQUESTED
        cls.deliverable.save(update_fields=("approval_status",))
        cls.revision = Deliverable.objects.create(
            campaign=cls.campaign, uploaded_by=cls.employee, title="Updated creative",
            original=cls.deliverable, version=2, uploaded_file="deliverables/revision.pdf",
        )
        DeliverableMessage.objects.create(deliverable=cls.deliverable, sender=cls.owner,
                                          body="Private revision discussion", kind="changes_requested")

    def report(self, user, page):
        self.client.force_login(user)
        return self.client.get(reverse(page, args=(self.campaign.pk,)))

    def test_reports_count_current_versions_and_keep_version_history_without_full_discussion(self):
        for user, page in ((self.owner, "client_campaign_report"), (self.staff, "administrator_campaign_report")):
            response = self.report(user, page)
            self.assertEqual(response.context["deliverable_summary"], {"total": 1, "pending": 1, "approved": 0, "rejected": 0})
            self.assertEqual(response.context["changes_requested_count"], 0)
            self.assertEqual((response.context["total_versions"], response.context["revision_count"]), (2, 1))
            for value in ("GlowCare Cosmetics", "Vitamin C Serum", "Version 1", "Version 2", "Historical", "Current", "Changes Requested", "Pending Review"):
                self.assertContains(response, value)
            self.assertNotContains(response, "Private revision discussion")
            self.assertContains(response, 'onclick="window.print()"')
            self.assertContains(response, "campaigns/css/report.css")

    def test_reports_and_report_selection_refresh_current_changes_requested_and_approval(self):
        self.client.force_login(self.owner)
        for status, requests, approvals in (("changes_requested", 1, 0), ("approved", 0, 1)):
            Deliverable.objects.filter(pk=self.revision.pk).update(approval_status=status)
            response = self.client.get(reverse("client_campaign_report", args=(self.campaign.pk,)))
            self.assertEqual(response.context["changes_requested_count"], requests)
            self.assertEqual(response.context["deliverable_summary"]["approved"], approvals)
            response = self.client.get(reverse("client_reports"))
            campaign = next(c for c in response.context["campaigns"] if c.pk == self.campaign.pk)
            self.assertEqual(campaign.total_deliverables, 1)
            self.assertEqual(campaign.approved_deliverables, approvals)
            self.assertEqual(campaign.changes_requested_deliverables, requests)
            self.assertEqual(campaign.revision_count, 1)
            self.assertContains(response, "1 revision")

    def test_independent_deliverables_and_other_campaigns_do_not_distort_revision_counts(self):
        Deliverable.objects.create(campaign=self.campaign, uploaded_by=self.employee,
                                    title="Separate rejected creative", approval_status="rejected")
        other = Campaign.objects.create(client=self.other_client, name="Private", description="Private")
        root = Deliverable.objects.create(campaign=other, uploaded_by=self.employee, title="Private root", approval_status="changes_requested")
        Deliverable.objects.create(campaign=other, uploaded_by=self.employee, original=root, version=2, title="Private revision", approval_status="approved")
        response = self.report(self.owner, "client_campaign_report")
        self.assertEqual(response.context["deliverable_summary"], {"total": 2, "pending": 1, "approved": 0, "rejected": 1})
        self.assertEqual((response.context["total_versions"], response.context["revision_count"]), (3, 1))
        self.assertNotContains(response, "Private root")
        self.assertNotContains(response, "Private revision")

    def test_all_revision_files_retain_existing_download_permissions(self):
        for deliverable, content in ((self.deliverable, b"original"), (self.revision, b"revision")):
            path = self.media_root / deliverable.uploaded_file.name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            for user in (self.owner, self.employee_user, self.staff):
                self.client.force_login(user)
                response = self.client.get(deliverable.uploaded_file.url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b"".join(response.streaming_content), content)
                response.close()
            for user in (self.other_client, self.other_employee_user):
                self.client.force_login(user)
                self.assertEqual(self.client.get(deliverable.uploaded_file.url).status_code, 404)
            self.client.logout()
            self.assertEqual(self.client.get(deliverable.uploaded_file.url).status_code, 302)


class ControlledEnhancementEndToEndTests(AuditFixtures):
    password = "Agency-Workflow-2026!"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        for user in (cls.owner, cls.staff, cls.employee_user):
            user.set_password(cls.password)
            user.save(update_fields=("password",))
        ClientProfile.objects.create(user=cls.owner, company_name="GlowCare Cosmetics")

    def post(self, browser, url, data):
        return browser.post(url, {**data, "csrfmiddlewaretoken": browser.cookies["csrftoken"].value})

    def login(self, user, page, dashboard):
        browser = Client(enforce_csrf_checks=True)
        browser.get(reverse(page))
        self.assertRedirects(self.post(browser, reverse(page), {"username": user.username, "password": self.password}), reverse(dashboard))
        return browser

    def test_complete_client_admin_employee_revision_workflow_with_csrf(self):
        client = self.login(self.owner, "login", "client_dashboard")
        self.assertContains(client.get(reverse("client_profile")), "GlowCare Cosmetics")
        request = {"name": "Agency Launch", "description": "Launch requirements", "campaign_type": "Social",
                   "product_service_name": "Vitamin C Serum", "budget": "5000.00", "target_audience": "Shoppers",
                   "platforms": "Instagram, Facebook", "campaign_goal": "Product awareness",
                   "start_date": "2026-10-01", "end_date": "2026-10-31"}
        self.assertRedirects(self.post(client, reverse("campaign_request"), request), reverse("client_campaign_list"))
        campaign = Campaign.objects.get(name="Agency Launch")
        self.assertEqual(campaign.status, Campaign.Status.PENDING)
        edit_url = reverse("client_campaign_edit", args=(campaign.pk,))
        self.assertEqual(client.get(edit_url).status_code, 200)
        self.assertRedirects(self.post(client, edit_url, {**request, "description": "Corrected requirements"}),
                             reverse("client_campaign_detail", args=(campaign.pk,)))

        admin = self.login(self.staff, "administrator_login", "administrator_dashboard")
        admin_detail = reverse("administrator_campaign_detail", args=(campaign.pk,))
        self.assertContains(admin.get(admin_detail), "Corrected requirements")
        self.assertRedirects(self.post(admin, reverse("administrator_campaign_decision", args=(campaign.pk, "approve")), {}), admin_detail)
        self.assertRedirects(self.post(admin, admin_detail, {"assignment-assigned_employee": self.employee.pk, "update_assignment": "1"}), admin_detail)
        task_data = {"title": "Prepare creative", "description": "First brief", "due_date": "2026-10-10", "assigned_employee": self.employee.pk}
        self.assertRedirects(self.post(admin, reverse("administrator_task_create", args=(campaign.pk,)), task_data), admin_detail)
        task = campaign.tasks.get()
        self.assertRedirects(self.post(admin, reverse("administrator_task_edit", args=(campaign.pk, task.pk)),
                                       {**task_data, "description": "Corrected task brief"}), admin_detail)
        self.assertEqual(client.get(edit_url).status_code, 403)
        self.assertEqual(self.post(client, edit_url, request).status_code, 403)

        employee = self.login(self.employee_user, "employee_login", "employee_dashboard")
        employee_detail = reverse("employee_campaign_detail", args=(campaign.pk,))
        response = employee.get(employee_detail)
        for value in ("GlowCare Cosmetics", "Vitamin C Serum", "Corrected requirements"):
            self.assertContains(response, value)
        self.assertContains(employee.get(reverse("employee_task_detail", args=(task.pk,))), "Corrected task brief")
        self.assertRedirects(self.post(employee, reverse("employee_task_status_update", args=(task.pk,)), {"status": "completed"}),
                             reverse("employee_task_detail", args=(task.pk,)))
        self.assertRedirects(self.post(employee, employee_detail, {"status": "in_progress", "progress_percentage": 60}), employee_detail)
        self.assertRedirects(self.post(employee, reverse("employee_deliverable_upload", args=(campaign.pk,)), {
            "title": "Instagram Launch Creative", "description": "First version",
            "uploaded_file": SimpleUploadedFile("launch.pdf", b"version one"),
        }), employee_detail)
        original = campaign.deliverables.get()
        self.assertEqual(original.approval_status, "pending")

        self.assertContains(client.get(reverse("client_campaign_tracking")), "60%")
        self.assertContains(client.get(reverse("client_deliverables")), original.title)
        discussion = reverse("deliverable_discussion", args=(campaign.pk, original.pk))
        self.assertRedirects(self.post(client, reverse("client_deliverable_decision", args=(campaign.pk, original.pk, "request_changes")), {
            "body": "Please make the product image larger and change the headline.",
        }), discussion)
        self.assertContains(employee.get(discussion), "Please make the product image larger")
        self.assertContains(employee.get(employee_detail), "Please make the product image larger")
        self.assertRedirects(self.post(employee, discussion, {"body": "Sure, I will update it."}), discussion)
        self.post(employee, reverse("employee_deliverable_revision", args=(campaign.pk, original.pk)), {
            "title": original.title, "description": "Larger image and updated headline",
            "uploaded_file": SimpleUploadedFile("launch.pdf", b"version two"),
        })
        revision = campaign.deliverables.get(version=2)
        current_discussion = reverse("deliverable_discussion", args=(campaign.pk, revision.pk))
        self.assertContains(client.get(current_discussion), "Current version: 2")
        self.assertRedirects(self.post(client, reverse("client_deliverable_decision", args=(campaign.pk, revision.pk, "approve")), {"return_to": "discussion"}), current_discussion)
        revision.refresh_from_db()
        original.refresh_from_db()
        self.assertEqual(revision.approval_status, "approved")
        self.assertEqual(original.approval_status, "changes_requested")
        self.assertNotEqual(original.uploaded_file.name, revision.uploaded_file.name)
        self.assertEqual(campaign.deliverables.count(), 2)

        report = client.get(reverse("client_campaign_report", args=(campaign.pk,)))
        for value in ("GlowCare Cosmetics", "Vitamin C Serum", "60%", "Version 1", "Version 2", "Changes Requested", "Approved", "Print / Save as PDF"):
            self.assertContains(report, value)
        self.assertEqual(report.context["task_summary"]["completed"], 1)
        self.assertEqual(report.context["deliverable_summary"], {"total": 1, "pending": 0, "approved": 1, "rejected": 0})
        self.assertEqual(report.context["revision_count"], 1)
        self.assertContains(report, 'onclick="window.print()"')
        for deliverable, content in ((original, b"version one"), (revision, b"version two")):
            file_response = client.get(deliverable.uploaded_file.url)
            self.assertEqual(b"".join(file_response.streaming_content), content)
            file_response.close()
