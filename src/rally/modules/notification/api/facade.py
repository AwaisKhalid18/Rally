"""M7 — facade for the worker.

M7 publishes nothing to business modules (AGENTS.md §3). These operations exist for
Platform's two hosts: the worker, which polls the outbox and asks M7 to dispatch what is
due, and the web host, which renders a player's own inbox (S10).
"""
from __future__ import annotations

from rally.modules.notification.internal import adapters, dispatch, inbox
from rally.modules.notification.internal.adapters import EmailAdapter
from rally.modules.notification.internal.dispatch import DispatchRun

MAX_ATTEMPTS = dispatch.MAX_ATTEMPTS
RETRY_INTERVAL = dispatch.RETRY_INTERVAL
RETRY_WINDOW = dispatch.RETRY_WINDOW

# The provider seam, published because ADR-005 asks for the provider-outage case to be
# demonstrable: "simulate email-provider outage; invitation operations should still
# succeed". A caller swaps the adapter; it still cannot see M7's internals (rule 2).
RecordingEmailAdapter = adapters.RecordingEmailAdapter
AlwaysFailingEmailAdapter = adapters.AlwaysFailingEmailAdapter


def set_email_adapter(adapter: EmailAdapter | None) -> EmailAdapter | None:
    """Install an email adapter and return the previous one. Tests and the demo only."""
    return adapters.set_adapter(adapter)


def dispatch_due(limit: int = 50) -> DispatchRun:
    """Dispatch every outbox record whose next attempt is due. Never raises on a
    provider failure: a failure is recorded and retried."""
    return dispatch.dispatch_due(limit=limit)


# --- The in-app inbox (S10) ---------------------------------------------------
#
# Published for Platform's web host, exactly as the dispatch operations above are
# published for its worker host. No *business* module calls these: "nothing -> M7"
# (AGENTS.md §3) keeps capability modules out, and Platform calls every facade
# (rule 14). M7 still owns the invariant and starts its own transaction for a write.

NotificationRecord = inbox.NotificationRecord
EMAIL_STATUSES = inbox.EMAIL_STATUSES
NO_EMAIL_REASON = inbox.NO_EMAIL_REASON


def list_for_player(account_id: int, limit: int = 50) -> list[NotificationRecord]:
    """One player's notifications, newest first. Ids and event types, no wording."""
    return inbox.list_for_player(account_id, limit=limit)


def unread_count(account_id: int) -> int:
    return inbox.unread_count(account_id)


def mark_read(notification_id: int, account_id: int) -> bool:
    """False when the notification is not this player's — or does not exist. The two
    answers are deliberately the same (ASR-05)."""
    return inbox.mark_read(notification_id, account_id)


def mark_all_read(account_id: int) -> int:
    return inbox.mark_all_read(account_id)
