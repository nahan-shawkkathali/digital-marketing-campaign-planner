from django.contrib import admin

from .models import Campaign, EmployeeProfile


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "job_title", "phone")
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email")


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "client", "assigned_employee", "progress_percentage", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("name", "client__username", "client__email")
