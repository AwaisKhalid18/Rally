"""M7's tables: `outbox` and `notification`.

Neither carries a contact address (rule 6, ADR-005). `entity_refs` holds identifiers
only; the email address is read from M1 at send time and dropped again.
"""
from __future__ import annotations

from django.db import models

from rally.core import clock


class OutboxStatus(models.TextChoices):
    """The honest wording of AGENTS.md section 5.

    `SENT` means the provider accepted the message. It never means delivered: the system
    does not claim a delivery the provider did not confirm (G-03).
    """

    QUEUED = "queued", "queued"
    SENT = "sent", "sent"
    FAILED = "failed", "failed"


class Outbox(models.Model):
    event_type = models.CharField(max_length=64)
    entity_refs = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=OutboxStatus.choices, default=OutboxStatus.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(default=clock.now, editable=False)
    next_attempt_at = models.DateTimeField(default=clock.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    provider_response = models.CharField(max_length=255, blank=True, default="")
    last_error = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "outbox"
        indexes = [models.Index(fields=["status", "next_attempt_at"], name="outbox_due_idx")]

    def __str__(self) -> str:  # pragma: no cover
        return f"outbox:{self.pk}:{self.event_type}"


class Notification(models.Model):
    """The in-app notification. It always succeeds locally, whatever email does."""

    recipient_account_id = models.BigIntegerField()
    notification_type = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=clock.now, editable=False)
    read_at = models.DateTimeField(null=True, blank=True)

    # Mechanism, not content: it makes dispatch idempotent when the worker retries a
    # record whose email failed, so one event never produces two in-app notifications.
    source_outbox = models.OneToOneField(
        Outbox, on_delete=models.CASCADE, related_name="notification", null=True, blank=True
    )

    class Meta:
        db_table = "notification"
        indexes = [models.Index(fields=["recipient_account_id", "read_at"], name="notification_inbox_idx")]

    def __str__(self) -> str:  # pragma: no cover
        return f"notification:{self.pk}"
