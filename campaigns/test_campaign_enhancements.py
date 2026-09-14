from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from .forms import CampaignRequestForm, DeliverableUploadForm
from .models import Campaign, Deliverable
from .test_audit import AuditFixtures
from .test_final_verification import PageMarkup


class CampaignRequirementsTests(AuditFixtures):
    platforms = "Instagram, Facebook, YouTube"
    campaign_goal = "Build awareness for the new product.\nGenerate product enquiries and sales."

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.campaign.platforms = cls.platforms
        cls.campaign.campaign_goal = cls.campaign_goal
        cls.campaign.save(update_fields=("platforms", "campaign_goal"))

    def request_data(self, **overrides):
        return {
            "name": "Product Launch", "description": "Promote the new product.",
            "campaign_type": "Social Media", "target_audience": "Local shoppers",
            "budget": "5000.00", "start_date": "2026-10-01", "end_date": "2026-10-31",
            "platforms": self.platforms, "campaign_goal": self.campaign_goal, **overrides,
        }

    def detail_audiences(self):
        return ((self.owner, "client_campaign_detail"), (self.staff, "administrator_campaign_detail"),
                (self.employee_user, "employee_campaign_detail"), (self.owner, "client_campaign_report"),
                (self.staff, "administrator_campaign_report"))

    def test_request_form_preserves_existing_fields_and_styles_new_fields(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("campaign_request"))
        self.assertIsInstance(response.context["form"], CampaignRequestForm)
        self.assertEqual(set(response.context["form"].fields), {
            "name", "description", "campaign_type", "target_audience", "budget", "start_date", "end_date",
            "platforms", "campaign_goal",
        })
        for name in ("platforms", "campaign_goal"):
            field = response.context["form"].fields[name]
            self.assertFalse(field.required)
            self.assertEqual(field.widget.attrs["class"], "form-control")
            self.assertFalse(field.help_text)
            self.assertNotIn("placeholder", field.widget.attrs)
            self.assertIn(response.context["form"][name].value(), (None, ""))
            self.assertNotContains(response, f'id="id_{name}_helptext"')
        for value in ("Platforms", "Campaign Goal", '<input type="text" name="platforms"',
                      '<textarea name="campaign_goal"'):
            self.assertContains(response, value)
        self.assertContains(response, '<input type="text" name="platforms" maxlength="255" class="form-control" id="id_platforms">', html=True)
        self.assertContains(response, '<textarea name="campaign_goal" cols="40" rows="4" class="form-control" id="id_campaign_goal"></textarea>', html=True)
        self.assertNotContains(response, self.platforms)
        self.assertNotContains(response, "Build awareness for the new product")

    def test_campaign_request_saves_platforms_goal_and_all_existing_fields(self):
        self.client.force_login(self.owner)
        before = Campaign.objects.get(pk=self.campaign.pk).__dict__.copy()
        response = self.client.post(reverse("campaign_request"), self.request_data(
            client=self.other_client.pk, assigned_employee=self.employee.pk,
            status="approved", progress_percentage=100,
        ))
        self.assertRedirects(response, reverse("client_campaign_list"))
        campaign = Campaign.objects.get(name="Product Launch")
        for name, value in self.request_data().items():
            self.assertEqual(str(getattr(campaign, name)), value)
        self.assertEqual(campaign.client, self.owner)
        self.assertIsNone(campaign.assigned_employee)
        self.assertEqual(campaign.status, Campaign.Status.PENDING)
        self.assertEqual(campaign.progress_percentage, 0)
        unchanged = Campaign.objects.get(pk=self.campaign.pk).__dict__.copy()
        before.pop("_state")
        unchanged.pop("_state")
        self.assertEqual(unchanged, before)

    def test_campaign_requests_without_new_fields_remain_valid(self):
        self.client.force_login(self.owner)
        data = self.request_data()
        data.pop("platforms")
        data.pop("campaign_goal")
        self.assertRedirects(self.client.post(reverse("campaign_request"), data), reverse("client_campaign_list"))
        campaign = Campaign.objects.get(name=data["name"])
        self.assertEqual(campaign.platforms, "")
        self.assertEqual(campaign.campaign_goal, "")

    def test_new_fields_do_not_bypass_budget_or_date_validation(self):
        self.client.force_login(self.owner)
        for overrides, error in (
            ({"budget": "-1"}, "Budget cannot be negative."),
            ({"end_date": "2026-09-30"}, "End date cannot be before the start date."),
        ):
            with self.subTest(overrides=overrides):
                response = self.client.post(reverse("campaign_request"), self.request_data(**overrides))
                self.assertContains(response, error)
                self.assertContains(response, self.platforms)
                self.assertEqual(response.context["form"]["campaign_goal"].value(), self.campaign_goal)
                self.assertFalse(Campaign.objects.filter(name="Product Launch").exists())

    def test_platforms_length_validation_and_long_goal(self):
        form = CampaignRequestForm(self.request_data(platforms="x" * 256))
        self.assertFalse(form.is_valid())
        self.assertIn("platforms", form.errors)
        form = CampaignRequestForm(self.request_data(platforms="x" * 255, campaign_goal="Goal details. " * 100))
        self.assertTrue(form.is_valid(), form.errors)

    def assert_requirements_displayed(self, user, name):
        self.client.force_login(user)
        response = self.client.get(reverse(name, args=(self.campaign.pk,)))
        for value in ("Platforms", "Campaign Goal", self.platforms, "Build awareness for the new product.",
                      "Generate product enquiries and sales."):
            self.assertContains(response, value)
        self.assertContains(response, "Build awareness for the new product.<br>Generate product enquiries and sales.")

    def test_client_campaign_detail_displays_requirements(self):
        self.assert_requirements_displayed(self.owner, "client_campaign_detail")

    def test_admin_campaign_detail_displays_requirements(self):
        self.assert_requirements_displayed(self.staff, "administrator_campaign_detail")

    def test_employee_campaign_detail_displays_requirements(self):
        self.assert_requirements_displayed(self.employee_user, "employee_campaign_detail")

    def test_existing_client_and_admin_reports_display_requirements(self):
        for user, name in ((self.owner, "client_campaign_report"), (self.staff, "administrator_campaign_report")):
            with self.subTest(report=name):
                self.assert_requirements_displayed(user, name)

    def test_legacy_campaigns_show_not_specified_for_both_fields(self):
        legacy = Campaign.objects.create(
            client=self.owner, assigned_employee=self.employee, name="Legacy campaign", description="Existing data",
        )
        self.assertEqual((legacy.platforms, legacy.campaign_goal), ("", ""))
        for user, name in self.detail_audiences():
            with self.subTest(page=name):
                self.client.force_login(user)
                response = self.client.get(reverse(name, args=(legacy.pk,)))
                if name.endswith("report"):
                    for label in ("Platforms", "Campaign Goal"):
                        self.assertContains(response, f'<dt class="col-sm-4">{label}</dt><dd class="col-sm-8 text-break">Not specified</dd>', html=True)
                else:
                    for label in ("Platforms", "Campaign Goal"):
                        self.assertContains(response, f'<h2 class="h6 text-uppercase text-secondary">{label}</h2><p class="mb-4 text-break">Not specified</p>', html=True)

    def test_requirements_are_escaped_in_every_detail_and_report(self):
        Campaign.objects.filter(pk=self.campaign.pk).update(
            platforms="<script>platforms()</script>", campaign_goal="<script>goal()</script>\nNext objective",
        )
        for user, name in self.detail_audiences():
            with self.subTest(page=name):
                self.client.force_login(user)
                response = self.client.get(reverse(name, args=(self.campaign.pk,)))
                for field in ("platforms", "goal"):
                    self.assertContains(response, f"&lt;script&gt;{field}()&lt;/script&gt;")
                    self.assertNotContains(response, f"<script>{field}()</script>")

    def test_requirements_are_not_added_to_compact_lists(self):
        for user, name in (
            (self.owner, "client_campaign_list"), (self.owner, "client_campaign_tracking"),
            (self.owner, "client_reports"), (self.employee_user, "employee_dashboard"),
            (self.employee_user, "employee_deliverable_campaigns"), (self.staff, "administrator_dashboard"),
        ):
            with self.subTest(page=name):
                self.client.force_login(user)
                response = self.client.get(reverse(name))
                self.assertNotContains(response, self.platforms)
                self.assertNotContains(response, "Build awareness for the new product.")


class EmployeeDeliverableSelectionTests(AuditFixtures):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.campaign.end_date = "2027-01-07"
        cls.campaign.progress_percentage = 25
        cls.campaign.save(update_fields=("end_date", "progress_percentage"))
        cls.in_progress = Campaign.objects.create(
            client=cls.owner, assigned_employee=cls.employee, name="Ongoing campaign", description="Work",
            status=Campaign.Status.IN_PROGRESS,
        )
        cls.completed = Campaign.objects.create(
            client=cls.owner, assigned_employee=cls.employee, name="Completed campaign", description="Work",
            status=Campaign.Status.COMPLETED, progress_percentage=100,
        )
        cls.blocked = [Campaign.objects.create(
            client=cls.owner, assigned_employee=cls.employee, name=f"Blocked {status}", description="Work", status=status,
        ) for status in (Campaign.Status.PENDING, Campaign.Status.REJECTED)]
        cls.unassigned = Campaign.objects.create(
            client=cls.owner, name="Unassigned campaign", description="Work", status=Campaign.Status.APPROVED,
        )
        cls.other_campaign = Campaign.objects.create(
            client=cls.other_client, assigned_employee=cls.other_employee, name="Other employee campaign",
            description="Private work", status=Campaign.Status.APPROVED,
        )

    def setUp(self):
        super().setUp()
        self.client.force_login(self.employee_user)

    def upload_url(self, campaign=None):
        return reverse("employee_deliverable_upload", args=((campaign or self.campaign).pk,))

    def upload_data(self, **overrides):
        return {"title": "New employee creative", "description": "Ready for client review",
                "uploaded_file": SimpleUploadedFile("creative.pdf", b"uploaded creative", content_type="application/pdf"),
                **overrides}

    def test_dashboard_choose_campaign_opens_dedicated_selector(self):
        response = self.client.get(reverse("employee_dashboard"))
        url = reverse("employee_deliverable_campaigns")
        self.assertContains(response, f'<a class="btn btn-outline-primary" href="{url}">Choose Campaign</a>', html=True)
        self.assertNotContains(response, 'href="#assigned-campaigns">Choose Campaign')
        selection = self.client.get(url)
        self.assertContains(selection, "Choose Campaign to Upload Deliverable")
        self.assertTemplateUsed(selection, "campaigns/employee_deliverable_campaigns.html")

    def test_selector_only_lists_assigned_eligible_campaigns_with_direct_upload_links(self):
        response = self.client.get(reverse("employee_deliverable_campaigns"), {
            "assigned_employee": self.other_employee.pk, "campaign_id": self.other_campaign.pk,
        })
        self.assertCountEqual(response.context["campaigns"], [self.campaign, self.in_progress, self.completed])
        for value in (self.campaign.name, self.owner.username, "Jan 7, 2027", "Approved", "In Progress", "Completed", "25%", "100%"):
            self.assertContains(response, value)
        for campaign in (self.campaign, self.in_progress, self.completed):
            self.assertContains(response, f'href="{self.upload_url(campaign)}"')
        for campaign in (*self.blocked, self.unassigned, self.other_campaign):
            self.assertNotContains(response, campaign.name)
            self.assertNotContains(response, self.upload_url(campaign))

    def test_selector_empty_state_when_no_campaigns_are_available(self):
        for campaign in (self.campaign, self.in_progress, self.completed):
            Campaign.objects.filter(pk=campaign.pk).update(assigned_employee=None)
        self.assertContains(self.client.get(reverse("employee_deliverable_campaigns")),
                            "No campaigns are currently available for deliverable upload.")

    def test_selector_is_get_only_and_does_not_modify_data(self):
        before = list(Campaign.objects.values())
        url = reverse("employee_deliverable_campaigns")
        self.assertEqual(self.client.get(url).status_code, 200)
        for method in ("post", "put", "patch", "delete"):
            self.assertEqual(getattr(self.client, method)(url, {"status": "completed"}).status_code, 405)
        self.assertEqual(list(Campaign.objects.values()), before)

    def test_selection_opens_existing_multipart_csrf_upload_form(self):
        page = self.client.get(reverse("employee_deliverable_campaigns"))
        self.assertIn(self.upload_url(), PageMarkup(page.content.decode()).links)
        response = self.client.get(self.upload_url())
        self.assertTemplateUsed(response, "campaigns/employee_deliverable_upload.html")
        self.assertIsInstance(response.context["form"], DeliverableUploadForm)
        self.assertEqual(response.context["campaign"], self.campaign)
        self.assertContains(response, 'enctype="multipart/form-data"')
        form = PageMarkup(response.content.decode()).forms[-1]
        self.assertEqual(form["method"], "post")
        self.assertTrue(form["csrf"])

    def test_upload_with_csrf_saves_correct_relationships_and_appears_for_owning_client(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.employee_user)
        browser.get(self.upload_url())
        response = browser.post(self.upload_url(), self.upload_data(
            csrfmiddlewaretoken=browser.cookies["csrftoken"].value,
            campaign=self.other_campaign.pk, uploaded_by=self.other_employee.pk, approval_status="approved",
        ), follow=True)
        self.assertRedirects(response, reverse("employee_campaign_detail", args=(self.campaign.pk,)))
        self.assertContains(response, 'Deliverable &quot;New employee creative&quot; uploaded successfully.')
        deliverable = Deliverable.objects.get(title="New employee creative")
        self.assertEqual(deliverable.campaign, self.campaign)
        self.assertEqual(deliverable.uploaded_by, self.employee)
        self.assertEqual(deliverable.approval_status, Deliverable.ApprovalStatus.PENDING)
        self.assertTrue(deliverable.uploaded_file.storage.exists(deliverable.uploaded_file.name))
        self.client.force_login(self.owner)
        review = self.client.get(reverse("client_deliverables"), {"status": "pending"})
        self.assertContains(review, deliverable.title)
        self.assertContains(review, deliverable.uploaded_file.url)
        self.client.force_login(self.other_client)
        self.assertNotContains(self.client.get(reverse("client_deliverables")), deliverable.title)
        self.assertEqual(self.client.get(deliverable.uploaded_file.url).status_code, 404)

    def test_uploads_still_support_all_existing_allowed_statuses(self):
        for campaign in (self.campaign, self.in_progress, self.completed):
            with self.subTest(status=campaign.status):
                self.assertRedirects(self.client.post(self.upload_url(campaign), self.upload_data(title=campaign.name)),
                                     reverse("employee_campaign_detail", args=(campaign.pk,)))
                self.assertEqual(Deliverable.objects.get(title=campaign.name).campaign, campaign)

    def test_changing_url_ids_cannot_upload_to_other_or_unassigned_campaigns(self):
        count = Deliverable.objects.count()
        for campaign in (self.other_campaign, self.unassigned):
            with self.subTest(campaign=campaign.name):
                self.assertEqual(self.client.get(self.upload_url(campaign)).status_code, 404)
                self.assertEqual(self.client.post(self.upload_url(campaign), self.upload_data()).status_code, 404)
        missing_url = reverse("employee_deliverable_upload", args=(999999,))
        self.assertEqual(self.client.post(missing_url, self.upload_data()).status_code, 404)
        self.assertEqual(Deliverable.objects.count(), count)
        self.assertFalse(any(self.media_root.rglob("*.pdf")))

    def test_pending_and_rejected_campaigns_reject_direct_uploads(self):
        count = Deliverable.objects.count()
        for campaign in self.blocked:
            response = self.client.post(self.upload_url(campaign), self.upload_data())
            self.assertContains(response, "This campaign must be approved before work can be updated.")
        self.assertEqual(Deliverable.objects.count(), count)
        self.assertFalse(any(self.media_root.rglob("*.pdf")))

    def test_reassignment_revokes_a_previously_opened_upload_form(self):
        self.assertEqual(self.client.get(self.upload_url()).status_code, 200)
        Campaign.objects.filter(pk=self.campaign.pk).update(assigned_employee=self.other_employee)
        self.assertNotContains(self.client.get(reverse("employee_deliverable_campaigns")), self.campaign.name)
        self.assertEqual(self.client.post(self.upload_url(), self.upload_data()).status_code, 404)
        self.assertFalse(Deliverable.objects.filter(title="New employee creative").exists())

    def test_nonemployees_cannot_access_selection_or_upload_pages(self):
        for user in (self.owner, self.staff, self.superuser):
            self.client.force_login(user)
            for url in (reverse("employee_deliverable_campaigns"), self.upload_url()):
                with self.subTest(user=user.username, url=url):
                    self.assertRedirects(self.client.get(url), f'{reverse("employee_login")}?next={url}')
                    self.assertRedirects(self.client.post(url, self.upload_data()), f'{reverse("employee_login")}?next={url}')

    def test_anonymous_users_redirect_from_selection_and_upload(self):
        self.client.logout()
        for url in (reverse("employee_deliverable_campaigns"), self.upload_url()):
            self.assertRedirects(self.client.get(url), f'{reverse("employee_login")}?next={url}')
        self.assertRedirects(self.client.post(self.upload_url(), self.upload_data()),
                             f'{reverse("employee_login")}?next={self.upload_url()}')

    def test_uploads_require_post_and_valid_csrf(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.employee_user)
        browser.get(self.upload_url())
        for extra in ({}, {"csrfmiddlewaretoken": "invalid"}):
            self.assertEqual(browser.post(self.upload_url(), self.upload_data(**extra)).status_code, 403)
        self.assertEqual(self.client.get(self.upload_url(), {"title": "GET upload"}).status_code, 200)
        for method in ("put", "patch", "delete"):
            self.assertEqual(getattr(self.client, method)(self.upload_url()).status_code, 405)
        self.assertFalse(Deliverable.objects.filter(title__in=("New employee creative", "GET upload")).exists())

    def test_uploaded_work_uses_existing_approval_rejection_and_repeat_protection(self):
        for decision, expected in (("approve", "approved"), ("reject", "rejected")):
            self.client.force_login(self.employee_user)
            self.client.post(self.upload_url(), self.upload_data(title=f"Creative to {decision}"))
            deliverable = Deliverable.objects.get(title=f"Creative to {decision}")
            self.client.force_login(self.owner)
            action = reverse("client_deliverable_decision", args=(self.campaign.pk, deliverable.pk, decision))
            self.assertRedirects(self.client.post(action, {"return_to": "deliverables"}), reverse("client_deliverables"))
            deliverable.refresh_from_db()
            self.assertEqual(deliverable.approval_status, expected)
            opposite = "reject" if decision == "approve" else "approve"
            repeat = reverse("client_deliverable_decision", args=(self.campaign.pk, deliverable.pk, opposite))
            response = self.client.post(repeat, {"return_to": "deliverables"}, follow=True)
            self.assertContains(response, "This deliverable has already been reviewed.")
            deliverable.refresh_from_db()
            self.assertEqual(deliverable.approval_status, expected)
