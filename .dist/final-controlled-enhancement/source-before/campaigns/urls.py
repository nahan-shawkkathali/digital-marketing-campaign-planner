from urllib.parse import unquote, urlsplit

from django.contrib.auth import views as auth_views
from django.urls import Resolver404, path, resolve, reverse_lazy

from . import views
from .forms import AdministratorLoginForm, ClientLoginForm, EmployeeLoginForm


class RoleLoginView(auth_views.LoginView):
    default_redirect_name = "home"

    def get_default_redirect_url(self):
        if self.request.user.is_staff or self.request.user.is_superuser:
            return reverse_lazy("administrator_dashboard")
        if hasattr(self.request.user, "employee_profile"):
            return reverse_lazy("employee_dashboard")
        return reverse_lazy(self.default_redirect_name)

    def get_redirect_url(self):
        destination = super().get_redirect_url()
        if not destination or not self.request.user.is_authenticated:
            return destination
        try:
            match = resolve(unquote(urlsplit(destination).path))
        except Resolver404:
            return ""
        name = match.url_name or ""
        if name in {
            "login", "register", "logout", "administrator_login", "employee_login",
            "administrator_campaign_decision", "client_deliverable_decision", "employee_task_status_update",
        }:
            return ""
        user = self.request.user
        role = "administrator" if user.is_staff or user.is_superuser else (
            "employee" if hasattr(user, "employee_profile") else "client"
        )
        if name in {"home", "deliverable_file"} or name.startswith(role + "_"):
            return destination
        if role == "client" and name == "campaign_request":
            return destination
        return ""


urlpatterns = [
    path('', views.home, name='home'),
    path('client/register/', views.register, name='register'),
    path('client/login/', RoleLoginView.as_view(
        template_name='campaigns/login.html',
        authentication_form=ClientLoginForm,
        redirect_authenticated_user=False,
        default_redirect_name='client_dashboard',
    ), name='login'),
    path('client/logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),
    path('client/dashboard/', views.client_dashboard, name='client_dashboard'),
    path('client/profile/', views.client_profile, name='client_profile'),
    path('client/deliverables/', views.client_deliverables, name='client_deliverables'),
    path('client/reports/', views.client_reports, name='client_reports'),
    path('client/campaigns/request/', views.campaign_request, name='campaign_request'),
    path('client/campaigns/', views.client_campaign_list, name='client_campaign_list'),
    path('client/campaigns/track/', views.client_campaign_list, {"tracking": True}, name='client_campaign_tracking'),
    path('client/campaigns/<int:campaign_id>/', views.client_campaign_detail, name='client_campaign_detail'),
    path('client/campaigns/<int:campaign_id>/report/', views.client_campaign_report, name='client_campaign_report'),
    path(
        'client/campaigns/<int:campaign_id>/deliverables/<int:deliverable_id>/<str:decision>/',
        views.client_deliverable_decision,
        name='client_deliverable_decision',
    ),
    path('administrator/login/', RoleLoginView.as_view(
        template_name='campaigns/administrator_login.html',
        authentication_form=AdministratorLoginForm,
        redirect_authenticated_user=False,
        default_redirect_name='administrator_dashboard',
    ), name='administrator_login'),
    path('administrator/dashboard/', views.administrator_dashboard, name='administrator_dashboard'),
    path('administrator/campaigns/<int:campaign_id>/', views.administrator_campaign_detail, name='administrator_campaign_detail'),
    path('administrator/campaigns/<int:campaign_id>/report/', views.administrator_campaign_report, name='administrator_campaign_report'),
    path('administrator/campaigns/<int:campaign_id>/tasks/create/', views.administrator_task_create, name='administrator_task_create'),
    path('administrator/campaigns/<int:campaign_id>/<str:decision>/', views.administrator_campaign_decision, name='administrator_campaign_decision'),
    path('administrator/employees/', views.administrator_employee_list, name='administrator_employee_list'),
    path('administrator/employees/create/', views.administrator_employee_create, name='administrator_employee_create'),
    path('administrator/employees/<int:employee_id>/edit/', views.administrator_employee_edit, name='administrator_employee_edit'),
    path('employee/login/', RoleLoginView.as_view(
        template_name='campaigns/employee_login.html',
        authentication_form=EmployeeLoginForm,
        redirect_authenticated_user=False,
        default_redirect_name='employee_dashboard',
    ), name='employee_login'),
    path('employee/dashboard/', views.employee_dashboard, name='employee_dashboard'),
    path('employee/deliverables/', views.employee_deliverable_campaigns, name='employee_deliverable_campaigns'),
    path('employee/tasks/', views.employee_task_list, name='employee_task_list'),
    path('employee/tasks/<int:task_id>/', views.employee_task_detail, name='employee_task_detail'),
    path('employee/tasks/<int:task_id>/status/', views.employee_task_status_update, name='employee_task_status_update'),
    path('employee/campaigns/<int:campaign_id>/', views.employee_campaign_detail, name='employee_campaign_detail'),
    path('employee/campaigns/<int:campaign_id>/deliverables/upload/', views.employee_deliverable_upload, name='employee_deliverable_upload'),
    path('employee/profile/', views.employee_profile, name='employee_profile'),
]
