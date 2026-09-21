from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from .models import Campaign, Deliverable, Task
from .test_audit import AuditFixtures
from .test_final_verification import PageMarkup


class ClientModuleUXTests(AuditFixtures):
    list_pages = (
        "client_campaign_list", "client_campaign_tracking", "client_deliverables", "client_reports",
    )

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.campaign.progress_percentage = 25
        cls.campaign.end_date = "2026-10-01"
        cls.campaign.save(update_fields=("progress_percentage", "end_date"))
        for number in range(2):
            Task.objects.create(
                campaign=cls.campaign, assigned_employee=cls.employee,
                title=f"Completed task {number}", due_date="2026-10-01", status=Task.Status.COMPLETED,
            )
        cls.approved = Deliverable.objects.create(
            campaign=cls.campaign, uploaded_by=cls.employee, title="Approved creative",
            uploaded_file="deliverables/approved.pdf", approval_status=Deliverable.ApprovalStatus.APPROVED,
        )
        cls.rejected = Deliverable.objects.create(
            campaign=cls.campaign, uploaded_by=cls.employee, title="Rejected creative",
            uploaded_file="deliverables/rejected.pdf", approval_status=Deliverable.ApprovalStatus.REJECTED,
        )
        cls.empty_campaign = Campaign.objects.create(
            client=cls.owner, name="Unassigned campaign", description="No work yet",
        )
        cls.private_campaign = Campaign.objects.create(
            client=cls.other_client, name="Other client's private campaign", description="Private",
            assigned_employee=cls.employee,
        )
        cls.private_deliverables = [
            Deliverable.objects.create(
                campaign=cls.private_campaign, uploaded_by=cls.employee,
                title=f"Private {status} creative", uploaded_file=f"deliverables/private-{status}.pdf",
                approval_status=status,
            ) for status in Deliverable.ApprovalStatus.values
        ]
        Task.objects.create(
            campaign=cls.private_campaign, title="Private completed task",
            due_date="2026-10-01", status=Task.Status.COMPLETED,
        )

    def setUp(self):
        super().setUp()
        self.client.force_login(self.owner)

    def decision_url(self, decision, deliverable=None, campaign=None):
        deliverable = deliverable or self.deliverable
        return reverse("client_deliverable_decision", args=(
            (campaign or deliverable.campaign).pk, deliverable.pk, decision,
        ))

    def test_six_dashboard_buttons_have_six_correct_distinct_destinations(self):
        response = self.client.get(reverse("client_dashboard"))
        main = response.content.decode().split("<main>", 1)[1].split("</main>", 1)[0]
        expected = (
            ("Request Campaign", "campaign_request"), ("View Campaigns", "client_campaign_list"),
            ("Track Campaigns", "client_campaign_tracking"), ("Review Deliverables", "client_deliverables"),
            ("View Reports", "client_reports"), ("Manage Profile", "client_profile"),
        )
        self.assertCountEqual(PageMarkup(main).links, [reverse(name) for _, name in expected])
        self.assertEqual(len(set(reverse(name) for _, name in expected)), 6)
        for label, name in expected:
            self.assertIn(f'href="{reverse(name)}">{label}</a>', main)

    def test_general_campaign_list_remains_a_simple_overview(self):
        response = self.client.get(reverse("client_campaign_list"))
        for value in ("My Campaigns", "Submitted", "Deadline", "Status", "25%", "Oct 1, 2026", "View Details"):
            self.assertContains(response, value)
        self.assertContains(response, date_format(timezone.localtime(self.campaign.created_at), "M j, Y"))
        self.assertContains(response, reverse("client_campaign_detail", args=(self.campaign.pk,)))
        for value in ("View Report", 'role="progressbar"', "Tasks completed", "Assigned employee",
                      self.decision_url("approve"), self.decision_url("reject")):
            self.assertNotContains(response, value)

    def test_tracking_shows_recorded_progress_and_separate_task_completion(self):
        response = self.client.get(reverse("client_campaign_tracking"))
        for value in ("Track Campaign Progress", "Assigned employee", "Maya", "Oct 1, 2026", "Approved", "2 / 3"):
            self.assertContains(response, value)
        self.assertContains(response, 'aria-label="Campaign progress" aria-valuenow="25"')
        self.assertContains(response, 'aria-label="Task completion" aria-valuenow="67"')
        self.assertContains(response, 'aria-label="Task completion" aria-valuenow="0"')
        self.assertNotContains(response, "View Report")
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.progress_percentage, 25)

    def test_campaign_lists_and_reports_ignore_forged_owner_parameters(self):
        for name in ("client_campaign_list", "client_campaign_tracking", "client_reports"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name), {
                    "client": self.other_client.pk, "campaign_id": self.private_campaign.pk,
                })
                self.assertCountEqual(response.context["campaigns"], [self.campaign, self.empty_campaign])
                self.assertNotContains(response, self.private_campaign.name)
                self.assertNotContains(response, reverse("client_campaign_report", args=(self.private_campaign.pk,)))

    def test_deliverable_table_shows_metadata_files_badges_and_pending_actions(self):
        response = self.client.get(reverse("client_deliverables"))
        self.assertTemplateUsed(response, "campaigns/client_deliverables.html")
        for value in ("Review Deliverables", self.deliverable.title, self.campaign.name, "Maya",
                      "Upload date", "Approval status", "Open File", "Pending Review"):
            self.assertContains(response, value)
        self.assertContains(response, date_format(timezone.localtime(self.deliverable.uploaded_at), "M j, Y, P"))
        self.assertContains(response, '<span class="badge text-bg-success">Approved</span>', html=True)
        self.assertContains(response, '<span class="badge text-bg-danger ">Rejected</span>', html=True)
        parsed = PageMarkup(response.content.decode())
        for decision in ("approve", "request_changes"):
            form = next(form for form in parsed.forms if form["action"] == self.decision_url(decision))
            self.assertEqual(form["method"], "post")
            self.assertTrue(form["csrf"])
            for reviewed in (self.approved, self.rejected):
                self.assertNotContains(response, self.decision_url(decision, reviewed))
        for deliverable in (self.deliverable, self.approved, self.rejected):
            self.assertIn(deliverable.uploaded_file.url, parsed.links)

    def test_deliverable_filters_only_return_owned_matching_records(self):
        for status in ("all", *Deliverable.ApprovalStatus.values):
            with self.subTest(status=status):
                response = self.client.get(reverse("client_deliverables"), {
                    "status": status, "client": self.other_client.pk, "campaign_id": self.private_campaign.pk,
                })
                expected = [item for item in (self.deliverable, self.approved, self.rejected)
                            if status == "all" or item.approval_status == status]
                self.assertCountEqual(response.context["deliverables"], expected)
                self.assertEqual(response.context["selected_status"], status)
                self.assertContains(response, 'aria-current="page"', count=1)
                for private in self.private_deliverables:
                    self.assertNotContains(response, private.title)
                    self.assertNotContains(response, private.uploaded_file.url)

    def test_missing_or_invalid_deliverable_filter_defaults_to_all(self):
        for data in ({}, {"status": ""}, {"status": "unknown"}, {"status": "https://example.com/"}):
            with self.subTest(data=data):
                response = self.client.get(reverse("client_deliverables"), data)
                self.assertEqual(response.context["selected_status"], "all")
                self.assertEqual(len(response.context["deliverables"]), 3)

    def test_all_four_pages_have_helpful_empty_states(self):
        self.client.force_login(User.objects.create_user("emptyclient"))
        for name, message in (
            ("client_campaign_list", "No campaigns found."),
            ("client_campaign_tracking", "No campaigns found."),
            ("client_deliverables", "No deliverables available for review."),
            ("client_reports", "No campaign reports available yet."),
        ):
            with self.subTest(page=name):
                self.assertContains(self.client.get(reverse(name)), message)

    def test_empty_filter_offers_return_to_all_deliverables(self):
        self.deliverable.approval_status = Deliverable.ApprovalStatus.APPROVED
        self.deliverable.save(update_fields=("approval_status",))
        response = self.client.get(reverse("client_deliverables"), {"status": "pending"})
        self.assertContains(response, "No deliverables available for review.")
        self.assertContains(response, "View all deliverables")

    def test_deliverables_without_files_have_a_fallback(self):
        self.campaign.deliverables.update(uploaded_file="")
        response = self.client.get(reverse("client_deliverables"))
        self.assertContains(response, "No file available", count=3)
        self.assertNotContains(response, ">Open File</a>")

    def submit_review_with_csrf(self, decision, expected_status):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        browser.get(reverse("client_deliverables"), {"status": "pending"})
        response = browser.post(self.decision_url(decision), {
            "csrfmiddlewaretoken": browser.cookies["csrftoken"].value,
            "return_to": "deliverables", "status": "pending",
        }, follow=True)
        self.assertRedirects(response, reverse("client_deliverables") + "?status=pending")
        self.assertContains(response, f'was {expected_status}.')
        self.assertNotContains(response, self.decision_url("approve"))
        self.deliverable.refresh_from_db()
        self.assertEqual(self.deliverable.approval_status, expected_status)
        self.assertContains(browser.get(reverse("client_deliverables"), {"status": expected_status}), self.deliverable.title)

    def test_pending_deliverable_can_be_approved_with_csrf(self):
        self.submit_review_with_csrf("approve", Deliverable.ApprovalStatus.APPROVED)

    def test_pending_deliverable_can_be_rejected_with_csrf(self):
        self.submit_review_with_csrf("reject", Deliverable.ApprovalStatus.REJECTED)

    def test_review_requires_csrf_and_post(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        browser.get(reverse("client_deliverables"))
        for decision in ("approve", "reject"):
            url = self.decision_url(decision)
            for data in ({}, {"csrfmiddlewaretoken": "invalid"}):
                self.assertEqual(browser.post(url, data).status_code, 403)
            for method in ("get", "head", "put", "patch", "delete"):
                self.assertEqual(getattr(self.client, method)(url).status_code, 405)
        self.deliverable.refresh_from_db()
        self.assertEqual(self.deliverable.approval_status, Deliverable.ApprovalStatus.PENDING)

    def test_reviewed_deliverables_cannot_be_reviewed_again(self):
        for deliverable in (self.approved, self.rejected):
            original_status = deliverable.approval_status
            for decision in ("approve", "reject"):
                with self.subTest(status=original_status, decision=decision):
                    response = self.client.post(self.decision_url(decision, deliverable), {
                        "return_to": "deliverables", "status": original_status,
                    }, follow=True)
                    self.assertContains(response, "This deliverable has already been reviewed.")
                    deliverable.refresh_from_db()
                    self.assertEqual(deliverable.approval_status, original_status)

    def test_unknown_decision_does_not_change_deliverable(self):
        response = self.client.post(self.decision_url("invalid"), {"return_to": "deliverables"}, follow=True)
        self.assertContains(response, "Invalid deliverable decision.")
        self.deliverable.refresh_from_db()
        self.assertEqual(self.deliverable.approval_status, Deliverable.ApprovalStatus.PENDING)

    def test_reviews_keep_only_fixed_local_destinations_and_valid_filters(self):
        for status in ("all", "pending", "approved", "rejected", "https://example.com/", "pending&client=99"):
            response = self.client.post(self.decision_url("approve", self.approved), {
                "return_to": "deliverables", "status": status, "next": "https://example.com/",
            })
            expected = reverse("client_deliverables")
            if status in Deliverable.ApprovalStatus.values:
                expected += f"?status={status}"
            self.assertRedirects(response, expected)
        for data in ({}, {"return_to": "https://example.com/", "next": "//example.com/"}):
            self.assertRedirects(
                self.client.post(self.decision_url("approve", self.approved), data),
                reverse("client_campaign_detail", args=(self.campaign.pk,)),
            )

    def test_manual_ids_cannot_expose_private_campaigns_reports_or_reviews(self):
        for name in ("client_campaign_detail", "client_campaign_report"):
            for campaign_id in (self.private_campaign.pk, 999999):
                self.assertEqual(self.client.get(reverse(name, args=(campaign_id,))).status_code, 404)
        private = self.private_deliverables[0]
        for decision in ("approve", "reject"):
            for deliverable, campaign in (
                (private, self.private_campaign), (private, self.campaign),
                (self.deliverable, self.empty_campaign),
            ):
                response = self.client.post(self.decision_url(decision, deliverable, campaign), {
                    "return_to": "deliverables", "client": self.owner.pk,
                })
                self.assertEqual(response.status_code, 404)
        private.refresh_from_db()
        self.assertEqual(private.approval_status, Deliverable.ApprovalStatus.PENDING)

    def test_file_links_retain_existing_ownership_protection(self):
        self.deliverable.uploaded_file.save("client-ux.pdf", SimpleUploadedFile("client-ux.pdf", b"review content"))
        url = self.deliverable.uploaded_file.url
        self.assertContains(self.client.get(reverse("client_deliverables")), f'href="{url}"')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"review content")
        response.close()
        self.client.force_login(self.other_client)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_employees_staff_and_superusers_cannot_use_client_pages_or_review(self):
        for user in (self.employee_user, self.staff, self.superuser):
            Campaign.objects.filter(pk=self.campaign.pk).update(client=user)
            self.client.force_login(user)
            for name, args in self.role_routes()["client"]:
                with self.subTest(user=user.username, page=name):
                    url = reverse(name, args=args)
                    self.assertRedirects(self.client.get(url), f'{reverse("login")}?next={url}')
            for decision in ("approve", "reject"):
                url = self.decision_url(decision)
                self.assertRedirects(self.client.post(url), f'{reverse("login")}?next={url}')
        self.deliverable.refresh_from_db()
        self.assertEqual(self.deliverable.approval_status, Deliverable.ApprovalStatus.PENDING)

    def test_anonymous_users_redirect_for_all_lists_and_reviews(self):
        self.client.logout()
        for name in self.list_pages:
            url = reverse(name)
            self.assertRedirects(self.client.get(url), f'{reverse("login")}?next={url}')
        for decision in ("approve", "reject"):
            url = self.decision_url(decision)
            self.assertRedirects(self.client.post(url), f'{reverse("login")}?next={url}')

    def test_list_pages_are_read_only(self):
        models = (Campaign, Task, Deliverable)
        before = [list(model.objects.values()) for model in models]
        for name in self.list_pages:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
            for method in ("post", "put", "patch", "delete"):
                response = getattr(self.client, method)(reverse(name), {"approval_status": "approved"})
                self.assertEqual(response.status_code, 405)
        self.assertEqual([list(model.objects.values()) for model in models], before)

    def test_reports_show_accurate_summaries_and_existing_report_links(self):
        response = self.client.get(reverse("client_reports"))
        self.assertTemplateUsed(response, "campaigns/client_reports.html")
        campaign = next(item for item in response.context["campaigns"] if item.pk == self.campaign.pk)
        self.assertEqual((campaign.completed_tasks, campaign.total_tasks), (2, 3))
        self.assertEqual((campaign.total_deliverables, campaign.approved_deliverables,
                          campaign.pending_deliverables, campaign.rejected_deliverables), (3, 1, 1, 1))
        for value in ("25%", "Maya", "2 / 3 completed", "1 approved, 1 pending review, 1 rejected", "View Report"):
            self.assertContains(response, value)
        for owned in (self.campaign, self.empty_campaign):
            report_url = reverse("client_campaign_report", args=(owned.pk,))
            self.assertContains(response, f'href="{report_url}"')
            report = self.client.get(report_url)
            self.assertTemplateUsed(report, "campaigns/campaign_report.html")
            self.assertContains(report, "Print / Save as PDF")
        self.assertNotContains(response, self.decision_url("approve"))

    def test_reports_handle_unassigned_campaigns_without_work(self):
        response = self.client.get(reverse("client_reports"))
        for value in ("Not assigned", "0 / 0 completed", "No deliverables uploaded yet."):
            self.assertContains(response, value)

    def test_report_selection_refreshes_from_the_same_current_records(self):
        self.client.get(reverse("client_reports"))
        self.campaign.tasks.update(status=Task.Status.COMPLETED)
        self.client.post(self.decision_url("approve"), {"return_to": "deliverables"})
        Campaign.objects.filter(pk=self.campaign.pk).update(progress_percentage=70)
        response = self.client.get(reverse("client_reports"))
        self.assertContains(response, "70%")
        self.assertContains(response, "3 / 3 completed")
        self.assertContains(response, "2 approved, 0 pending review, 1 rejected")
        report = self.client.get(reverse("client_campaign_report", args=(self.campaign.pk,)))
        self.assertEqual(report.context["task_summary"]["completed"], 3)
        self.assertEqual(report.context["deliverable_summary"]["approved"], 2)
        self.assertContains(report, "70%")

    def test_report_selection_includes_every_owned_campaign_status(self):
        for status in Campaign.Status:
            Campaign.objects.filter(pk=self.campaign.pk).update(status=status)
            response = self.client.get(reverse("client_reports"))
            self.assertContains(response, status.label)
            self.assertContains(response, reverse("client_campaign_report", args=(self.campaign.pk,)))

    def test_client_navbar_stays_simple(self):
        for name in self.list_pages:
            response = self.client.get(reverse(name))
            navigation = response.content.decode().split("<nav", 1)[1].split("</nav>", 1)[0]
            for destination in ("home", "client_dashboard", "client_campaign_list", "client_campaign_tracking", "client_profile"):
                self.assertIn(reverse(destination), PageMarkup(navigation).links)
            for destination in ("client_deliverables", "client_reports"):
                self.assertNotIn(reverse(destination), PageMarkup(navigation).links)

    def test_new_pages_escape_campaign_and_deliverable_names(self):
        Campaign.objects.filter(pk=self.campaign.pk).update(name="<script>campaign()</script>")
        self.campaign.deliverables.update(title="<script>deliverable()</script>")
        for name in ("client_deliverables", "client_reports"):
            response = self.client.get(reverse(name))
            self.assertContains(response, "&lt;script&gt;campaign()&lt;/script&gt;")
            self.assertNotContains(response, "<script>campaign()</script>")
            self.assertNotContains(response, "<script>deliverable()</script>")
