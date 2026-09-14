from django.contrib.auth import login
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST, require_http_methods, require_safe

from .forms import (
    AdministratorEmployeeForm,
    AdministratorTaskForm,
    CampaignAssignmentForm,
    CampaignRequestForm,
    CampaignStatusForm,
    ClientProfileForm,
    ClientRegistrationForm,
    EmployeeCampaignProgressForm,
    EmployeeCreationForm,
    EmployeeProfileForm,
    EmployeeTaskStatusForm,
    DeliverableUploadForm,
)
from .models import Campaign, Deliverable, EmployeeProfile, Task
from .reports import campaign_report_context


def staff_required(view_func):
    return user_passes_test(
        lambda user: user.is_authenticated and (user.is_staff or user.is_superuser),
        login_url="administrator_login",
    )(view_func)


def employee_required(view_func):
    return user_passes_test(
        lambda user: user.is_authenticated and hasattr(user, "employee_profile"),
        login_url="employee_login",
    )(view_func)


def is_client(user):
    return (
        user.is_authenticated
        and not user.is_staff
        and not user.is_superuser
        and not hasattr(user, "employee_profile")
    )


def client_required(view_func):
    return user_passes_test(
        is_client,
        login_url="login",
    )(view_func)


def home(request):
    return render(request, 'campaigns/home.html')


def register(request):
    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            return redirect("administrator_dashboard")
        if hasattr(request.user, "employee_profile"):
            return redirect("employee_dashboard")
        return redirect("client_dashboard")
    form = ClientRegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("client_dashboard")
    return render(request, "campaigns/register.html", {"form": form})


@client_required
def client_dashboard(request):
    return render(request, "campaigns/client_dashboard.html")


@client_required
def client_profile(request):
    form = ClientProfileForm(request.POST if request.method == "POST" else None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your profile was updated.")
        return redirect("client_profile")
    return render(request, "campaigns/client_profile.html", {"form": form})


@client_required
def campaign_request(request):
    form = CampaignRequestForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        campaign = form.save(commit=False)
        campaign.client = request.user
        campaign.status = Campaign.Status.PENDING
        campaign.save()
        messages.success(request, f'Campaign request "{campaign.name}" submitted successfully.')
        return redirect("client_campaign_list")
    return render(request, "campaigns/campaign_request.html", {"form": form})


def _client_campaigns(user):
    return Campaign.objects.filter(client=user).select_related("assigned_employee__user")


def _with_task_counts(campaigns):
    # Distinct counts stay accurate when a list also joins deliverables.
    return campaigns.annotate(
        total_tasks=Count("tasks", distinct=True),
        completed_tasks=Count("tasks", filter=Q(tasks__status=Task.Status.COMPLETED), distinct=True),
    )


def _deliverable_filter(value):
    return value if value in Deliverable.ApprovalStatus.values else "all"


@client_required
@require_GET
def client_campaign_list(request, tracking=False):
    campaigns = _client_campaigns(request.user)
    if tracking:
        campaigns = _with_task_counts(campaigns)
    return render(request, "campaigns/client_campaign_list.html", {
        "campaigns": campaigns, "tracking": tracking,
    })


@client_required
@require_GET
def client_deliverables(request):
    status = _deliverable_filter(request.GET.get("status"))
    deliverables = Deliverable.objects.filter(campaign__client=request.user).select_related(
        "campaign", "uploaded_by__user",
    )
    if status != "all":
        deliverables = deliverables.filter(approval_status=status)
    return render(request, "campaigns/client_deliverables.html", {
        "deliverables": deliverables,
        "selected_status": status,
        "status_filters": (("all", "All"), ("pending", "Pending"),
                           ("approved", "Approved"), ("rejected", "Rejected")),
    })


@client_required
@require_GET
def client_reports(request):
    campaigns = _with_task_counts(_client_campaigns(request.user)).annotate(
        total_deliverables=Count("deliverables", distinct=True),
        approved_deliverables=Count(
            "deliverables", filter=Q(deliverables__approval_status=Deliverable.ApprovalStatus.APPROVED),
            distinct=True,
        ),
        pending_deliverables=Count(
            "deliverables", filter=Q(deliverables__approval_status=Deliverable.ApprovalStatus.PENDING),
            distinct=True,
        ),
        rejected_deliverables=Count(
            "deliverables", filter=Q(deliverables__approval_status=Deliverable.ApprovalStatus.REJECTED),
            distinct=True,
        ),
    )
    return render(request, "campaigns/client_reports.html", {"campaigns": campaigns})


@client_required
def client_campaign_detail(request, campaign_id):
    campaign = get_object_or_404(
        Campaign.objects.select_related("assigned_employee__user"),
        pk=campaign_id,
        client=request.user,
    )
    deliverables = campaign.deliverables.select_related("uploaded_by__user")
    total_tasks = campaign.tasks.count()
    completed_tasks = campaign.tasks.filter(status=Task.Status.COMPLETED).count()
    return render(request, "campaigns/client_campaign_detail.html", {
        "campaign": campaign,
        "deliverables": deliverables,
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
    })


@client_required
@require_POST
def client_deliverable_decision(request, campaign_id, deliverable_id, decision):
    deliverables = Deliverable.objects.filter(
        pk=deliverable_id,
        campaign_id=campaign_id,
        campaign__client=request.user,
    )
    deliverable = get_object_or_404(deliverables)
    decisions = {
        "approve": Deliverable.ApprovalStatus.APPROVED,
        "reject": Deliverable.ApprovalStatus.REJECTED,
    }
    if decision not in decisions:
        messages.error(request, "Invalid deliverable decision.")
    elif not deliverables.filter(approval_status=Deliverable.ApprovalStatus.PENDING).update(
        approval_status=decisions[decision],
    ):
        # Check and update together so a stale review cannot overwrite a decision.
        messages.error(request, "This deliverable has already been reviewed.")
    else:
        deliverable.approval_status = decisions[decision]
        messages.success(request, f'Deliverable "{deliverable.title}" was {deliverable.get_approval_status_display().lower()}.')
    if request.POST.get("return_to") == "deliverables":
        destination = reverse("client_deliverables")
        status = _deliverable_filter(request.POST.get("status"))
        if status != "all":
            destination += f"?status={status}"
        return redirect(destination)
    return redirect("client_campaign_detail", campaign_id=campaign_id)


@login_required(login_url="login")
@require_safe
def deliverable_file(request, file_path):
    """Apply campaign access rules to the existing uploaded-file URLs."""
    deliverables = Deliverable.objects.filter(uploaded_file=file_path)
    if request.user.is_staff or request.user.is_superuser:
        pass
    elif hasattr(request.user, "employee_profile"):
        deliverables = deliverables.filter(
            campaign__assigned_employee=request.user.employee_profile,
        )
    else:
        deliverables = deliverables.filter(campaign__client=request.user)
    deliverable = get_object_or_404(deliverables)
    try:
        response = FileResponse(deliverable.uploaded_file.open("rb"))
    except FileNotFoundError as error:
        raise Http404("File not found.") from error
    response["Cache-Control"] = "private, no-store"
    return response


@client_required
@require_GET
def client_campaign_report(request, campaign_id):
    campaign = get_object_or_404(
        Campaign.objects.select_related("client", "assigned_employee__user"),
        pk=campaign_id,
        client=request.user,
    )
    context = campaign_report_context(campaign)
    context["campaign_detail_url_name"] = "client_campaign_detail"
    return render(request, "campaigns/campaign_report.html", context)


@staff_required
@require_GET
def administrator_campaign_report(request, campaign_id):
    campaign = get_object_or_404(
        Campaign.objects.select_related("client", "assigned_employee__user"),
        pk=campaign_id,
    )
    context = campaign_report_context(campaign)
    context["campaign_detail_url_name"] = "administrator_campaign_detail"
    return render(request, "campaigns/campaign_report.html", context)


@staff_required
def administrator_dashboard(request):
    campaigns = Campaign.objects.select_related("client", "assigned_employee__user").all()
    context = {
        "campaigns": campaigns,
        "total_campaigns": campaigns.count(),
        "pending_campaigns": campaigns.filter(status=Campaign.Status.PENDING).count(),
        "approved_campaigns": campaigns.filter(status=Campaign.Status.APPROVED).count(),
        "in_progress_campaigns": campaigns.filter(status=Campaign.Status.IN_PROGRESS).count(),
        "completed_campaigns": campaigns.filter(status=Campaign.Status.COMPLETED).count(),
        "rejected_campaigns": campaigns.filter(status=Campaign.Status.REJECTED).count(),
    }
    return render(request, "campaigns/administrator_dashboard.html", context)


@staff_required
def administrator_campaign_detail(request, campaign_id):
    campaign = get_object_or_404(Campaign.objects.select_related("client", "assigned_employee__user"), pk=campaign_id)
    status_form = CampaignStatusForm(
        request.POST if request.method == "POST" and "update_status" in request.POST else None,
        instance=campaign, prefix="status",
    )
    assignment_form = CampaignAssignmentForm(
        request.POST if request.method == "POST" and "update_assignment" in request.POST else None,
        instance=campaign, prefix="assignment",
    )
    if request.method == "POST" and "update_status" in request.POST and status_form.is_valid():
        status_form.save()
        messages.success(request, f'Campaign "{campaign.name}" status updated.')
        return redirect("administrator_campaign_detail", campaign_id=campaign.pk)
    if request.method == "POST" and "update_assignment" in request.POST and assignment_form.is_valid():
        with transaction.atomic():
            assignment_form.save()
            campaign.tasks.update(assigned_employee=campaign.assigned_employee)
        messages.success(request, f'Campaign "{campaign.name}" assignment updated.')
        return redirect("administrator_campaign_detail", campaign_id=campaign.pk)
    if request.method == "POST":
        campaign.refresh_from_db()
    return render(request, "campaigns/administrator_campaign_detail.html", {
        "campaign": campaign,
        "status_form": status_form,
        "assignment_form": assignment_form,
        "tasks": campaign.tasks.select_related("assigned_employee__user"),
    })


@staff_required
def administrator_task_create(request, campaign_id):
    campaign = get_object_or_404(
        Campaign,
        pk=campaign_id,
        status__in=(Campaign.Status.APPROVED, Campaign.Status.IN_PROGRESS),
    )
    form = AdministratorTaskForm(request.POST if request.method == "POST" else None, campaign=campaign)
    if request.method == "POST" and form.is_valid():
        task = form.save(commit=False)
        task.campaign = campaign
        task.status = Task.Status.PENDING
        task.save()
        messages.success(request, f'Task "{task.title}" created.')
        return redirect("administrator_campaign_detail", campaign_id=campaign.pk)
    return render(request, "campaigns/administrator_task_form.html", {
        "campaign": campaign,
        "form": form,
    })


@staff_required
@require_POST
def administrator_campaign_decision(request, campaign_id, decision):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    decisions = {
        "approve": Campaign.Status.APPROVED,
        "reject": Campaign.Status.REJECTED,
    }
    if decision not in decisions:
        messages.error(request, "Invalid campaign decision.")
    else:
        campaign.status = decisions[decision]
        campaign.save(update_fields=("status", "updated_at"))
        messages.success(request, f'Campaign "{campaign.name}" was {campaign.get_status_display().lower()}.')
    return redirect("administrator_campaign_detail", campaign_id=campaign.pk)


@staff_required
def administrator_employee_list(request):
    employees = EmployeeProfile.objects.select_related("user").all().order_by("user__first_name", "user__username")
    return render(request, "campaigns/administrator_employee_list.html", {"employees": employees})


@staff_required
def administrator_employee_create(request):
    form = EmployeeCreationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f'Employee account for "{user.username}" created.')
        return redirect("administrator_employee_list")
    return render(request, "campaigns/administrator_employee_form.html", {"form": form, "creating": True})


@staff_required
def administrator_employee_edit(request, employee_id):
    employee = get_object_or_404(EmployeeProfile.objects.select_related("user"), pk=employee_id)
    form = AdministratorEmployeeForm(request.POST if request.method == "POST" else None, instance=employee)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Employee account updated.")
        return redirect("administrator_employee_list")
    return render(request, "campaigns/administrator_employee_form.html", {"form": form, "employee": employee})


@employee_required
def employee_dashboard(request):
    campaigns = Campaign.objects.filter(assigned_employee=request.user.employee_profile).select_related("client")
    return render(request, "campaigns/employee_dashboard.html", {"campaigns": campaigns})


@employee_required
@require_GET
def employee_deliverable_campaigns(request):
    campaigns = Campaign.objects.filter(
        assigned_employee=request.user.employee_profile,
    ).exclude(status__in=(Campaign.Status.PENDING, Campaign.Status.REJECTED)).select_related("client")
    return render(request, "campaigns/employee_deliverable_campaigns.html", {"campaigns": campaigns})


@employee_required
def employee_task_list(request):
    tasks = Task.objects.filter(
        assigned_employee=request.user.employee_profile,
        campaign__assigned_employee=request.user.employee_profile,
    ).select_related("campaign")
    return render(request, "campaigns/employee_task_list.html", {"tasks": tasks})


@employee_required
def employee_task_detail(request, task_id):
    task = get_object_or_404(
        Task.objects.select_related("campaign", "assigned_employee__user"),
        pk=task_id,
        assigned_employee=request.user.employee_profile,
        campaign__assigned_employee=request.user.employee_profile,
    )
    return render(request, "campaigns/employee_task_detail.html", {
        "task": task,
        "status_form": EmployeeTaskStatusForm(instance=task),
    })


@employee_required
@require_POST
def employee_task_status_update(request, task_id):
    task = get_object_or_404(
        Task,
        pk=task_id,
        assigned_employee=request.user.employee_profile,
        campaign__assigned_employee=request.user.employee_profile,
    )
    form = EmployeeTaskStatusForm(request.POST, instance=task)
    if task.campaign.status in (Campaign.Status.PENDING, Campaign.Status.REJECTED):
        messages.error(request, "This campaign must be approved before work can be updated.")
    elif form.is_valid():
        form.save()
        messages.success(request, "Task status updated.")
    else:
        messages.error(request, "Please select a valid task status.")
    return redirect("employee_task_detail", task_id=task.pk)


@employee_required
def employee_campaign_detail(request, campaign_id):
    campaign = get_object_or_404(
        Campaign.objects.select_related("client"),
        pk=campaign_id,
        assigned_employee=request.user.employee_profile,
    )
    form = EmployeeCampaignProgressForm(request.POST if request.method == "POST" else None, instance=campaign)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Campaign progress updated.")
        return redirect("employee_campaign_detail", campaign_id=campaign.pk)
    if request.method == "POST":
        campaign.refresh_from_db()
    return render(request, "campaigns/employee_campaign_detail.html", {
        "campaign": campaign,
        "deliverables": campaign.deliverables.select_related("uploaded_by__user"),
        "progress_form": form,
    })


@employee_required
@require_http_methods(["GET", "POST"])
def employee_deliverable_upload(request, campaign_id):
    campaign = get_object_or_404(
        Campaign,
        pk=campaign_id,
        assigned_employee=request.user.employee_profile,
    )
    form = DeliverableUploadForm(request.POST if request.method == "POST" else None, request.FILES or None)
    if request.method == "POST" and campaign.status in (Campaign.Status.PENDING, Campaign.Status.REJECTED):
        form.add_error(None, "This campaign must be approved before work can be updated.")
    if request.method == "POST" and form.is_valid():
        deliverable = form.save(commit=False)
        deliverable.campaign = campaign
        deliverable.uploaded_by = request.user.employee_profile
        deliverable.save()
        messages.success(request, f'Deliverable "{deliverable.title}" uploaded successfully.')
        return redirect("employee_campaign_detail", campaign_id=campaign.pk)
    return render(request, "campaigns/employee_deliverable_upload.html", {
        "campaign": campaign,
        "form": form,
    })


@employee_required
def employee_profile(request):
    profile = request.user.employee_profile
    form = EmployeeProfileForm(request.POST if request.method == "POST" else None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your profile was updated.")
        return redirect("employee_profile")
    return render(request, "campaigns/employee_profile.html", {"form": form})
