"""Template context processors."""
from __future__ import annotations


def viewer(request) -> dict:
    """Expose only the public viewer view model to templates (FE-1)."""
    return {"viewer": getattr(request, "viewer", None)}


def unread_notifications(request) -> dict:
    """The badge in the header (S10).

    A count, not a notification: nothing private and nothing about another player
    (FE-2). It is kept out of `ViewerView` on purpose - that view model is M1's identity
    summary, and the inbox belongs to M7.
    """
    seen = getattr(request, "viewer", None)
    if seen is None:
        return {"unread_notifications": 0}

    from rally.modules.notification.api import facade as notification

    return {"unread_notifications": notification.unread_count(seen.account_id)}


def unread_messages(request) -> dict:
    """The messages badge in the header (M9).

    A count, nothing about who or what (FE-2). Kept out of `ViewerView` for the same
    reason the notifications count is: that view model is M1's identity summary.
    """
    seen = getattr(request, "viewer", None)
    if seen is None:
        return {"unread_messages": 0}

    from rally.modules.messaging.api import facade as messaging

    return {"unread_messages": messaging.unread_count(seen.account_id)}
