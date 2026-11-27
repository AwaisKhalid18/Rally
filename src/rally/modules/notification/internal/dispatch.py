"""Outbox dispatch and the retry policy (ASR-11, ASR-12, ADR-005).

Shape of one record, deliberately in three steps so that **no transaction encloses the
external call** (rule 5):

    transaction A   claim the record
    (no transaction) compose the message and hand it to the provider
    transaction B   record what the provider actually reported

The in-app notification is not created here. The appender wrote it in the transaction
that changed the business state, so it already exists before the worker ever looks: a
provider outage, or a stopped worker, degrades email only and never the state a player
sees (plan.md S10 AC2, ASR-12).
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from django.db import transaction
from django.db.models import F

from rally.core import clock
from rally.core.logging import log_operation
from rally.core.ports.outbox import RECIPIENT_KEY
from rally.modules.notification.internal import messages
from rally.modules.notification.internal.adapters import EmailDeliveryFailed, current_adapter
from rally.modules.notification.internal.models import Notification, Outbox, OutboxStatus

# PRD section 12.3: delivery is attempted within 5 minutes, a failure is retried up to
# 3 times within 15 minutes, then it is logged and left alone.
MAX_ATTEMPTS = 4  # the first attempt plus three retries
RETRY_INTERVAL = _dt.timedelta(minutes=5)
RETRY_WINDOW = _dt.timedelta(minutes=15)


@dataclass(frozen=True)
class DispatchRun:
    claimed: int = 0
    sent: int = 0
    retrying: int = 0
    failed: int = 0

    def __add__(self, other: "DispatchRun") -> "DispatchRun":
        return DispatchRun(
            claimed=self.claimed + other.claimed,
            sent=self.sent + other.sent,
            retrying=self.retrying + other.retrying,
            failed=self.failed + other.failed,
        )


def due_record_ids(now: _dt.datetime, limit: int) -> list[int]:
    return list(
        Outbox.objects.filter(status=OutboxStatus.QUEUED, next_attempt_at__lte=now)
        .order_by("next_attempt_at", "id")
        .values_list("id", flat=True)[:limit]
    )


def _claim(record_id: int) -> Outbox | None:
    """Transaction A: take the record, and make sure its in-app notification exists.

    The appender writes that notification, so the `get_or_create` below is a safety net
    for a record appended before S10 moved it there - not the normal path.
    """
    with transaction.atomic():
        record = (
            Outbox.objects.select_for_update(skip_locked=True)
            .filter(pk=record_id, status=OutboxStatus.QUEUED)
            .first()
        )
        if record is None:
            return None  # another worker got there first
        Notification.objects.get_or_create(
            source_outbox=record,
            defaults={
                "recipient_account_id": int(record.entity_refs.get(RECIPIENT_KEY, 0)),
                "notification_type": record.event_type,
                "created_at": clock.now(),
            },
        )
        return record


def _record_success(record_id: int, provider_response: str, now: _dt.datetime) -> None:
    """Transaction B, happy path. `sent` means the provider accepted it, nothing more."""
    Outbox.objects.filter(pk=record_id).update(
        status=OutboxStatus.SENT,
        attempts=F("attempts") + 1,
        sent_at=now,
        provider_response=provider_response[:255],
        last_error="",
    )


def _record_failure(record: Outbox, reason: str, now: _dt.datetime) -> str:
    """Transaction B, sad path. Returns 'retrying' or 'failed'."""
    attempts = record.attempts + 1
    give_up = attempts >= MAX_ATTEMPTS or (now - record.created_at) >= RETRY_WINDOW
    Outbox.objects.filter(pk=record.pk).update(
        status=OutboxStatus.FAILED if give_up else OutboxStatus.QUEUED,
        attempts=attempts,
        next_attempt_at=now + RETRY_INTERVAL,
        last_error=reason[:255],
    )
    outcome = "failed" if give_up else "retrying"
    log_operation(
        "notification.email",
        outcome,
        outbox_id=record.pk,
        event=record.event_type,
        attempts=attempts,
        reason=reason,
    )
    return outcome


def dispatch_one(record_id: int) -> DispatchRun:
    record = _claim(record_id)
    if record is None:
        return DispatchRun()

    now = clock.now()
    recipient_account_id = int(record.entity_refs.get(RECIPIENT_KEY, 0))

    try:
        message = messages.compose(record.event_type, recipient_account_id)
    except messages.MessageCannotBeComposed as reason:
        # Nothing to send and nothing a retry would fix.
        Outbox.objects.filter(pk=record.pk).update(
            status=OutboxStatus.FAILED,
            attempts=record.attempts + 1,
            last_error=str(reason)[:255],
        )
        log_operation(
            "notification.email", "failed", outbox_id=record.pk, event=record.event_type, reason=str(reason)
        )
        return DispatchRun(claimed=1, failed=1)

    # Outside every transaction (rule 5).
    try:
        provider_response = current_adapter().send(message.to_address, message.subject, message.body)
    except EmailDeliveryFailed as error:
        outcome = _record_failure(record, str(error), clock.now())
        return DispatchRun(claimed=1, retrying=int(outcome == "retrying"), failed=int(outcome == "failed"))

    _record_success(record.pk, provider_response, clock.now())
    log_operation(
        "notification.email",
        "sent",
        outbox_id=record.pk,
        event=record.event_type,
        account_id=recipient_account_id,
    )
    return DispatchRun(claimed=1, sent=1)


def dispatch_due(limit: int = 50) -> DispatchRun:
    total = DispatchRun()
    for record_id in due_record_ids(clock.now(), limit):
        total = total + dispatch_one(record_id)
    return total
