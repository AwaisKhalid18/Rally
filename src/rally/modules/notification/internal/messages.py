"""Message composition, one entry per event type.

M7 decides how an event is worded, never whether it happened (rule: M7 makes no business
decision). Everything private that a message needs - the address, the verification token -
is read from M1 at send time and dropped again (architecture section 6.1, rule 6).
"""
from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.urls import reverse

from rally.core.ports.outbox import EVENT_ACCOUNT_VERIFICATION_REQUESTED
from rally.modules.identity.api import facade as identity


class MessageCannotBeComposed(Exception):
    """The event refers to something that is no longer there. Not a provider failure."""


@dataclass(frozen=True)
class Message:
    to_address: str
    subject: str
    body: str
    notification_type: str


def _site_url() -> str:
    return getattr(settings, "RALLY_SITE_URL", "http://127.0.0.1:8000").rstrip("/")


def _verification_message(recipient_account_id: int) -> Message:
    address = identity.get_delivery_address(recipient_account_id)
    token = identity.get_verification_token(recipient_account_id)
    if address is None:
        raise MessageCannotBeComposed("no deliverable account")
    if token is None:
        raise MessageCannotBeComposed("already verified")

    link = _site_url() + reverse("verify_email", kwargs={"token": token})
    body = (
        "Welcome to Rally.\n\n"
        "Open the link below and press Confirm to verify this email address. "
        "You need a verified address before your profile appears in search results "
        "and before you can send an invitation.\n\n"
        f"{link}\n\n"
        "If you did not create a Rally account, ignore this message.\n"
    )
    return Message(
        to_address=address,
        subject="Verify your email address for Rally",
        body=body,
        notification_type="account.verification_requested",
    )


_COMPOSERS = {
    EVENT_ACCOUNT_VERIFICATION_REQUESTED: _verification_message,
}


def compose(event_type: str, recipient_account_id: int) -> Message:
    try:
        composer = _COMPOSERS[event_type]
    except KeyError:
        raise MessageCannotBeComposed(f"no message for event {event_type!r}") from None
    return composer(recipient_account_id)
