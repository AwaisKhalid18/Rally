"""The in-app inbox: reading and marking notifications (FR-12, ASR-11, ASR-12).

The in-app notification is the part that **always** exists. It is written by the
appender, inside the transaction that changed the business state, so it is committed
with the accept, decline or cancellation that caused it. Email is the fragile half and
is attempted later by the worker; a provider outage, or a stopped worker, leaves the
player's inbox complete and only the email status behind (ASR-12, ADR-005).

Nothing here carries a contact address (rule 6). A notification names its event type and
the ids it refers to; Platform turns those into wording and links.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from django.db import transaction

from rally.core import clock
from rally.modules.notification.internal.models import Notification, OutboxStatus

# The only three words the product may use for an email (AGENTS.md §5 Honest feedback,
# FE-5). "delivered" is not among them: the provider accepting a message is not a
# delivery, and Rally never claims one it was not told about (G-03).
EMAIL_STATUSES = (OutboxStatus.QUEUED, OutboxStatus.SENT, OutboxStatus.FAILED)

# Rule 13: a field that cannot be resolved is absent **with a reason**, never blank.
NO_EMAIL_REASON = "No email was requested for this notification."


@dataclass(frozen=True)
class NotificationRecord:
    """What M7 can honestly say about one notification. Ids and an event type only."""

    notification_id: int
    notification_type: str
    created_at: _dt.datetime
    is_read: bool
    email_status: str | None
    email_status_reason: str | None
    invitation_id: int | None
    game_id: int | None


def _record(row: Notification) -> NotificationRecord:
    outbox = row.source_outbox
    refs = outbox.entity_refs if outbox is not None else {}

    def ref(key: str) -> int | None:
        value = refs.get(key)
        return int(value) if value is not None else None

    return NotificationRecord(
        notification_id=row.pk,
        notification_type=row.notification_type,
        created_at=row.created_at,
        is_read=row.read_at is not None,
        email_status=outbox.status if outbox is not None else None,
        email_status_reason=None if outbox is not None else NO_EMAIL_REASON,
        invitation_id=ref("invitation_id"),
        game_id=ref("game_id"),
    )


def list_for_player(account_id: int, limit: int = 50) -> list[NotificationRecord]:
    """One player's notifications, newest first. Never another player's (ASR-04)."""
    rows = (
        Notification.objects.filter(recipient_account_id=account_id)
        .select_related("source_outbox")
        .order_by("-created_at", "-id")[:limit]
    )
    return [_record(row) for row in rows]


def unread_count(account_id: int) -> int:
    return Notification.objects.filter(
        recipient_account_id=account_id, read_at__isnull=True
    ).count()


def mark_read(notification_id: int, account_id: int) -> bool:
    """Mark one notification read. False when it is not this player's (ASR-05: the
    answer is the same as for one that does not exist, which would otherwise confirm
    that it does)."""
    with transaction.atomic():
        changed = Notification.objects.filter(
            pk=notification_id, recipient_account_id=account_id, read_at__isnull=True
        ).update(read_at=clock.now())
    if changed:
        return True
    # Already read is success; a stranger's row, or none, is not.
    return Notification.objects.filter(
        pk=notification_id, recipient_account_id=account_id
    ).exists()


def mark_all_read(account_id: int) -> int:
    with transaction.atomic():
        return Notification.objects.filter(
            recipient_account_id=account_id, read_at__isnull=True
        ).update(read_at=clock.now())
