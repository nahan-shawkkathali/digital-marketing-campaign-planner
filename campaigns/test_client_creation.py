from unittest.mock import patch

from django.contrib.auth.hashers import identify_hasher
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from .forms import ClientRegistrationForm
from .models import ClientProfile, EmployeeProfile
from .test_audit import AuditFixtures
from .views import is_client


class ClientCreationTests(AuditFixtures):
    password = "Account-creation-2026!"
    fields = ("username", "first_name", "last_name", "email", "company_name", "password1", "password2")

    def account_data(self, **overrides):
        return {
            "username": "newclient", "first_name": "Anita", "last_name": "Rao",
            "email": "NEWCLIENT@example.com", "company_name": "Bright Garden",
            "password1": self.password, "password2": self.password, **overrides,
        }

    def submit(self, route, data):
        self.client.logout()
        if route == "administrator_client_create":
            self.client.force_login(self.staff)
        return self.client.post(reverse(route), data)

    def record_counts(self):
        return (User.objects.count(), ClientProfile.objects.count(), EmployeeProfile.objects.count())

    def assert_client_account(self, data):
        user = User.objects.get(username=data["username"])
        self.assertEqual(user.first_name, data["first_name"])
        self.assertEqual(user.last_name, data["last_name"])
        self.assertEqual(user.email, data["email"].lower())
        self.assertTrue(user.is_active)
        self.assertTrue(is_client(user))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(EmployeeProfile.objects.filter(user=user).exists())
        self.assertFalse(user.groups.exists())
        self.assertFalse(user.user_permissions.exists())
        self.assertNotEqual(user.password, data["password1"])
        self.assertTrue(identify_hasher(user.password).algorithm)
        self.assertTrue(user.check_password(data["password1"]))
        profile = ClientProfile.objects.get(user=user)
        self.assertEqual(profile.company_name, data["company_name"])
        return user

    def assert_creation_fields(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(tuple(response.context["form"].fields), self.fields)
        self.assertContains(response, "Company / Business Name")
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        for name, field in response.context["form"].fields.items():
            self.assertContains(response, f'name="{name}"')
            self.assertEqual(field.widget.attrs["class"], "form-control")
            self.assertNotIn("placeholder", field.widget.attrs)
        self.assertFalse(response.context["form"].fields["company_name"].required)

    def test_registration_displays_added_fields_without_creating_records(self):
        before = self.record_counts()
        self.assert_creation_fields(self.client.get(reverse("register")))
        self.assertEqual(self.record_counts(), before)

    def test_admin_dashboard_links_to_client_form_with_all_registration_fields(self):
        before = self.record_counts()
        self.client.force_login(self.staff)
        url = reverse("administrator_client_create")
        self.assertContains(self.client.get(reverse("administrator_dashboard")),
                            f'<a class="btn btn-light" href="{url}">Add Client</a>', html=True)
        self.assert_creation_fields(self.client.get(url))
        self.assertEqual(self.record_counts(), before)

    def test_registration_saves_all_details_and_preserves_automatic_login(self):
        data = self.account_data()
        users, profiles, employees = self.record_counts()
        self.assertRedirects(self.submit("register", data), reverse("client_dashboard"))
        user = self.assert_client_account(data)
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
        self.assertContains(self.client.get(reverse("client_profile")), 'value="Bright Garden"')
        self.assertEqual(self.record_counts(), (users + 1, profiles + 1, employees))

    def test_staff_and_superuser_can_create_clients_without_switching_admin_session(self):
        for index, administrator in enumerate((self.staff, self.superuser)):
            with self.subTest(administrator=administrator.username):
                self.client.force_login(administrator)
                data = self.account_data(username=f"createdclient{index}", email=f"created{index}@example.com")
                response = self.client.post(reverse("administrator_client_create"), data)
                self.assertRedirects(response, reverse("administrator_dashboard"))
                self.assertEqual(self.client.session["_auth_user_id"], str(administrator.pk))
                user = self.assert_client_account(data)
                browser = Client()
                self.assertRedirects(browser.post(reverse("login"), {
                    "username": user.username, "password": self.password,
                }), reverse("client_dashboard"))
                self.assertContains(browser.get(reverse("client_profile")), 'value="Bright Garden"')
                for route, login in (("administrator_client_create", "administrator_login"),
                                     ("administrator_dashboard", "administrator_login"),
                                     ("employee_dashboard", "employee_login")):
                    url = reverse(route)
                    self.assertRedirects(browser.get(url), f'{reverse(login)}?next={url}')

    def test_both_creation_methods_populate_editable_profile_without_duplicates(self):
        for index, route in enumerate(("register", "administrator_client_create")):
            with self.subTest(route=route):
                data = self.account_data(username=f"profileclient{index}", email=f"profile{index}@example.com")
                self.assertEqual(self.submit(route, data).status_code, 302)
                user = self.assert_client_account(data)
                profile = ClientProfile.objects.get(user=user)
                self.client.force_login(user)
                response = self.client.get(reverse("client_profile"))
                for field in ("first_name", "last_name", "company_name"):
                    self.assertEqual(response.context["form"][field].value(), data[field])
                self.assertEqual(response.context["form"]["email"].value(), data["email"].lower())
                for company in ("Updated Garden", ""):
                    self.assertRedirects(self.client.post(reverse("client_profile"), {
                        "first_name": user.first_name, "last_name": user.last_name,
                        "email": user.email, "company_name": company,
                    }), reverse("client_profile"))
                    profile.refresh_from_db()
                    self.assertEqual(profile.company_name, company)
                    self.assertEqual(ClientProfile.objects.get(user=user).pk, profile.pk)

    def test_admin_can_omit_or_leave_company_blank(self):
        for index, company in enumerate((None, "")):
            data = self.account_data(username=f"optionalclient{index}", email=f"optional{index}@example.com",
                                     company_name=company)
            if company is None:
                data.pop("company_name")
            self.assertRedirects(self.submit("administrator_client_create", data), reverse("administrator_dashboard"))
            user = User.objects.get(username=data["username"])
            self.assertTrue(is_client(user))
            self.assertFalse(ClientProfile.objects.filter(user=user).exists())
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("client_profile")).context["form"]["company_name"].value(), "")

    def test_non_administrators_cannot_read_or_submit_client_creation(self):
        before = self.record_counts()
        url = reverse("administrator_client_create")
        for user in (None, self.owner, self.employee_user):
            with self.subTest(user=user):
                self.client.logout()
                if user:
                    self.client.force_login(user)
                for method in ("get", "post"):
                    response = getattr(self.client, method)(url, self.account_data() if method == "post" else {})
                    self.assertRedirects(response, f'{reverse("administrator_login")}?next={url}')
        self.assertEqual(self.record_counts(), before)

    def test_both_creation_methods_require_csrf_and_accept_valid_tokens(self):
        for index, route in enumerate(("register", "administrator_client_create")):
            with self.subTest(route=route):
                browser = Client(enforce_csrf_checks=True)
                if route == "administrator_client_create":
                    browser.force_login(self.staff)
                data = self.account_data(username=f"csrfclient{index}", email=f"csrf{index}@example.com")
                url = reverse(route)
                browser.get(url)
                before = self.record_counts()
                self.assertEqual(browser.post(url, data).status_code, 403)
                self.assertEqual(self.record_counts(), before)
                response = browser.post(url, {**data, "csrfmiddlewaretoken": browser.cookies["csrftoken"].value})
                self.assertEqual(response.status_code, 302)
                self.assert_client_account(data)

    def test_admin_client_creation_rejects_unsupported_methods(self):
        self.client.force_login(self.staff)
        before = self.record_counts()
        for method in ("put", "patch", "delete", "head"):
            self.assertEqual(getattr(self.client, method)(reverse("administrator_client_create")).status_code, 405)
        self.assertEqual(self.record_counts(), before)

    def test_forged_roles_and_existing_account_ids_are_ignored_by_both_methods(self):
        profile = ClientProfile.objects.create(user=self.owner, company_name="Existing Company")
        original_user = User.objects.filter(pk=self.owner.pk).values().get()
        for index, route in enumerate(("register", "administrator_client_create")):
            data = self.account_data(username=f"safeclient{index}", email=f"safe{index}@example.com",
                id=self.owner.pk, user_id=self.owner.pk, profile_id=profile.pk,
                is_staff=True, is_superuser=True, is_active=False, role="administrator",
                employee_profile=self.employee.pk, groups=[1], user_permissions=[1])
            self.assertEqual(self.submit(route, data).status_code, 302)
            user = self.assert_client_account(data)
            self.assertNotEqual(user.pk, self.owner.pk)
            self.assertEqual(User.objects.filter(pk=self.owner.pk).values().get(), original_user)
            profile.refresh_from_db()
            self.assertEqual(profile.company_name, "Existing Company")

    def test_both_methods_validate_details_and_passwords_without_partial_accounts(self):
        cases = (
            ({"username": self.owner.username}, "username"),
            ({"email": self.owner.email.upper()}, "email"),
            ({"email": "invalid"}, "email"),
            ({"first_name": "x" * 151}, "first_name"),
            ({"last_name": "x" * 151}, "last_name"),
            ({"company_name": "x" * 256}, "company_name"),
            ({"password2": "different-password"}, "password2"),
            ({"password1": "12345678", "password2": "12345678"}, "password2"),
        )
        before = self.record_counts()
        for route in ("register", "administrator_client_create"):
            for changes, field in cases:
                with self.subTest(route=route, field=field, changes=changes):
                    response = self.submit(route, self.account_data(**changes))
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(field, response.context["form"].errors)
                    self.assertNotContains(response, f'value="{self.password}"')
                    self.assertEqual(self.record_counts(), before)

    def test_creation_rolls_back_user_if_company_profile_cannot_be_saved(self):
        before = self.record_counts()
        form = ClientRegistrationForm(self.account_data())
        self.assertTrue(form.is_valid(), form.errors)
        with patch.object(ClientProfile.objects, "update_or_create", side_effect=RuntimeError("Save failed")):
            with self.assertRaises(RuntimeError):
                form.save()
        self.assertEqual(self.record_counts(), before)

    def test_creation_commit_false_does_not_save_user_or_profile(self):
        before = self.record_counts()
        form = ClientRegistrationForm(self.account_data())
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save(commit=False)
        self.assertIsNone(user.pk)
        self.assertEqual(user.first_name, "Anita")
        self.assertTrue(user.check_password(self.password))
        self.assertEqual(self.record_counts(), before)

    def test_admin_repeated_submission_cannot_duplicate_or_overwrite_client(self):
        data = self.account_data()
        self.assertRedirects(self.submit("administrator_client_create", data), reverse("administrator_dashboard"))
        before = self.record_counts()
        response = self.client.post(reverse("administrator_client_create"), {**data, "company_name": "Replacement"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("username", response.context["form"].errors)
        self.assertIn("email", response.context["form"].errors)
        self.assertEqual(self.record_counts(), before)
        self.assert_client_account(data)
