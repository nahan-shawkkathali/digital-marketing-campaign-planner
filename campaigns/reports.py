from django.db.models import Count, Q
from django.utils import timezone

from .models import Deliverable, Task


def campaign_report_context(campaign):
    """Build a live report from an already permission-checked campaign."""
    tasks = campaign.tasks.select_related("assigned_employee__user")
    deliverables = campaign.deliverables.with_current_version().select_related("uploaded_by__user")
    current_deliverables = deliverables.filter(has_newer_version=False)
    task_summary = tasks.aggregate(
        total=Count("pk"),
        pending=Count("pk", filter=Q(status=Task.Status.PENDING)),
        in_progress=Count("pk", filter=Q(status=Task.Status.IN_PROGRESS)),
        completed=Count("pk", filter=Q(status=Task.Status.COMPLETED)),
    )
    deliverable_summary = current_deliverables.aggregate(
        total=Count("pk"),
        pending=Count("pk", filter=Q(approval_status=Deliverable.ApprovalStatus.PENDING)),
        approved=Count("pk", filter=Q(approval_status=Deliverable.ApprovalStatus.APPROVED)),
        rejected=Count("pk", filter=Q(approval_status=Deliverable.ApprovalStatus.REJECTED)),
    )
    total_tasks = task_summary["total"]
    task_completion_percentage = (
        round(task_summary["completed"] / total_tasks * 100, 1)
        if total_tasks else 0
    )
    return {
        "campaign": campaign,
        "tasks": tasks,
        "deliverables": deliverables,
        "task_summary": task_summary,
        "deliverable_summary": deliverable_summary,
        "changes_requested_count": current_deliverables.filter(approval_status=Deliverable.ApprovalStatus.CHANGES_REQUESTED).count(),
        "total_versions": deliverables.count(),
        "revision_count": deliverables.filter(original__isnull=False).count(),
        "task_completion_percentage": task_completion_percentage,
        "generated_at": timezone.now(),
    }
