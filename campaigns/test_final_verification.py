from html.parser import HTMLParser
from urllib.parse import urlsplit

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import resolve, reverse

from .forms import EmployeeCampaignProgressForm
from .models import Campaign, Deliverable, Task
from .test_audit import AuditFixtures


class FinalRegressionTests(AuditFixtures):
    def test_tracking_is_a_separate_owned_page(self):
        Campaign.objects.create(client=self.other_client, name="Private tracking", description="Private")
        Campaign.objects.filter(pk=self.campaign.pk).update(progress_percentage=45)
        self.client.force_login(self.owner)
        url = reverse("client_campaign_tracking")
        self.assertNotEqual(url, reverse("client_campaign_list"))
        self.assertContains(self.client.get(reverse("client_dashboard")), f'href="{url}"')
        response = self.client.get(url, {"client": self.other_client.pk, "campaign_id": 99999})
        self.assertContains(response, "Track Campaign Progress")
        self.assertContains(response, "45%")
        self.assertContains(response, "0 / 1")
        self.assertNotContains(response, "Private tracking")
        for user in (self.staff, self.employee_user):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 302)
        self.client.logout()
        self.assertRedirects(self.client.get(url), f'{reverse("login")}?next={url}')
        self.client.force_login(self.other_client)
        Campaign.objects.filter(client=self.other_client).delete()
        self.assertContains(self.client.get(url), "No campaigns found.")

    def test_completed_status_does_not_bypass_progress_validation(self):
        for status in (Campaign.Status.IN_PROGRESS, Campaign.Status.COMPLETED):
            for value in (-1, 101, "", "invalid", "12.5"):
                with self.subTest(status=status, progress=value):
                    self.campaign.refresh_from_db()
                    form = EmployeeCampaignProgressForm(
                        {"status": status, "progress_percentage": value}, instance=self.campaign,
                    )
                    self.assertFalse(form.is_valid())
                    self.assertIn("progress_percentage", form.errors)

    def test_administrator_completion_sets_progress_to_one_hundred(self):
        self.client.force_login(self.staff)
        url = reverse("administrator_campaign_detail", args=(self.campaign.pk,))
        self.assertRedirects(self.client.post(url, {
            "status-status": "completed", "update_status": "1",
        }), url)
        self.campaign.refresh_from_db()
        self.assertEqual((self.campaign.status, self.campaign.progress_percentage), ("completed", 100))

    def test_reassignment_transfers_tasks_and_revokes_previous_employee_access(self):
        self.client.force_login(self.staff)
        url = reverse("administrator_campaign_detail", args=(self.campaign.pk,))
        self.assertRedirects(self.client.post(url, {
            "assignment-assigned_employee": self.other_employee.pk, "update_assignment": "1",
        }), url)
        self.task.refresh_from_db()
        self.assertEqual(self.task.assigned_employee, self.other_employee)
        self.assertEqual(self.task.status, Task.Status.PENDING)
        self.client.force_login(self.employee_user)
        self.assertNotContains(self.client.get(reverse("employee_task_list")), self.task.title)
        for name in ("employee_task_detail", "employee_task_status_update"):
            response = self.client.post(reverse(name, args=(self.task.pk,)), {"status": "completed"})
            self.assertEqual(response.status_code, 404)
        self.client.force_login(self.other_employee_user)
        self.assertEqual(self.client.get(reverse("employee_task_detail", args=(self.task.pk,))).status_code, 200)

    def test_stale_task_assignment_cannot_expose_or_update_campaign_work(self):
        Campaign.objects.filter(pk=self.campaign.pk).update(assigned_employee=self.other_employee)
        self.client.force_login(self.employee_user)
        self.assertNotContains(self.client.get(reverse("employee_task_list")), self.task.title)
        self.assertEqual(self.client.get(reverse("employee_task_detail", args=(self.task.pk,))).status_code, 404)
        self.assertEqual(self.client.post(reverse("employee_task_status_update", args=(self.task.pk,)), {
            "status": "completed",
        }).status_code, 404)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.PENDING)

    def test_task_creation_requires_campaign_assignment(self):
        Campaign.objects.filter(pk=self.campaign.pk).update(assigned_employee=None)
        self.client.force_login(self.staff)
        response = self.client.post(reverse("administrator_task_create", args=(self.campaign.pk,)), {
            "title": "Unassigned campaign task", "due_date": "2026-10-01",
            "assigned_employee": self.employee.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assign an active employee to this campaign before creating tasks.")
        self.assertFalse(Task.objects.filter(title="Unassigned campaign task").exists())

    def test_admin_can_assign_and_add_tasks_while_campaign_is_in_progress(self):
        Campaign.objects.filter(pk=self.campaign.pk).update(status=Campaign.Status.IN_PROGRESS)
        self.client.force_login(self.staff)
        detail = reverse("administrator_campaign_detail", args=(self.campaign.pk,))
        self.assertRedirects(self.client.post(detail, {
            "assignment-assigned_employee": self.other_employee.pk, "update_assignment": "1",
        }), detail)
        task_url = reverse("administrator_task_create", args=(self.campaign.pk,))
        self.assertContains(self.client.get(detail), f'href="{task_url}"')
        self.assertRedirects(self.client.post(task_url, {
            "title": "Follow-up task", "due_date": "2026-10-01", "assigned_employee": self.other_employee.pk,
        }), detail)
        self.assertEqual(Task.objects.get(title="Follow-up task").assigned_employee, self.other_employee)
        for status in (Campaign.Status.PENDING, Campaign.Status.REJECTED, Campaign.Status.COMPLETED):
            Campaign.objects.filter(pk=self.campaign.pk).update(status=status)
            self.assertEqual(self.client.get(task_url).status_code, 404)

    def test_login_next_does_not_return_users_to_a_wrong_role_or_dead_end(self):
        password = "Audit-login-password-2026"
        self.employee_user.set_password(password)
        self.employee_user.save(update_fields=("password",))
        for destination in (reverse("client_dashboard"), reverse("employee_login"),
                            reverse("employee_task_status_update", args=(self.task.pk,)),
                            "/missing-page/", "https://example.com/"):
            with self.subTest(next=destination):
                self.client.logout()
                self.assertRedirects(self.client.post(reverse("login"), {
                    "username": self.employee_user.username, "password": password, "next": destination,
                }), reverse("employee_dashboard"))
        self.client.logout()
        destination = reverse("employee_campaign_detail", args=(self.campaign.pk,))
        self.assertRedirects(self.client.post(reverse("employee_login"), {
            "username": self.employee_user.username, "password": password, "next": destination,
        }), destination)

    def test_invalid_choices_and_uploads_do_not_change_saved_records(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("administrator_campaign_detail", args=(self.campaign.pk,)), {
            "status-status": "invalid", "update_status": "1",
        })
        self.assertTrue(response.context["status_form"].errors)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, Campaign.Status.APPROVED)
        self.client.force_login(self.employee_user)
        response = self.client.post(reverse("employee_campaign_detail", args=(self.campaign.pk,)), {
            "status": "approved", "progress_percentage": 40,
        })
        self.assertTrue(response.context["progress_form"].errors)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.progress_percentage, 0)
        for upload in (SimpleUploadedFile("empty.pdf", b""), SimpleUploadedFile("unsafe.html", b"<script>bad()</script>")):
            response = self.client.post(reverse("employee_deliverable_upload", args=(self.campaign.pk,)), {
                "title": "Invalid upload", "uploaded_file": upload,
            })
            self.assertTrue(response.context["form"].errors)
            self.assertFalse(Deliverable.objects.filter(title="Invalid upload").exists())

    def test_pending_and_rejected_campaigns_cannot_be_restarted_by_employee(self):
        self.client.force_login(self.employee_user)
        for status in (Campaign.Status.PENDING, Campaign.Status.REJECTED):
            with self.subTest(status=status):
                Campaign.objects.filter(pk=self.campaign.pk).update(status=status)
                response = self.client.post(reverse("employee_campaign_detail", args=(self.campaign.pk,)), {
                    "status": "in_progress", "progress_percentage": 40,
                })
                self.assertContains(response, "This campaign must be approved before work can be updated.")
                self.client.post(reverse("employee_task_status_update", args=(self.task.pk,)), {"status": "completed"})
                self.client.post(reverse("employee_deliverable_upload", args=(self.campaign.pk,)), {
                    "title": "Blocked work", "uploaded_file": SimpleUploadedFile("blocked.pdf", b"test"),
                })
                self.campaign.refresh_from_db()
                self.task.refresh_from_db()
                self.assertEqual(self.campaign.status, status)
                self.assertEqual(self.campaign.progress_percentage, 0)
                self.assertEqual(self.task.status, Task.Status.PENDING)
                self.assertFalse(Deliverable.objects.filter(title="Blocked work").exists())

    def test_empty_posts_display_required_field_errors(self):
        cases = [(self.owner, "campaign_request", ()), (self.owner, "client_profile", ()),
                 (self.staff, "administrator_employee_create", ()),
                 (self.staff, "administrator_employee_edit", (self.employee.pk,)),
                 (self.staff, "administrator_task_create", (self.campaign.pk,)),
                 (self.employee_user, "employee_profile", ()),
                 (self.employee_user, "employee_campaign_detail", (self.campaign.pk,)),
                 (self.employee_user, "employee_deliverable_upload", (self.campaign.pk,))]
        for user, name, args in cases:
            with self.subTest(page=name):
                self.client.force_login(user)
                self.assertContains(self.client.post(reverse(name, args=args), {}), "This field is required.")
        self.client.logout()
        self.assertContains(self.client.post(reverse("register"), {}), "This field is required.")

    def test_negative_budget_is_rejected_and_date_errors_are_useful(self):
        self.client.force_login(self.owner)
        for data, message in (
            ({"budget": "-1"}, "Budget cannot be negative."),
            ({"start_date": "2026-10-02", "end_date": "2026-10-01"}, "End date cannot be before the start date."),
            ({"start_date": "invalid"}, "Enter a valid date."),
        ):
            with self.subTest(data=data):
                response = self.client.post(reverse("campaign_request"), {
                    "name": "Invalid request", "description": "Invalid", **data,
                })
                self.assertContains(response, message)
                self.assertFalse(Campaign.objects.filter(name="Invalid request").exists())

    def test_employee_profile_rejects_invalid_duplicate_and_overlong_email(self):
        long_email = "a" * 64 + "@" + "b" * 63 + "." + "c" * 63 + "." + "d" * 60 + ".com"
        for user, name, args in (
            (self.employee_user, "employee_profile", ()),
            (self.staff, "administrator_employee_edit", (self.employee.pk,)),
        ):
            self.client.force_login(user)
            for email in (long_email, "invalid-email", "CLIENT@example.com"):
                with self.subTest(page=name, email_length=len(email)):
                    response = self.client.post(reverse(name, args=args), {
                        "first_name": "Maya", "email": email, "is_active": "on",
                    })
                    self.assertTrue(response.context["form"].has_error("email"))
                    self.employee_user.refresh_from_db()
                    self.assertEqual(self.employee_user.email, "employee@example.com")

    def test_invalid_progress_does_not_appear_as_saved_on_detail(self):
        self.client.force_login(self.employee_user)
        response = self.client.post(reverse("employee_campaign_detail", args=(self.campaign.pk,)), {
            "progress_percentage": 101, "status": "in_progress",
        })
        self.assertContains(response, 'aria-valuenow="0"')
        self.assertNotContains(response, 'width:101%')

    def test_administrator_forms_only_validate_the_submitted_action(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("administrator_campaign_detail", args=(self.campaign.pk,)), {
            "assignment-assigned_employee": 99999, "update_assignment": "1",
        })
        self.assertTrue(response.context["assignment_form"].errors)
        self.assertFalse(response.context["status_form"].is_bound)
        self.assertNotContains(response, "This field is required.")

    def test_client_login_routes_staff_and_employees_to_their_dashboard(self):
        password = "Audit-login-password-2026"
        for user, destination in ((self.staff, "administrator_dashboard"), (self.employee_user, "employee_dashboard")):
            with self.subTest(user=user.username):
                user.set_password(password)
                user.save(update_fields=("password",))
                self.client.logout()
                self.assertRedirects(self.client.post(reverse("login"), {
                    "username": user.username, "password": password,
                }), reverse(destination))

    def test_error_messages_use_bootstrap_danger_style(self):
        self.client.force_login(self.employee_user)
        response = self.client.post(reverse("employee_task_status_update", args=(self.task.pk,)), {
            "status": "invalid",
        }, follow=True)
        self.assertContains(response, 'class="alert alert-danger"')
        self.assertContains(response, "Please select a valid task status.")


class PageMarkup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links, self.forms, self.ids = [], [], set()
        self.current_form = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "a":
            self.links.append(attrs.get("href", ""))
        if tag == "form":
            self.current_form = {"method": attrs.get("method", "get"), "action": attrs.get("action", ""), "csrf": False}
            self.forms.append(self.current_form)
        if tag == "input" and self.current_form is not None and attrs.get("name") == "csrfmiddlewaretoken":
            self.current_form["csrf"] = bool(attrs.get("value"))

    def handle_endtag(self, tag):
        if tag == "form":
            self.current_form = None


class NavigationRegressionTests(AuditFixtures):
    def test_rendered_links_fragments_and_post_forms_for_every_role(self):
        self.deliverable.uploaded_file.save("navigation.pdf", SimpleUploadedFile("navigation.pdf", b"audit"))
        users = {"client": self.owner, "administrator": self.staff, "employee": self.employee_user}
        routes = self.role_routes()
        for role, user in users.items():
            self.client.force_login(user)
            for name, args in routes[role] + [("home", ())]:
                url = reverse(name, args=args)
                page = self.client.get(url)
                self.assertEqual(page.status_code, 200)
                parsed = PageMarkup(page.content.decode())
                for link in parsed.links:
                    with self.subTest(page=name, link=link):
                        self.assertNotIn(link, ("", "#"))
                        target = urlsplit(link)
                        if target.netloc:
                            continue
                        response = self.client.get(target.path or url, follow=True)
                        self.assertEqual(response.status_code, 200)
                        if target.fragment:
                            self.assertIn(target.fragment, PageMarkup(response.content.decode()).ids)
                        response.close()
                for form in parsed.forms:
                    self.assertEqual(form["method"].lower(), "post")
                    self.assertTrue(form["csrf"])
                    self.assertIsNotNone(resolve(form["action"] or url))
        self.client.logout()
        for name in ("home", "register", "login", "administrator_login", "employee_login"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)
            for form in PageMarkup(response.content.decode()).forms:
                self.assertTrue(form["csrf"])

    def test_login_and_tracking_csrf_and_logout_methods(self):
        browser = Client(enforce_csrf_checks=True)
        for name in ("register", "login", "employee_login", "administrator_login"):
            self.assertEqual(browser.post(reverse(name), {}).status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertEqual(self.client.post(reverse("client_campaign_tracking")).status_code, 405)
