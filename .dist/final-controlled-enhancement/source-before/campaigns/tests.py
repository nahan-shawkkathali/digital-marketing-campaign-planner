import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Campaign, Deliverable, EmployeeProfile, Task

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

    def test_client_can_submit_pending_campaign_request(self):
        user = User.objects.create_user("requester", "requester@example.com", self.password)
        self.client.force_login(user)
        response = self.client.post(reverse("campaign_request"), {
            "name": "Social Media Launch",
            "description": "Launch the new product on social media.",
            "target_audience": "College students",
            "budget": "25000.00",
            "start_date": "2026-09-10",
            "end_date": "2026-10-10",
        })
        self.assertRedirects(response, reverse("client_campaign_list"))
        campaign = Campaign.objects.get(name="Social Media Launch")
        self.assertEqual(campaign.client, user)
        self.assertEqual(campaign.status, Campaign.Status.PENDING)

    def test_client_campaign_list_only_contains_own_campaigns(self):
        user = User.objects.create_user("owner", password=self.password)
        other_user = User.objects.create_user("otherowner", password=self.password)
        Campaign.objects.create(client=user, name="My Campaign", description="Mine")
        Campaign.objects.create(client=other_user, name="Private Campaign", description="Theirs")
        self.client.force_login(user)
        response = self.client.get(reverse("client_campaign_list"))
        self.assertContains(response, "My Campaign")
        self.assertNotContains(response, "Private Campaign")

    def test_campaign_request_requires_login(self):
        response = self.client.get(reverse("campaign_request"))
        self.assertRedirects(response, f'{reverse("login")}?next={reverse("campaign_request")}')


class ClientProfileTests(TestCase):
    password = "A-strong-password-2026"

    def setUp(self):
        self.user = User.objects.create_user(
            "profileclient",
            "old@example.com",
            self.password,
            first_name="Old",
            last_name="Name",
        )

    def test_client_can_view_current_profile_information(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("client_profile"))
        self.assertContains(response, "profileclient")
        self.assertContains(response, "Old")
        self.assertContains(response, "Name")
        self.assertContains(response, "old@example.com")
        self.assertContains(response, "readonly")

    def test_client_can_update_own_profile(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("client_profile"), {
            "first_name": "Updated",
            "last_name": "Client",
            "email": "UPDATED@example.com",
        })
        self.assertRedirects(response, reverse("client_profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Updated")
        self.assertEqual(self.user.last_name, "Client")
        self.assertEqual(self.user.email, "updated@example.com")
        self.assertEqual(self.user.username, "profileclient")

    def test_profile_update_does_not_change_another_user(self):
        other = User.objects.create_user("unchangedclient", "unchanged@example.com", self.password)
        self.client.force_login(self.user)
        self.client.post(reverse("client_profile"), {
            "first_name": "Only",
            "last_name": "Owner",
            "email": "owner@example.com",
            "user_id": other.pk,
        })
        other.refresh_from_db()
        self.assertEqual(other.email, "unchanged@example.com")

    def test_duplicate_email_redisplays_validation_error(self):
        User.objects.create_user("existingclient", "used@example.com", self.password)
        self.client.force_login(self.user)
        response = self.client.post(reverse("client_profile"), {
            "first_name": "Old",
            "last_name": "Name",
            "email": "USED@example.com",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "An account with this email already exists.")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.com")

    def test_anonymous_user_is_redirected_to_client_login(self):
        response = self.client.get(reverse("client_profile"))
        self.assertRedirects(response, f'{reverse("login")}?next={reverse("client_profile")}')

    def test_employee_and_staff_cannot_access_client_profile(self):
        employee_user = User.objects.create_user("profileemployee", password=self.password)
        EmployeeProfile.objects.create(user=employee_user)
        self.client.force_login(employee_user)
        self.assertEqual(self.client.get(reverse("client_profile")).status_code, 302)

        staff = User.objects.create_user("profileadmin", password=self.password, is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("client_profile")).status_code, 302)


class ClientCampaignDetailTests(TestCase):
    password = "A-strong-password-2026"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_directory = tempfile.TemporaryDirectory()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_directory.name)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        cls._media_directory.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.owner = User.objects.create_user("detailowner", password=self.password)
        self.other_client = User.objects.create_user("otherclient", password=self.password)
        employee_user = User.objects.create_user("detailmarketer", first_name="Maya", last_name="Singh", password=self.password)
        self.employee = EmployeeProfile.objects.create(user=employee_user)
        self.campaign = Campaign.objects.create(
            client=self.owner,
            assigned_employee=self.employee,
            name="Owned Campaign",
            description="Campaign visible to its owner.",
            campaign_type="Social Media",
            status=Campaign.Status.IN_PROGRESS,
            progress_percentage=40,
        )
        self.deliverable = Deliverable.objects.create(
            campaign=self.campaign,
            uploaded_by=self.employee,
            title="Creative Preview",
            description="First creative version.",
            uploaded_file=SimpleUploadedFile("creative.pdf", b"sample content"),
        )

    def detail_url(self, campaign=None):
        return reverse("client_campaign_detail", args=((campaign or self.campaign).pk,))

    def decision_url(self, decision, campaign=None, deliverable=None):
        return reverse("client_deliverable_decision", args=(
            (campaign or self.campaign).pk,
            (deliverable or self.deliverable).pk,
            decision,
        ))

    def test_client_can_open_own_campaign_detail_and_see_deliverable(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.detail_url())
        self.assertContains(response, "Owned Campaign")
        self.assertContains(response, "Social Media")
        self.assertContains(response, "Creative Preview")
        self.assertContains(response, "Maya Singh")
        self.assertContains(response, self.deliverable.uploaded_file.url)

    def test_client_cannot_open_another_clients_campaign(self):
        self.client.force_login(self.other_client)
        response = self.client.get(self.detail_url())
        self.assertEqual(response.status_code, 404)

    def test_detail_only_shows_deliverables_from_that_campaign(self):
        other_campaign = Campaign.objects.create(
            client=self.owner,
            name="Second Campaign",
            description="Separate campaign.",
        )
        Deliverable.objects.create(
            campaign=other_campaign,
            uploaded_by=self.employee,
            title="Unrelated Deliverable",
            uploaded_file=SimpleUploadedFile("unrelated.pdf", b"other content"),
        )
        self.client.force_login(self.owner)
        response = self.client.get(self.detail_url())
        self.assertContains(response, "Creative Preview")
        self.assertNotContains(response, "Unrelated Deliverable")

    def test_client_can_approve_own_campaign_deliverable(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.decision_url("approve"))
        self.assertRedirects(response, self.detail_url())
        self.deliverable.refresh_from_db()
        self.assertEqual(self.deliverable.approval_status, Deliverable.ApprovalStatus.APPROVED)

    def test_client_can_reject_own_campaign_deliverable(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.decision_url("reject"))
        self.assertRedirects(response, self.detail_url())
        self.deliverable.refresh_from_db()
        self.assertEqual(self.deliverable.approval_status, Deliverable.ApprovalStatus.REJECTED)

    def test_client_cannot_decide_another_clients_deliverable(self):
        self.client.force_login(self.other_client)
        response = self.client.post(self.decision_url("approve"))
        self.assertEqual(response.status_code, 404)
        self.deliverable.refresh_from_db()
        self.assertEqual(self.deliverable.approval_status, Deliverable.ApprovalStatus.PENDING)

    def test_deliverable_decision_requires_post(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.decision_url("approve"))
        self.assertEqual(response.status_code, 405)
        self.deliverable.refresh_from_db()
        self.assertEqual(self.deliverable.approval_status, Deliverable.ApprovalStatus.PENDING)

    def test_anonymous_user_is_redirected_to_client_login(self):
        response = self.client.get(self.detail_url())
        self.assertRedirects(response, f'{reverse("login")}?next={self.detail_url()}')

    def test_employee_and_staff_accounts_cannot_open_client_detail(self):
        self.client.force_login(self.employee.user)
        self.assertEqual(self.client.get(self.detail_url()).status_code, 302)
        staff = User.objects.create_user("detailadmin", password=self.password, is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.detail_url()).status_code, 302)


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

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_directory = tempfile.TemporaryDirectory()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_directory.name)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        cls._media_directory.cleanup()
        super().tearDownClass()

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

    def test_dashboard_shows_employee_job_title_and_campaign_deadline(self):
        self.campaign.end_date = "2026-09-30"
        self.campaign.save(update_fields=("end_date",))
        self.client.force_login(self.employee_user)
        response = self.client.get(reverse("employee_dashboard"))
        self.assertContains(response, "Campaign Specialist")
        self.assertContains(response, "Sep 30, 2026")

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

    def test_assigned_employee_can_upload_deliverable(self):
        self.client.force_login(self.employee_user)
        uploaded_file = SimpleUploadedFile(
            "campaign-report.pdf",
            b"sample pdf content",
            content_type="application/pdf",
        )
        response = self.client.post(
            reverse("employee_deliverable_upload", args=(self.campaign.pk,)),
            {
                "title": "Campaign Report",
                "description": "First campaign report",
                "uploaded_file": uploaded_file,
            },
        )
        self.assertRedirects(response, reverse("employee_campaign_detail", args=(self.campaign.pk,)))
        deliverable = Deliverable.objects.get(title="Campaign Report")
        self.assertEqual(deliverable.campaign, self.campaign)
        self.assertEqual(deliverable.uploaded_by, self.employee)
        self.assertEqual(deliverable.approval_status, Deliverable.ApprovalStatus.PENDING)
        self.assertTrue(deliverable.uploaded_file.storage.exists(deliverable.uploaded_file.name))

    def test_unassigned_employee_cannot_upload_deliverable(self):
        self.client.force_login(self.other_user)
        response = self.client.get(reverse("employee_deliverable_upload", args=(self.campaign.pk,)))
        self.assertEqual(response.status_code, 404)

    def test_disallowed_deliverable_file_extension_is_rejected(self):
        self.client.force_login(self.employee_user)
        response = self.client.post(
            reverse("employee_deliverable_upload", args=(self.campaign.pk,)),
            {
                "title": "Unsafe File",
                "description": "Should not be accepted",
                "uploaded_file": SimpleUploadedFile("program.exe", b"not allowed"),
            },
        )
        self.assertContains(response, "File extension “exe” is not allowed")
        self.assertFalse(Deliverable.objects.filter(title="Unsafe File").exists())


class CampaignTaskManagementTests(TestCase):
    password = "A-strong-password-2026"

    def setUp(self):
        self.client_user = User.objects.create_user("taskclient", password=self.password)
        self.staff_user = User.objects.create_user("taskadmin", password=self.password, is_staff=True)
        self.employee_user = User.objects.create_user("taskemployee", password=self.password)
        self.employee = EmployeeProfile.objects.create(user=self.employee_user)
        self.other_employee_user = User.objects.create_user("othertaskemployee", password=self.password)
        self.other_employee = EmployeeProfile.objects.create(user=self.other_employee_user)
        self.campaign = Campaign.objects.create(
            client=self.client_user,
            assigned_employee=self.employee,
            name="Task Campaign",
            description="Campaign with tasks",
            status=Campaign.Status.APPROVED,
        )
        self.task = Task.objects.create(
            campaign=self.campaign,
            assigned_employee=self.employee,
            title="Prepare Content",
            description="Create the campaign content.",
            due_date="2026-10-15",
        )

    def test_administrator_can_create_task_for_approved_campaign(self):
        self.client.force_login(self.staff_user)
        response = self.client.post(reverse("administrator_task_create", args=(self.campaign.pk,)), {
            "title": "Schedule Posts",
            "description": "Prepare the publishing schedule.",
            "due_date": "2026-10-20",
            "assigned_employee": self.employee.pk,
        })
        self.assertRedirects(response, reverse("administrator_campaign_detail", args=(self.campaign.pk,)))
        task = Task.objects.get(title="Schedule Posts")
        self.assertEqual(task.campaign, self.campaign)
        self.assertEqual(task.assigned_employee, self.employee)
        self.assertEqual(task.status, Task.Status.PENDING)

    def test_non_administrator_cannot_create_task(self):
        self.client.force_login(self.client_user)
        response = self.client.get(reverse("administrator_task_create", args=(self.campaign.pk,)))
        self.assertEqual(response.status_code, 302)

    def test_employee_sees_only_own_assigned_tasks(self):
        Task.objects.create(
            campaign=self.campaign,
            assigned_employee=self.other_employee,
            title="Private Employee Task",
            due_date="2026-10-16",
        )
        self.client.force_login(self.employee_user)
        response = self.client.get(reverse("employee_task_list"))
        self.assertContains(response, "Prepare Content")
        self.assertNotContains(response, "Private Employee Task")

    def test_employee_cannot_view_another_employees_task(self):
        self.client.force_login(self.other_employee_user)
        response = self.client.get(reverse("employee_task_detail", args=(self.task.pk,)))
        self.assertEqual(response.status_code, 404)

    def test_employee_can_change_own_task_to_in_progress(self):
        self.client.force_login(self.employee_user)
        response = self.client.post(reverse("employee_task_status_update", args=(self.task.pk,)), {
            "status": Task.Status.IN_PROGRESS,
        })
        self.assertRedirects(response, reverse("employee_task_detail", args=(self.task.pk,)))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.IN_PROGRESS)

    def test_employee_can_mark_own_task_completed(self):
        self.client.force_login(self.employee_user)
        self.client.post(reverse("employee_task_status_update", args=(self.task.pk,)), {
            "status": Task.Status.COMPLETED,
        })
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.COMPLETED)

    def test_employee_cannot_modify_another_employees_task(self):
        self.client.force_login(self.other_employee_user)
        response = self.client.post(reverse("employee_task_status_update", args=(self.task.pk,)), {
            "status": Task.Status.COMPLETED,
        })
        self.assertEqual(response.status_code, 404)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.PENDING)

    def test_client_cannot_access_employee_task_pages(self):
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.get(reverse("employee_task_list")).status_code, 302)
        self.assertEqual(self.client.get(reverse("employee_task_detail", args=(self.task.pk,))).status_code, 302)

    def test_anonymous_user_is_redirected_to_employee_login(self):
        response = self.client.get(reverse("employee_task_list"))
        self.assertRedirects(response, f'{reverse("employee_login")}?next={reverse("employee_task_list")}')

    def test_status_change_requires_post(self):
        self.client.force_login(self.employee_user)
        response = self.client.get(reverse("employee_task_status_update", args=(self.task.pk,)))
        self.assertEqual(response.status_code, 405)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.PENDING)

    def test_client_sees_only_completed_task_count(self):
        self.task.status = Task.Status.COMPLETED
        self.task.save(update_fields=("status",))
        Task.objects.create(
            campaign=self.campaign,
            assigned_employee=self.employee,
            title="Internal Task Title",
            description="Internal task description",
            due_date="2026-10-17",
        )
        self.client.force_login(self.client_user)
        response = self.client.get(reverse("client_campaign_detail", args=(self.campaign.pk,)))
        self.assertContains(response, "Tasks Completed:")
        self.assertContains(response, "1 / 2")
        self.assertNotContains(response, "Internal Task Title")


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

    def test_inactive_employee_is_not_offered_for_assignment(self):
        self.employee_user.is_active = False
        self.employee_user.save(update_fields=("is_active",))
        campaign = Campaign.objects.create(
            client=self.client_user,
            name="Approved Assignment",
            description="Ready for work",
            status=Campaign.Status.APPROVED,
        )
        response = self.client.get(reverse("administrator_campaign_detail", args=(campaign.pk,)))
        self.assertNotContains(response, f'value="{self.employee.pk}"')
