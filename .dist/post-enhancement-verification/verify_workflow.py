"""One-off verification against an in-memory database and temporary uploads."""
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "campaign_planner.settings")
from django.conf import settings

settings.DATABASES["default"]["NAME"] = ":memory:"
assert settings.DATABASES["default"]["NAME"] == ":memory:"
media = tempfile.TemporaryDirectory(prefix="planner-post-enhancement-")
settings.MEDIA_ROOT = media.name
settings.ALLOWED_HOSTS = ["testserver"]
import django

django.setup()
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client
from django.test.utils import setup_test_environment
from django.urls import reverse
from campaigns.models import Campaign, Deliverable, EmployeeProfile, Task

setup_test_environment()
call_command("migrate", verbosity=0, interactive=False)
snapshots = {}
snapshot_dir = OUT / "snapshots"
snapshot_dir.mkdir(exist_ok=True)
password = "Mountain!Cedar8392"


def page(browser, name, *args, key=None):
    url = reverse(name, args=args)
    response = browser.get(url)
    assert response.status_code == 200, (name, response.status_code)
    filename = (key or name) + ".html"
    (snapshot_dir / filename).write_bytes(response.content)
    snapshots[key or name] = {"url": url, "file": "snapshots/" + filename}
    return response


def post(browser, name, data=None, args=(), target=None):
    response = browser.post(reverse(name, args=args), {
        **(data or {}), "csrfmiddlewaretoken": browser.cookies["csrftoken"].value,
    })
    assert response.status_code == 302, (name, response.status_code, response.content.decode()[-6000:])
    if target:
        assert response.url == target, (name, response.url, target)
    return response


def login(browser, name, username):
    page(browser, name)
    post(browser, name, {"username": username, "password": password})
    assert browser.session.get("_auth_user_id") == str(User.objects.get(username=username).pk)


try:
    owner_browser, admin_browser, employee_browser = [Client(enforce_csrf_checks=True) for _ in range(3)]
    page(owner_browser, "home")
    page(owner_browser, "register")
    post(owner_browser, "register", {
        "username": "rehearsalclient", "email": "rehearsalclient@example.com",
        "password1": password, "password2": password,
    }, target=reverse("client_dashboard"))
    owner = User.objects.get(username="rehearsalclient")
    page(owner_browser, "client_dashboard")
    post(owner_browser, "logout", target=reverse("home"))
    login(owner_browser, "login", owner.username)
    page(owner_browser, "client_profile")
    post(owner_browser, "client_profile", {
        "first_name": "Rehearsal", "last_name": "Client", "email": owner.email,
    })
    for name in ("client_campaign_list", "client_campaign_tracking", "client_deliverables", "client_reports"):
        page(owner_browser, name, key=name + "_empty")
    page(owner_browser, "campaign_request")
    requirements = {"platforms": "Instagram, Facebook, YouTube", "campaign_goal": "Build launch awareness.\nGenerate 25 product enquiries."}
    post(owner_browser, "campaign_request", {
        "name": "Post Enhancement Rehearsal", "description": "Launch a local product with connected campaign records.",
        "campaign_type": "Social Media", "target_audience": "Local shoppers", "budget": "5000.00",
        "start_date": "2026-10-01", "end_date": "2026-10-31", **requirements,
    }, target=reverse("client_campaign_list"))
    campaign = Campaign.objects.get(client=owner)
    assert campaign.status == "pending" and campaign.progress_percentage == 0
    assert all(getattr(campaign, name) == value for name, value in requirements.items())

    User.objects.create_user("rehearsaladmin", password=password, is_staff=True)
    login(admin_browser, "administrator_login", "rehearsaladmin")
    dashboard = page(admin_browser, "administrator_dashboard")
    assert dashboard.context["total_campaigns"] == dashboard.context["pending_campaigns"] == 1
    detail = page(admin_browser, "administrator_campaign_detail", campaign.pk)
    assert requirements["platforms"] in detail.content.decode() and "Generate 25 product enquiries." in detail.content.decode()
    post(admin_browser, "administrator_campaign_decision", args=(campaign.pk, "approve"))
    page(admin_browser, "administrator_employee_create")
    post(admin_browser, "administrator_employee_create", {
        "username": "rehearsalemployee", "first_name": "Rehearsal", "last_name": "Employee",
        "email": "rehearsalemployee@example.com", "job_title": "Marketing Executive", "phone": "1234567890",
        "password1": password, "password2": password,
    })
    employee = EmployeeProfile.objects.get(user__username="rehearsalemployee")
    post(admin_browser, "administrator_campaign_detail", {
        "assignment-assigned_employee": employee.pk, "update_assignment": "1",
    }, args=(campaign.pk,))
    page(admin_browser, "administrator_task_create", campaign.pk)
    post(admin_browser, "administrator_task_create", {
        "title": "Prepare launch content", "description": "Create the final creative for this campaign.",
        "due_date": "2026-10-15", "assigned_employee": employee.pk,
    }, args=(campaign.pk,))
    task = campaign.tasks.get()
    assert task.assigned_employee == employee

    login(employee_browser, "employee_login", employee.user.username)
    dashboard = page(employee_browser, "employee_dashboard")
    assert list(dashboard.context["campaigns"]) == [campaign]
    detail = page(employee_browser, "employee_campaign_detail", campaign.pk)
    assert requirements["platforms"] in detail.content.decode() and "Build launch awareness." in detail.content.decode()
    page(employee_browser, "employee_task_list")
    page(employee_browser, "employee_task_detail", task.pk)
    for status in ("in_progress", "completed"):
        post(employee_browser, "employee_task_status_update", {"status": status}, args=(task.pk,))
        task.refresh_from_db()
        assert task.status == status and task.campaign_id == campaign.pk
    post(employee_browser, "employee_campaign_detail", {"status": "in_progress", "progress_percentage": 65}, args=(campaign.pk,))
    selector = page(employee_browser, "employee_deliverable_campaigns")
    assert list(selector.context["campaigns"]) == [campaign]
    upload_url = reverse("employee_deliverable_upload", args=(campaign.pk,))
    assert upload_url in selector.content.decode()
    page(employee_browser, "employee_deliverable_upload", campaign.pk)
    for title in ("Approved creative", "Rejected creative"):
        post(employee_browser, "employee_deliverable_upload", {
            "title": title, "description": "Creative ready for review.",
            "uploaded_file": SimpleUploadedFile("rehearsal.png", bytes.fromhex(
                "89504e470d0a1a0a0000000d4948445200000001000000010804000000b51c0c020000000b4944415478da6364f80f00010501012718e3660000000049454e44ae426082"
            ), content_type="image/png"),
        }, args=(campaign.pk,))
    assert campaign.deliverables.count() == 2
    assert all(d.uploaded_by == employee and d.approval_status == "pending" for d in campaign.deliverables.all())

    tracking = page(owner_browser, "client_campaign_tracking")
    assert "65%" in tracking.content.decode() and "1 / 1" in tracking.content.decode()
    review = page(owner_browser, "client_deliverables", key="client_deliverables_pending")
    for deliverable in campaign.deliverables.all():
        assert deliverable.title in review.content.decode()
        response = owner_browser.get(deliverable.uploaded_file.url)
        assert response.status_code == 200
        assert b"".join(response.streaming_content) == deliverable.uploaded_file.read()
        response.close()
        deliverable.uploaded_file.close()
        decision = "approve" if deliverable.title.startswith("Approved") else "reject"
        post(owner_browser, "client_deliverable_decision", {"return_to": "deliverables"}, args=(campaign.pk, deliverable.pk, decision))
    for browser, role in ((owner_browser, "client"), (admin_browser, "administrator")):
        report = page(browser, role + "_campaign_report", campaign.pk)
        assert report.context["task_summary"] == {"total": 1, "pending": 0, "in_progress": 0, "completed": 1}
        assert report.context["deliverable_summary"] == {"total": 2, "pending": 0, "approved": 1, "rejected": 1}
        assert report.context["task_completion_percentage"] == 100
        assert report.context["campaign"].progress_percentage == 65
        assert all(getattr(report.context["campaign"], name) == value for name, value in requirements.items())
        assert all(t.campaign_id == campaign.pk for t in report.context["tasks"])
        assert all(d.campaign_id == campaign.pk for d in report.context["deliverables"])
        assert "window.print()" in report.content.decode()

    for browser, pages in (
        (owner_browser, (("client_dashboard", ()), ("client_campaign_list", ()), ("client_deliverables", ()), ("client_reports", ()), ("client_campaign_detail", (campaign.pk,)), ("client_profile", ()))),
        (admin_browser, (("administrator_dashboard", ()), ("administrator_campaign_detail", (campaign.pk,)), ("administrator_employee_list", ()), ("administrator_employee_edit", (employee.pk,)))),
        (employee_browser, (("employee_dashboard", ()), ("employee_campaign_detail", (campaign.pk,)), ("employee_task_list", ()), ("employee_task_detail", (task.pk,)), ("employee_profile", ()))),
    ):
        for name, args in pages:
            page(browser, name, *args)
    other_user = User.objects.create_user("unassignedemployee")
    other_employee = EmployeeProfile.objects.create(user=other_user)
    campaign.assigned_employee = other_employee
    campaign.save(update_fields=["assigned_employee"])
    empty = page(employee_browser, "employee_deliverable_campaigns", key="employee_deliverable_campaigns_empty")
    assert "No campaigns are currently available" in empty.content.decode()
    assert employee_browser.get(upload_url).status_code == 404
    response = employee_browser.post(upload_url, {"title": "Forbidden", "csrfmiddlewaretoken": employee_browser.cookies["csrftoken"].value})
    assert response.status_code == 404 and campaign.deliverables.count() == 2
    for browser in (owner_browser, admin_browser, employee_browser):
        post(browser, "logout", target=reverse("home"))
        assert "_auth_user_id" not in browser.session
    (OUT / "snapshot-manifest.json").write_text(json.dumps(snapshots, indent=2), encoding="utf-8")
    result = {"result": "PASS", "database": "in-memory", "csrf_enforced": True, "snapshots": len(snapshots),
              "workflow": "registration/login -> request with requirements -> admin approval/employee creation/assignment/task -> employee task completion/progress/selector/upload -> client file access/approve/reject/report -> role logout",
              "campaign_progress": 65, "task_completion": 100, "deliverables": {"approved": 1, "rejected": 1},
              "reassignment_upload_revocation": "PASS"}
    (OUT / "workflow-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
finally:
    media.cleanup()
