from django.contrib import admin

from .models import Campaign, Deliverable, EmployeeProfile, Task


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "job_title", "phone")
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email")


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "client", "assigned_employee", "progress_percentage", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("name", "client__username", "client__email")


@admin.register(Deliverable)
class DeliverableAdmin(admin.ModelAdmin):
    list_display = ("title", "campaign", "uploaded_by", "approval_status", "uploaded_at")
    list_filter = ("approval_status", "uploaded_at")
    search_fields = ("title", "campaign__name", "uploaded_by__user__username")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "campaign", "assigned_employee", "due_date", "status")
    list_filter = ("status", "due_date")
    search_fields = ("title", "campaign__name", "assigned_employee__user__username")
