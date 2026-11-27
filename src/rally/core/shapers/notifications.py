"""Public view models for a player's own notification inbox (FR-12, ASR-11).

M7 hands over an event type and some ids. The wording and the link are presentation, so
they are built here (rule 14: no business decision is taken — nothing is filtered,
ranked or judged, only worded).

Two rules shape every line of this file:

* **FE-5 / AGENTS §5 Honest feedback.** An email is `queued`, `sent` or `failed`. `sent`
  means the provider accepted it. The product never says "delivered".
* **Rule 13 / FE-6.** A field that cannot be resolved is absent **with a reason**.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.urls import reverse

from rally.core.localtime import local_date_text, local_time_text
from rally.modules.notification.api.facade import NotificationRecord

# One entry per event type M7 can record. The sentence is written from the reader's point
# of view: they are the account the event named as its recipient.
_WORDING = {
    "account.verification_requested": "Verify your email address to appear in search and send invitations.",
    "invitation.sent": "You have a new invitation to play.",
    "invitation.accepted": "An invitation you sent was accepted. You have a confirmed game.",
    "invitation.declined": "An invitation you sent was declined.",
    "invitation.cancelled": "An invitation you received was cancelled by the player who sent it.",
    "game.cancelled": "A confirmed game was cancelled by the other player. That time is free again.",
    # S12: the block cascade. This must not say a block happened - see the event's
    # comment in rally.core.ports.outbox.
    "invitation.cancelled_by_block": "An invitation is no longer available and has been cancelled.",
}

# Rule 13 again: an event this build has no sentence for is still shown, honestly.
UNKNOWN_EVENT_TEXT = "Something happened on your account. Open your invitations to see."

# The email half, said in the product's own words. `sent` is the provider's acceptance
# and nothing more.
_EMAIL_WORDING = {
    "queued": "Email queued",
    "sent": "Email sent to your address (the provider accepted it)",
    "failed": "Email could not be sent — this notification is still here",
}


@dataclass(frozen=True)
class NotificationView:
    notification_id: int
    text: str
    when_text: str
    is_read: bool
    email_status: str            # "queued" | "sent" | "failed", or "" when absent
    email_status_text: str       # always a sentence: the status, or the reason (rule 13)
    link: str                    # "" when the event points at nothing to open


def _link(record: NotificationRecord) -> str:
    """Where this notification leads.

    Keyed on the **event type**, not on which ids happen to be present: an acceptance
    and a game cancellation both carry a game id and an invitation id, and they lead to
    different pages.
    """
    if record.notification_type == "game.cancelled":
        return reverse("games")
    if record.invitation_id is not None:
        return reverse("invitation_detail", kwargs={"invitation_id": record.invitation_id})
    return ""


def notification_view(record: NotificationRecord) -> NotificationView:
    status = record.email_status or ""
    return NotificationView(
        notification_id=record.notification_id,
        text=_WORDING.get(record.notification_type, UNKNOWN_EVENT_TEXT),
        when_text=(
            f"{local_date_text(record.created_at)} {local_time_text(record.created_at)}"
        ),
        is_read=record.is_read,
        email_status=status,
        email_status_text=(
            _EMAIL_WORDING.get(status)
            or record.email_status_reason
            or "The email status is not known."
        ),
        link=_link(record),
    )


def notification_views(records) -> list[NotificationView]:
    return [notification_view(record) for record in records]
