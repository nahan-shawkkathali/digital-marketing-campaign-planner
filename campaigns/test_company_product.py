from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from .forms import CampaignRequestForm, ClientProfileForm
from .models import Campaign, ClientProfile
from .test_audit import AuditFixtures


class CompanyProductTests(AuditFixtures):
    company_name = "GlowCare Cosmetics"
    product_service_name = "GlowCare Vitamin C Serum"

    def profile_data(self, **overrides):
        return {
            "first_name": "Nahan", "last_name": "Client", "email": "CLIENT@example.com",
            "company_name": self.company_name, **overrides,
        }

    def request_data(self, **overrides):
        return {
            "name": "New Product Launch Campaign", "description": "Promote our new product.",
            "campaign_type": "Social Media", "product_service_name": self.product_service_name,
            "target_audience": "Local shoppers", "budget": "5000.00",
            "start_date": timezone.localdate().isoformat(),
            "end_date": (timezone.localdate() + timedelta(days=30)).isoformat(),
            "platforms": "Instagram, Facebook, YouTube",
            "campaign_goal": "Increase product awareness and generate sales.", **overrides,
        }

    def add_business_details(self):
        ClientProfile.objects.create(user=self.owner, company_name=self.company_name)
        Campaign.objects.filter(pk=self.campaign.pk).update(product_service_name=self.product_service_name)

    def audiences(self):
        return (
            (self.owner, "client_campaign_detail"), (self.staff, "administrator_campaign_detail"),
            (self.employee_user, "employee_campaign_detail"), (self.owner, "client_campaign_report"),
            (self.staff, "administrator_campaign_report"),
        )

    def assert_business_details(self, user, page):
        self.client.force_login(user)
        response = self.client.get(reverse(page, args=(self.campaign.pk,)))
        for value in ("Company / Business Name", "Product / Service Name",
                      self.company_name, self.product_service_name):
            self.assertContains(response, value)
        return response

    def test_existing_client_can_open_profile_without_creating_a_profile_record(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("client_profile"))
        self.assertContains(response, "Company / Business Name")
        self.assertEqual(response.context["form"]["company_name"].value(), "")
        self.assertFalse(ClientProfile.objects.exists())

    def test_client_can_save_company_and_existing_profile_fields(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("client_profile"), self.profile_data())
        self.assertRedirects(response, reverse("client_profile"))
        self.assertEqual(ClientProfile.objects.get(user=self.owner).company_name, self.company_name)
        self.owner.refresh_from_db()
        self.assertEqual((self.owner.first_name, self.owner.last_name, self.owner.email),
                         ("Nahan", "Client", "client@example.com"))
        self.assertEqual(self.owner.username, "auditclient")
        self.assertContains(self.client.get(reverse("client_profile")), f'value="{self.company_name}"')

    def test_client_can_view_and_edit_existing_company_without_duplicate_profiles(self):
        self.add_business_details()
        profile = ClientProfile.objects.get(user=self.owner)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("client_profile"))
        self.assertEqual(response.context["form"]["company_name"].value(), self.company_name)
        self.assertRedirects(self.client.post(reverse("client_profile"), self.profile_data(
            company_name="GlowCare Beauty",
        )), reverse("client_profile"))
        profile.refresh_from_db()
        self.assertEqual(profile.company_name, "GlowCare Beauty")
        self.assertEqual(ClientProfile.objects.filter(user=self.owner).count(), 1)

    def test_client_can_clear_optional_company_name(self):
        self.add_business_details()
        self.client.force_login(self.owner)
        self.assertRedirects(self.client.post(reverse("client_profile"), self.profile_data(
            company_name="",
        )), reverse("client_profile"))
        self.assertEqual(ClientProfile.objects.get(user=self.owner).company_name, "")

    def test_forged_profile_owner_and_role_fields_cannot_modify_another_client(self):
        self.add_business_details()
        profile = ClientProfile.objects.get(user=self.owner)
        self.client.force_login(self.other_client)
        response = self.client.post(reverse("client_profile") + f"?user_id={self.owner.pk}", self.profile_data(
            email="other@example.com", company_name="Other Company", user=self.owner.pk,
            user_id=self.owner.pk, client=self.owner.pk, client_id=self.owner.pk,
            id=profile.pk, profile_id=profile.pk, is_staff=True, is_superuser=True,
        ))
        self.assertRedirects(response, reverse("client_profile"))
        profile.refresh_from_db()
        self.owner.refresh_from_db()
        self.other_client.refresh_from_db()
        self.assertEqual(profile.company_name, self.company_name)
        self.assertEqual(self.owner.email, "client@example.com")
        self.assertEqual(ClientProfile.objects.get(user=self.other_client).company_name, "Other Company")
        self.assertFalse(self.other_client.is_staff)
        self.assertFalse(self.other_client.is_superuser)

    def test_invalid_profile_does_not_save_company_or_contact_changes(self):
        self.add_business_details()
        self.other_client.email = "taken@example.com"
        self.other_client.save(update_fields=("email",))
        self.client.force_login(self.owner)
        for changes, field in (({"email": "TAKEN@example.com"}, "email"),
                               ({"company_name": "x" * 256}, "company_name")):
            with self.subTest(field=field):
                response = self.client.post(reverse("client_profile"), self.profile_data(**changes))
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
                self.assertEqual(ClientProfile.objects.get(user=self.owner).company_name, self.company_name)
                self.owner.refresh_from_db()
                self.assertEqual((self.owner.first_name, self.owner.email), ("", "client@example.com"))

    def test_profile_save_is_atomic_if_company_save_fails(self):
        form = ClientProfileForm(self.profile_data(), instance=self.owner)
        self.assertTrue(form.is_valid(), form.errors)
        with patch.object(ClientProfile.objects, "update_or_create", side_effect=RuntimeError("Save failed")):
            with self.assertRaises(RuntimeError):
                form.save()
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.first_name, "")
        self.assertFalse(ClientProfile.objects.exists())

    def test_profile_save_commit_false_does_not_write_either_record(self):
        form = ClientProfileForm(self.profile_data(), instance=self.owner)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save(commit=False).first_name, "Nahan")
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.first_name, "")
        self.assertFalse(ClientProfile.objects.exists())

    def test_new_form_fields_are_optional_styled_and_have_no_hints(self):
        self.client.force_login(self.owner)
        for page, name, label in (
            ("client_profile", "company_name", "Company / Business Name"),
            ("campaign_request", "product_service_name", "Product / Service Name"),
        ):
            with self.subTest(field=name):
                response = self.client.get(reverse(page))
                field = response.context["form"].fields[name]
                self.assertEqual(field.label, label)
                self.assertFalse(field.required)
                self.assertFalse(field.help_text)
                self.assertNotIn("placeholder", field.widget.attrs)
                self.assertEqual(field.widget.attrs["class"], "form-control")
                self.assertContains(response, label)
                self.assertNotContains(response, f'id="id_{name}_helptext"')

    def test_campaign_request_saves_product_and_preserves_existing_fields_and_ownership(self):
        self.add_business_details()
        self.client.force_login(self.owner)
        response = self.client.post(reverse("campaign_request"), self.request_data(
            client=self.other_client.pk, assigned_employee=self.employee.pk,
            status="approved", progress_percentage=100, company_name="Forged Company",
        ))
        self.assertRedirects(response, reverse("client_campaign_list"))
        campaign = Campaign.objects.get(name=self.request_data()["name"])
        for name, value in self.request_data().items():
            self.assertEqual(str(getattr(campaign, name)), value)
        self.assertEqual(campaign.client, self.owner)
        self.assertIsNone(campaign.assigned_employee)
        self.assertEqual(campaign.status, Campaign.Status.PENDING)
        self.assertEqual(campaign.progress_percentage, 0)
        self.assertEqual(ClientProfile.objects.get(user=self.owner).company_name, self.company_name)

    def test_campaign_request_without_product_or_client_profile_still_works(self):
        data = self.request_data()
        data.pop("product_service_name")
        self.client.force_login(self.owner)
        self.assertRedirects(self.client.post(reverse("campaign_request"), data), reverse("client_campaign_list"))
        campaign = Campaign.objects.get(name=data["name"])
        self.assertEqual(campaign.product_service_name, "")
        self.assertFalse(ClientProfile.objects.exists())
        self.assertEqual(self.client.get(reverse("client_campaign_detail", args=(campaign.pk,))).status_code, 200)

    def test_one_company_can_request_campaigns_for_different_products(self):
        self.add_business_details()
        self.client.force_login(self.owner)
        for title, product in (("Serum launch", self.product_service_name), ("Sunscreen launch", "Sunscreen SPF 50")):
            self.assertRedirects(self.client.post(reverse("campaign_request"), self.request_data(
                name=title, product_service_name=product,
            )), reverse("client_campaign_list"))
            campaign = Campaign.objects.get(name=title)
            response = self.client.get(reverse("client_campaign_detail", args=(campaign.pk,)))
            self.assertContains(response, self.company_name)
            self.assertContains(response, product)
        self.assertEqual(ClientProfile.objects.count(), 1)

    def test_product_length_and_existing_budget_date_validation(self):
        self.client.force_login(self.owner)
        for changes, field in (({"product_service_name": "x" * 256}, "product_service_name"),
                               ({"budget": "-1"}, "budget"), ({"end_date": (timezone.localdate() - timedelta(days=1)).isoformat()}, "end_date")):
            with self.subTest(field=field):
                response = self.client.post(reverse("campaign_request"), self.request_data(**changes))
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
                self.assertFalse(Campaign.objects.filter(name=self.request_data()["name"]).exists())
        form = CampaignRequestForm(self.request_data(product_service_name="x" * 255))
        self.assertTrue(form.is_valid(), form.errors)
        form = ClientProfileForm(self.profile_data(company_name="x" * 255), instance=self.owner)
        self.assertTrue(form.is_valid(), form.errors)

    def test_client_campaign_detail_displays_company_and_product(self):
        self.add_business_details()
        self.assert_business_details(self.owner, "client_campaign_detail")

    def test_admin_campaign_detail_displays_client_company_and_product(self):
        self.add_business_details()
        response = self.assert_business_details(self.staff, "administrator_campaign_detail")
        self.assertContains(response, self.owner.username)
        self.assertContains(response, self.owner.email)

    def test_employee_campaign_detail_displays_company_and_product(self):
        self.add_business_details()
        self.assert_business_details(self.employee_user, "employee_campaign_detail")

    def test_client_report_displays_company_and_product_and_print_action(self):
        self.add_business_details()
        response = self.assert_business_details(self.owner, "client_campaign_report")
        self.assertContains(response, "Print / Save as PDF")
        self.assertContains(response, 'onclick="window.print()"')

    def test_admin_report_displays_company_and_product_and_print_action(self):
        self.add_business_details()
        response = self.assert_business_details(self.staff, "administrator_campaign_report")
        self.assertContains(response, "Print / Save as PDF")
        self.assertContains(response, 'onclick="window.print()"')

    def test_details_and_reports_use_current_database_values(self):
        self.add_business_details()
        self.client.force_login(self.owner)
        self.client.post(reverse("client_profile"), self.profile_data(company_name="Updated Company"))
        Campaign.objects.filter(pk=self.campaign.pk).update(product_service_name="Updated Service")
        for user, page in self.audiences():
            with self.subTest(page=page):
                self.client.force_login(user)
                response = self.client.get(reverse(page, args=(self.campaign.pk,)))
                self.assertContains(response, "Updated Company")
                self.assertContains(response, "Updated Service")
                self.assertNotContains(response, self.company_name)
                self.assertNotContains(response, self.product_service_name)

    def assert_unspecified_business_details(self):
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.product_service_name, "")
        for user, page in self.audiences():
            with self.subTest(page=page):
                self.client.force_login(user)
                response = self.client.get(reverse(page, args=(self.campaign.pk,)))
                if page.endswith("report"):
                    self.assertContains(response, '<dt>Company / Business Name</dt><dd class="text-break">Not specified</dd>', html=True)
                    self.assertContains(response, '<dt class="col-sm-4">Product / Service Name</dt><dd class="col-sm-8 text-break">Not specified</dd>', html=True)
                else:
                    for label in ("Company / Business Name", "Product / Service Name"):
                        self.assertContains(response, f'<h2 class="h6 text-uppercase text-secondary">{label}</h2><p class="mb-4 text-break">Not specified</p>', html=True)

    def test_legacy_records_without_client_profile_show_not_specified(self):
        self.assert_unspecified_business_details()
        self.assertFalse(ClientProfile.objects.exists())

    def test_blank_company_and_product_show_not_specified(self):
        ClientProfile.objects.create(user=self.owner)
        self.assert_unspecified_business_details()

    def test_company_and_product_are_escaped_on_forms_details_and_reports(self):
        company = '<script>company()</script>'
        product = '<script>product()</script>'
        ClientProfile.objects.create(user=self.owner, company_name=company)
        Campaign.objects.filter(pk=self.campaign.pk).update(product_service_name=product)
        for user, page in self.audiences():
            self.client.force_login(user)
            response = self.client.get(reverse(page, args=(self.campaign.pk,)))
            for value in (company, product):
                self.assertContains(response, escape(value))
                self.assertNotContains(response, value)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("client_profile"))
        self.assertContains(response, escape(company))
        self.assertNotContains(response, company)
        response = self.client.post(reverse("campaign_request"), self.request_data(
            name="", product_service_name=product,
        ))
        self.assertContains(response, escape(product))
        self.assertNotContains(response, product)

    def test_company_profile_and_campaign_forms_keep_role_and_csrf_restrictions(self):
        self.add_business_details()
        for user in (None, self.employee_user, self.staff, self.superuser):
            self.client.logout()
            if user:
                self.client.force_login(user)
            for page, data in (("client_profile", self.profile_data(company_name="Forbidden")),
                               ("campaign_request", self.request_data())):
                url = reverse(page)
                self.assertRedirects(self.client.get(url), f'{reverse("login")}?next={url}')
                self.assertRedirects(self.client.post(url, data), f'{reverse("login")}?next={url}')
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        for page, data in (("client_profile", self.profile_data(company_name="Forbidden")),
                           ("campaign_request", self.request_data())):
            browser.get(reverse(page))
            self.assertEqual(browser.post(reverse(page), data).status_code, 403)
        self.assertEqual(ClientProfile.objects.get(user=self.owner).company_name, self.company_name)
        self.assertFalse(Campaign.objects.filter(name=self.request_data()["name"]).exists())

    def test_company_and_product_do_not_bypass_campaign_ownership_or_report_roles(self):
        self.add_business_details()
        for user, page, status in (
            (self.other_client, "client_campaign_detail", 404),
            (self.other_client, "client_campaign_report", 404),
            (self.other_employee_user, "employee_campaign_detail", 404),
            (self.owner, "administrator_campaign_detail", 302),
            (self.owner, "administrator_campaign_report", 302),
            (self.employee_user, "client_campaign_report", 302),
            (self.employee_user, "administrator_campaign_report", 302),
        ):
            with self.subTest(user=user.username, page=page):
                self.client.force_login(user)
                response = self.client.get(reverse(page, args=(self.campaign.pk,)))
                self.assertEqual(response.status_code, status)
                self.assertNotIn(self.company_name, response.content.decode())
                self.assertNotIn(self.product_service_name, response.content.decode())

    def test_registration_login_and_profile_save_still_work_without_company(self):
        password = "A-strong-password-2026"
        response = self.client.post(reverse("register"), {
            "username": "newbusinessclient", "email": "newbusiness@example.com",
            "password1": password, "password2": password,
        })
        self.assertRedirects(response, reverse("client_dashboard"))
        user = User.objects.get(username="newbusinessclient")
        self.assertFalse(ClientProfile.objects.filter(user=user).exists())
        self.client.post(reverse("logout"))
        self.assertRedirects(self.client.post(reverse("login"), {
            "username": user.username, "password": password,
        }), reverse("client_dashboard"))
        self.assertRedirects(self.client.post(reverse("client_profile"), {
            "first_name": "New", "last_name": "Client", "email": user.email,
        }), reverse("client_profile"))
        self.assertEqual(ClientProfile.objects.get(user=user).company_name, "")
        user.refresh_from_db()
        self.assertEqual(user.first_name, "New")
        self.assertTrue(user.check_password(password))
