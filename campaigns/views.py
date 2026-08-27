from django.contrib.auth import login
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import (
    AdministratorEmployeeForm,
    CampaignAssignmentForm,
    CampaignStatusForm,
    ClientRegistrationForm,
    EmployeeCampaignProgressForm,
    EmployeeCreationForm,
    EmployeeProfileForm,
)
from .models import Campaign, EmployeeProfile


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

def home(request):
    return render(request, 'campaigns/home.html')


def register(request):
    if request.user.is_authenticated:
        return redirect("client_dashboard")
    form = ClientRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("client_dashboard")
    return render(request, "campaigns/register.html", {"form": form})


@login_required(login_url="login")
def client_dashboard(request):
    return render(request, "campaigns/client_dashboard.html")


@staff_required
def administrator_dashboard(request):
    campaigns = Campaign.objects.select_related("client", "assigned_employee__user").all()
    context = {
        "campaigns": campaigns,
        "total_campaigns": campaigns.count(),
        "pending_campaigns": campaigns.filter(status=Campaign.Status.PENDING).count(),
        "approved_campaigns": campaigns.filter(status=Campaign.Status.APPROVED).count(),
        "completed_campaigns": campaigns.filter(status=Campaign.Status.COMPLETED).count(),
    }
    return render(request, "campaigns/administrator_dashboard.html", context)


@staff_required
def administrator_campaign_detail(request, campaign_id):
    campaign = get_object_or_404(Campaign.objects.select_related("client", "assigned_employee__user"), pk=campaign_id)
    status_form = CampaignStatusForm(request.POST or None, instance=campaign, prefix="status")
    assignment_form = CampaignAssignmentForm(request.POST or None, instance=campaign, prefix="assignment")
    if request.method == "POST" and "update_status" in request.POST and status_form.is_valid():
        status_form.save()
        messages.success(request, f'Campaign "{campaign.name}" status updated.')
        return redirect("administrator_campaign_detail", campaign_id=campaign.pk)
    if request.method == "POST" and "update_assignment" in request.POST and assignment_form.is_valid():
        assignment_form.save()
        messages.success(request, f'Campaign "{campaign.name}" assignment updated.')
        return redirect("administrator_campaign_detail", campaign_id=campaign.pk)
    return render(request, "campaigns/administrator_campaign_detail.html", {
        "campaign": campaign,
        "status_form": status_form,
        "assignment_form": assignment_form,
    })


@require_POST
@staff_required
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
        messages.success(request, f'Campaign "{campaign.name}" was {decision}d.')
    return redirect("administrator_campaign_detail", campaign_id=campaign.pk)


@staff_required
def administrator_employee_list(request):
    employees = EmployeeProfile.objects.select_related("user").all().order_by("user__first_name", "user__username")
    return render(request, "campaigns/administrator_employee_list.html", {"employees": employees})


@staff_required
def administrator_employee_create(request):
    form = EmployeeCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f'Employee account for "{user.username}" created.')
        return redirect("administrator_employee_list")
    return render(request, "campaigns/administrator_employee_form.html", {"form": form, "creating": True})


@staff_required
def administrator_employee_edit(request, employee_id):
    employee = get_object_or_404(EmployeeProfile.objects.select_related("user"), pk=employee_id)
    form = AdministratorEmployeeForm(request.POST or None, instance=employee)
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
def employee_campaign_detail(request, campaign_id):
    campaign = get_object_or_404(
        Campaign.objects.select_related("client"),
        pk=campaign_id,
        assigned_employee=request.user.employee_profile,
    )
    form = EmployeeCampaignProgressForm(request.POST or None, instance=campaign)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Campaign progress updated.")
        return redirect("employee_campaign_detail", campaign_id=campaign.pk)
    return render(request, "campaigns/employee_campaign_detail.html", {"campaign": campaign, "progress_form": form})


@employee_required
def employee_profile(request):
    profile = request.user.employee_profile
    form = EmployeeProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your profile was updated.")
        return redirect("employee_profile")
    return render(request, "campaigns/employee_profile.html", {"form": form})
