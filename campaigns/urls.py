from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import AdministratorLoginForm, ClientLoginForm, EmployeeLoginForm

urlpatterns = [
    path('', views.home, name='home'),
    path('client/register/', views.register, name='register'),
    path('client/login/', auth_views.LoginView.as_view(
        template_name='campaigns/login.html',
        authentication_form=ClientLoginForm,
        redirect_authenticated_user=True,
        next_page='client_dashboard',
    ), name='login'),
    path('client/logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),
    path('client/dashboard/', views.client_dashboard, name='client_dashboard'),
    path('administrator/login/', auth_views.LoginView.as_view(
        template_name='campaigns/administrator_login.html',
        authentication_form=AdministratorLoginForm,
        redirect_authenticated_user=False,
        next_page='administrator_dashboard',
    ), name='administrator_login'),
    path('administrator/dashboard/', views.administrator_dashboard, name='administrator_dashboard'),
    path('administrator/campaigns/<int:campaign_id>/', views.administrator_campaign_detail, name='administrator_campaign_detail'),
    path('administrator/campaigns/<int:campaign_id>/<str:decision>/', views.administrator_campaign_decision, name='administrator_campaign_decision'),
    path('administrator/employees/', views.administrator_employee_list, name='administrator_employee_list'),
    path('administrator/employees/create/', views.administrator_employee_create, name='administrator_employee_create'),
    path('administrator/employees/<int:employee_id>/edit/', views.administrator_employee_edit, name='administrator_employee_edit'),
    path('employee/login/', auth_views.LoginView.as_view(
        template_name='campaigns/employee_login.html',
        authentication_form=EmployeeLoginForm,
        redirect_authenticated_user=False,
        next_page='employee_dashboard',
    ), name='employee_login'),
    path('employee/dashboard/', views.employee_dashboard, name='employee_dashboard'),
    path('employee/campaigns/<int:campaign_id>/', views.employee_campaign_detail, name='employee_campaign_detail'),
    path('employee/profile/', views.employee_profile, name='employee_profile'),
]
