from django.db import models
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError

from .file_validation import ALLOWED_EXTENSIONS, VIDEO_TYPES, validate_deliverable_content


class ClientProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="client_profile",
    )
    company_name = models.CharField("Company / Business Name", max_length=255, blank=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


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
    campaign_type = models.CharField(max_length=100, blank=True)
    product_service_name = models.CharField("Product / Service Name", max_length=255, blank=True)
    target_audience = models.CharField(max_length=255, blank=True)
    platforms = models.CharField(max_length=255, blank=True)
    campaign_goal = models.TextField(blank=True)
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
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.name


class DeliverableQuerySet(models.QuerySet):
    def with_current_version(self):
        newer_versions = self.model.objects.filter(
            campaign_id=models.OuterRef("campaign_id"), version__gt=models.OuterRef("version"),
        ).filter(models.Q(original_id=models.OuterRef("pk")) |
                 models.Q(original_id=models.OuterRef("original_id")))
        return self.annotate(has_newer_version=models.Exists(newer_versions))


class Deliverable(models.Model):
    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", "Pending Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CHANGES_REQUESTED = "changes_requested", "Changes Requested"

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="deliverables",
    )
    uploaded_by = models.ForeignKey(
        EmployeeProfile,
        on_delete=models.CASCADE,
        related_name="uploaded_deliverables",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    uploaded_file = models.FileField(
        upload_to="deliverables/%Y/%m/%d/",
        validators=[FileExtensionValidator(ALLOWED_EXTENSIONS), validate_deliverable_content],
    )
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    original = models.ForeignKey(
        "self", on_delete=models.PROTECT, related_name="revisions", null=True, blank=True,
    )
    version = models.PositiveIntegerField(default=1)

    objects = DeliverableQuerySet.as_manager()

    class Meta:
        ordering = ("-uploaded_at",)
        constraints = [
            models.UniqueConstraint(fields=("original", "version"), name="unique_deliverable_revision"),
            models.CheckConstraint(
                condition=models.Q(original__isnull=True, version=1) |
                          models.Q(original__isnull=False, version__gte=2),
                name="deliverable_version_shape",
            ),
        ]

    def clean(self):
        super().clean()
        if self.original_id:
            if self.original.original_id or self.original_id == self.pk:
                raise ValidationError({"original": "Revisions must link to the original deliverable."})
            if self.original.campaign_id != self.campaign_id:
                raise ValidationError({"original": "Revisions must belong to the same campaign."})

    def revision_history(self):
        original_id = self.original_id or self.pk
        return Deliverable.objects.filter(
            models.Q(pk=original_id) | models.Q(original_id=original_id),
        ).order_by("version", "pk")

    @property
    def video_content_type(self):
        extension = self.uploaded_file.name.rsplit(".", 1)[-1].lower() if self.uploaded_file else ""
        return VIDEO_TYPES.get(extension, "")

    @property
    def is_current(self):
        if hasattr(self, "has_newer_version"):
            return not self.has_newer_version
        return not Deliverable.objects.filter(
            original_id=self.original_id or self.pk, version__gt=self.version,
        ).exists()

    def __str__(self):
        return self.title


class DeliverableMessage(models.Model):
    class Kind(models.TextChoices):
        COMMENT = "comment", "Message"
        CHANGES_REQUESTED = "changes_requested", "Changes Requested"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    deliverable = models.ForeignKey(Deliverable, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="deliverable_messages")
    body = models.TextField()
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.COMMENT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")


class Task(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    assigned_employee = models.ForeignKey(
        EmployeeProfile,
        on_delete=models.SET_NULL,
        related_name="assigned_tasks",
        null=True,
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("due_date", "created_at")

    def __str__(self):
        return self.title
