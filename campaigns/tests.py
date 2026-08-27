from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Campaign, EmployeeProfile

class ClientAuthenticationTests(TestCase):
    password = "A-strong-password-2026"

    def test_registration_creates_and_logs_in_client(self):
        response = self.client.post(reverse("register"), {
            "username": "newclient", "email": "client@example.com",
            "password1": self.password, "password2": self.password,
        })
        self.assertRedirects(response, reverse("client_dashboard"))
        self.assertTrue(User.objects.filter(username="newclient").exists())
        self.assertIn("_auth_user_id", self.client.session)

    def test_duplicate_email_is_rejected(self):
        User.objects.create_user("first", "client@example.com", self.password)
        response = self.client.post(reverse("register"), {
            "username": "second", "email": "CLIENT@example.com",
            "password1": self.password, "password2": self.password,
        })
        self.assertContains(response, "An account with this email already exists.")
        self.assertFalse(User.objects.filter(username="second").exists())

    def test_login_redirects_to_dashboard(self):
        User.objects.create_user("client", "client@example.com", self.password)
        response = self.client.post(reverse("login"), {"username": "client", "password": self.password})
        self.assertRedirects(response, reverse("client_dashboard"))

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("client_dashboard"))
        self.assertRedirects(response, f'{reverse("login")}?next={reverse("client_dashboard")}')

    def test_logged_in_client_can_view_and_log_out(self):
        user = User.objects.create_user("client", "client@example.com", self.password)
        self.client.force_login(user)
        dashboard = self.client.get(reverse("client_dashboard"))
        self.assertContains(dashboard, "Welcome, client!")
        self.assertContains(dashboard, "Approve Deliverables")
        self.assertRedirects(self.client.post(reverse("logout")), reverse("home"))


class AdministratorCampaignTests(TestCase):
    password = "A-strong-password-2026"

    def setUp(self):
        self.client_user = User.objects.create_user("campaignclient", "campaign@example.com", self.password)
        self.staff_user = User.objects.create_user("manager", "manager@example.com", self.password, is_staff=True)
        self.campaign = Campaign.objects.create(client=self.client_user, name="Launch Campaign", description="Product launch")

    def test_dashboard_rejects_non_staff_users(self):
        self.client.force_login(self.client_user)
        response = self.client.get(reverse("administrator_dashboard"))
        self.assertRedirects(response, f'{reverse("administrator_login")}?next={reverse("administrator_dashboard")}')

    def test_staff_dashboard_lists_campaign_and_counts(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("administrator_dashboard"))
        self.assertContains(response, "Launch Campaign")
        self.assertContains(response, "campaignclient")
        self.assertEqual(response.context["total_campaigns"], 1)
        self.assertEqual(response.context["pending_campaigns"], 1)

    def test_staff_can_change_status_and_approve_or_reject(self):
        self.client.force_login(self.staff_user)
        detail_url = reverse("administrator_campaign_detail", args=(self.campaign.pk,))
        self.client.post(detail_url, {"status-status": Campaign.Status.IN_PROGRESS, "update_status": "1"})
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, Campaign.Status.IN_PROGRESS)

        decision_url = reverse("administrator_campaign_decision", args=(self.campaign.pk, "reject"))
        self.client.post(decision_url)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, Campaign.Status.REJECTED)


class MarketingEmployeeTests(TestCase):
    password = "A-strong-password-2026"

    def setUp(self):
        self.client_user = User.objects.create_user("clientowner", "owner@example.com", self.password)
        self.employee_user = User.objects.create_user("employee", "employee@example.com", self.password)
        self.employee = EmployeeProfile.objects.create(user=self.employee_user, job_title="Campaign Specialist")
        self.other_user = User.objects.create_user("otheremployee", "other@example.com", self.password)
        self.other_employee = EmployeeProfile.objects.create(user=self.other_user)
        self.campaign = Campaign.objects.create(
            client=self.client_user,
            assigned_employee=self.employee,
            name="Assigned Campaign",
            description="Assigned work",
            status=Campaign.Status.APPROVED,
        )

    def test_employee_login_redirects_to_dashboard(self):
        response = self.client.post(reverse("employee_login"), {
            "username": self.employee_user.username,
            "password": self.password,
        })
        self.assertRedirects(response, reverse("employee_dashboard"))

    def test_employee_sees_only_assigned_campaigns(self):
        Campaign.objects.create(
            client=self.client_user,
            assigned_employee=self.other_employee,
            name="Someone Else Campaign",
            description="Private assignment",
            status=Campaign.Status.APPROVED,
        )
        self.client.force_login(self.employee_user)
        response = self.client.get(reverse("employee_dashboard"))
        self.assertContains(response, "Assigned Campaign")
        self.assertNotContains(response, "Someone Else Campaign")

    def test_employee_cannot_open_another_employees_campaign(self):
        self.client.force_login(self.other_user)
        response = self.client.get(reverse("employee_campaign_detail", args=(self.campaign.pk,)))
        self.assertEqual(response.status_code, 404)

    def test_employee_can_update_progress_and_allowed_status(self):
        self.client.force_login(self.employee_user)
        response = self.client.post(reverse("employee_campaign_detail", args=(self.campaign.pk,)), {
            "progress_percentage": 65,
            "status": Campaign.Status.IN_PROGRESS,
        })
        self.assertRedirects(response, reverse("employee_campaign_detail", args=(self.campaign.pk,)))
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.progress_percentage, 65)
        self.assertEqual(self.campaign.status, Campaign.Status.IN_PROGRESS)

    def test_completed_status_sets_progress_to_one_hundred(self):
        self.client.force_login(self.employee_user)
        self.client.post(reverse("employee_campaign_detail", args=(self.campaign.pk,)), {
            "progress_percentage": 80,
            "status": Campaign.Status.COMPLETED,
        })
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.progress_percentage, 100)
        self.assertEqual(self.campaign.status, Campaign.Status.COMPLETED)

    def test_non_employee_cannot_use_employee_dashboard(self):
        self.client.force_login(self.client_user)
        response = self.client.get(reverse("employee_dashboard"))
        self.assertRedirects(response, f'{reverse("employee_login")}?next={reverse("employee_dashboard")}')


class AdministratorEmployeeManagementTests(TestCase):
    password = "A-strong-password-2026"

    def setUp(self):
        self.staff_user = User.objects.create_user("adminmanager", password=self.password, is_staff=True)
        self.client_user = User.objects.create_user("assignmentclient", password=self.password)
        self.employee_user = User.objects.create_user("assignee", password=self.password)
        self.employee = EmployeeProfile.objects.create(user=self.employee_user)
        self.client.force_login(self.staff_user)

    def test_administrator_can_create_employee_account(self):
        response = self.client.post(reverse("administrator_employee_create"), {
            "username": "newmarketer",
            "first_name": "New",
            "last_name": "Marketer",
            "email": "newmarketer@example.com",
            "job_title": "SEO Specialist",
            "phone": "1234567890",
            "password1": self.password,
            "password2": self.password,
        })
        self.assertRedirects(response, reverse("administrator_employee_list"))
        self.assertTrue(EmployeeProfile.objects.filter(user__username="newmarketer").exists())

    def test_administrator_can_assign_approved_campaign(self):
        campaign = Campaign.objects.create(
            client=self.client_user,
            name="Approved Assignment",
            description="Ready for work",
            status=Campaign.Status.APPROVED,
        )
        response = self.client.post(reverse("administrator_campaign_detail", args=(campaign.pk,)), {
            "assignment-assigned_employee": self.employee.pk,
            "update_assignment": "1",
        })
        self.assertRedirects(response, reverse("administrator_campaign_detail", args=(campaign.pk,)))
        campaign.refresh_from_db()
        self.assertEqual(campaign.assigned_employee, self.employee)

    def test_pending_campaign_cannot_be_assigned(self):
        campaign = Campaign.objects.create(
            client=self.client_user,
            name="Pending Assignment",
            description="Not approved",
        )
        response = self.client.post(reverse("administrator_campaign_detail", args=(campaign.pk,)), {
            "assignment-assigned_employee": self.employee.pk,
            "update_assignment": "1",
        })
        self.assertContains(response, "Only approved campaigns can be assigned.")
        campaign.refresh_from_db()
        self.assertIsNone(campaign.assigned_employee)
