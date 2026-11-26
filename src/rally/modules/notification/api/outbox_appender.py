"""M7's implementation of Platform's `OutboxAppender` port.

It is invoked inside the calling module's transaction, so it opens none of its own
(rule 4) and makes no external call (rule 5). M7 stays the only writer of `outbox`
(rule 1) while no business module imports M7 (rule 3).
"""
from __future__ import annotations

from typing import Any

from rally.core import clock
from rally.modules.notification.internal.models import Outbox, OutboxStatus

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
        return record.pk


_appender = OutboxAppenderImpl()


def appender() -> OutboxAppenderImpl:
    return _appender
