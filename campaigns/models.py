from django.db import models
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator


class EmployeeProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee_profile",
    )
    job_title = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=30, blank=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Campaign(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="campaigns",
    )
    name = models.CharField(max_length=200)
    description = models.TextField()
    target_audience = models.CharField(max_length=255, blank=True)
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    assigned_employee = models.ForeignKey(
        EmployeeProfile,
        on_delete=models.SET_NULL,
        related_name="assigned_campaigns",
        null=True,
        blank=True,
    )
    progress_percentage = models.PositiveSmallIntegerField(
        default=0,
        validators=(MinValueValidator(0), MaxValueValidator(100)),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.name
