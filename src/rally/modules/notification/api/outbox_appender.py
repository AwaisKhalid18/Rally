"""M7's implementation of Platform's `OutboxAppender` port.

It is invoked inside the calling module's transaction, so it opens none of its own
(rule 4) and makes no external call (rule 5). M7 stays the only writer of `outbox` and
`notification` (rule 1) while no business module imports M7 (rule 3).

It writes **both** rows: the outbox record that will become an email, and the in-app
notification the player reads. Both are therefore committed with the business change
that caused them, so a player's inbox is complete even when the provider is down or the
worker never runs (plan.md S10 AC2, ASR-12). The caller knows of neither table.
"""
from __future__ import annotations

from typing import Any

from rally.core import clock
from rally.core.ports.outbox import RECIPIENT_KEY
from rally.modules.notification.internal.models import Notification, Outbox, OutboxStatus

FORBIDDEN_REF_HINT = "@"


class OutboxAppenderImpl:
    def append(self, event_type: str, entity_refs: dict[str, Any]) -> int:
        for key, value in entity_refs.items():
            if FORBIDDEN_REF_HINT in str(value):
                raise ValueError(
                    f"entity_refs[{key!r}] looks like a contact address; the outbox carries "
                    "identifiers only (rule 6)"
                )
        now = clock.now()
        record = Outbox.objects.create(
            event_type=event_type,
            entity_refs=entity_refs,
            status=OutboxStatus.QUEUED,
            created_at=now,
            next_attempt_at=now,
        )
        Notification.objects.create(
            recipient_account_id=int(entity_refs[RECIPIENT_KEY]),
            notification_type=event_type,
            created_at=now,
            source_outbox=record,
        )
        return record.pk


_appender = OutboxAppenderImpl()


def appender() -> OutboxAppenderImpl:
    return _appender
