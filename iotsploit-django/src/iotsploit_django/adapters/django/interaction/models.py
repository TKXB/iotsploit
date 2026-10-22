"""
Durable records for interactive plugin execution.

The database is the source of truth: an execution and its pending question
survive a worker restart, a Flutter reload, and a dropped WebSocket. See
``docs/interactive_exploit_plugin_plan.md`` Appendix A.4.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ExecutionStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    WAITING_INPUT = "waiting_input", "Waiting for input"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    # Reached only by the stranded-execution sweep: the worker went away while
    # a prompt was open. Distinct from FAILED so operators can tell
    # infrastructure loss from plugin failure.
    EXPIRED = "expired", "Expired"


class RequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ANSWERED = "answered", "Answered"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


TERMINAL_EXECUTION_STATUSES = frozenset({
    ExecutionStatus.COMPLETED,
    ExecutionStatus.FAILED,
    ExecutionStatus.CANCELLED,
    ExecutionStatus.EXPIRED,
})


class PluginExecution(models.Model):
    """One run of one plugin, addressable independently of Celery."""

    execution_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plugin_name = models.CharField(max_length=200, db_index=True)
    plugin_version = models.CharField(max_length=64, blank=True)

    # A snapshot, not a foreign key: TargetManager.get_current_target() is a
    # mutable process global, and a run must record what it actually touched.
    target_snapshot = models.JSONField(null=True, blank=True)
    parameters = models.JSONField(default=dict, blank=True)

    # Nullable so the models do not block on the authentication prerequisite.
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="plugin_executions",
    )

    status = models.CharField(
        max_length=16,
        choices=ExecutionStatus.choices,
        default=ExecutionStatus.QUEUED,
        db_index=True,
    )
    celery_task_id = models.CharField(max_length=128, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    result = models.JSONField(null=True, blank=True)
    error = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[Execution:{self.execution_id} {self.plugin_name} {self.status}]"

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_EXECUTION_STATUSES

    def pending_request(self) -> "InputRequest | None":
        return self.input_requests.filter(status=RequestStatus.PENDING).first()


class InputRequest(models.Model):
    """A question raised by a running plugin, and its answer.

    At most one request per execution is ``pending`` at a time, enforced by a
    partial unique constraint rather than by convention.
    """

    request_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution = models.ForeignKey(
        PluginExecution,
        related_name="input_requests",
        on_delete=models.CASCADE,
    )

    kind = models.CharField(max_length=20)
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    validation = models.JSONField(default=dict, blank=True)
    default = models.JSONField(null=True, blank=True)

    status = models.CharField(
        max_length=12,
        choices=RequestStatus.choices,
        default=RequestStatus.PENDING,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    answered_at = models.DateTimeField(null=True, blank=True)
    answered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="answered_input_requests",
    )
    # No v1 prompt type carries a credential, so the answer is stored plainly.
    # A `secret` kind must not reuse this path -- see plan decision 7.
    answer_value = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["execution"],
                condition=models.Q(status="pending"),
                name="one_pending_request_per_execution",
            )
        ]

    def __str__(self):
        return f"[InputRequest:{self.request_id} {self.kind} {self.status}]"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at
