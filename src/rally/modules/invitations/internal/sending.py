"""Sending an invitation: the eligibility rules and the one transaction (FR-08, ASR-10).

Every rule here is M5's, and the checks run **inside the transaction that creates the
invitation** (architecture §6.3). The facades M5 calls — M2, M3, M6 — are reads, so none
of them opens a transaction of its own (rule 4), and nothing external is touched inside
it (rule 5).

M5 does not call M1. The allowlist grants `invitations -> availability, safety, profile`
only, so the sender's verification state is read through M2, which relays M1's published
view (architecture §6.3: "verify sender is verified (M1 via M2)").
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from django.db import transaction

from rally.core import clock
from rally.core.ports.outbox import EVENT_INVITATION_SENT, RECIPIENT_KEY, append_outbox
from rally.modules.availability.api import facade as availability
from rally.modules.invitations.internal.models import Invitation, InvitationStatus
from rally.modules.profiles.api import facade as profiles
from rally.modules.safety.api import facade as safety

# PRD §12.3: an unanswered invitation expires 24 hours after it was created, or at the
# proposed start time if that comes first.
EXPIRY_WINDOW = _dt.timedelta(hours=24)

# G-12 (still an open proposal): the PRD says venue is free text but gives no bounds.
VENUE_MIN_LENGTH = 2
VENUE_MAX_LENGTH = 100

SENDER_UNVERIFIED = (
    "Verify your email address before sending invitations. "
    "Open the link in the verification email we queued when you registered."
)
RECIPIENT_IS_SELF = "You cannot invite yourself."
RECIPIENT_UNKNOWN = "That player is not available."
BLOCKED = "You cannot send an invitation to that player."
END_BEFORE_START = "The end time must be after the start time."
START_IN_PAST = "That time has already passed. Choose a time in the future."
VENUE_REQUIRED = "Enter where you would like to play."
VENUE_TOO_SHORT = f"Use at least {VENUE_MIN_LENGTH} characters."
VENUE_TOO_LONG = f"Use at most {VENUE_MAX_LENGTH} characters."
RECIPIENT_UNAVAILABLE = (
    "That player is not available for the whole of that time. "
    "Choose a time inside one of their listed playing times."
)
DUPLICATE_PENDING = (
    "You already have a pending invitation to that player for an overlapping time."
)


@dataclass(frozen=True)
class SendResult:
    invitation_id: int | None = None
    errors: dict[str, str] | None = None

    @property
    def ok(self) -> bool:
        return self.invitation_id is not None


def _check_venue(venue: str) -> str | None:
    value = (venue or "").strip()
    if not value:
        return VENUE_REQUIRED
    if len(value) < VENUE_MIN_LENGTH:
        return VENUE_TOO_SHORT
    if len(value) > VENUE_MAX_LENGTH:
        return VENUE_TOO_LONG
    return None


def _has_overlapping_pending(sender_id: int, recipient_id: int, starts_at, ends_at) -> bool:
    """PRD §12.3: a sender may not hold two pending invitations to the same recipient
    for overlapping times. Half-open, so back-to-back proposals are fine."""
    return Invitation.objects.filter(
        sender_account_id=sender_id,
        recipient_account_id=recipient_id,
        status=InvitationStatus.PENDING,
        starts_at__lt=ends_at,
        ends_at__gt=starts_at,
    ).exists()


def send(sender_id: int, recipient_id: int, starts_at, ends_at, venue: str) -> SendResult:
    """Create a Pending invitation, or say exactly why it cannot be created.

    The result is reported only after the transaction commits, so a success message can
    never be shown for an invitation that does not exist (FR-08, AC4).
    """
    errors: dict[str, str] = {}

    if ends_at is None or starts_at is None:
        return SendResult(errors={"form": END_BEFORE_START})
    if ends_at <= starts_at:
        errors["end"] = END_BEFORE_START
    elif starts_at <= clock.now():
        errors["date"] = START_IN_PAST

    venue_error = _check_venue(venue)
    if venue_error:
        errors["venue"] = venue_error

    if recipient_id == sender_id:
        errors["form"] = RECIPIENT_IS_SELF
    elif profiles.get_public_profile(recipient_id) is None:
        errors["form"] = RECIPIENT_UNKNOWN
    elif not profiles.is_verified_player(sender_id):
        # ASR-06. Read through M2, which relays M1's published view.
        errors["form"] = SENDER_UNVERIFIED
    elif safety.is_blocked_between(sender_id, recipient_id):
        # ASR-10. One rule, published by M6, applied here and in search.
        errors["form"] = BLOCKED

    if errors:
        return SendResult(errors=errors)

    now = clock.now()
    with transaction.atomic():
        # Re-checked inside the transaction: availability and the duplicate rule are
        # the two that another request could have changed since the checks above.
        if not availability.has_availability(recipient_id, starts_at, ends_at):
            return SendResult(errors={"form": RECIPIENT_UNAVAILABLE})
        if _has_overlapping_pending(sender_id, recipient_id, starts_at, ends_at):
            return SendResult(errors={"form": DUPLICATE_PENDING})

        invitation = Invitation.objects.create(
            sender_account_id=sender_id,
            recipient_account_id=recipient_id,
            starts_at=starts_at,
            ends_at=ends_at,
            venue=venue.strip(),
            status=InvitationStatus.PENDING,
            created_at=now,
            expires_at=min(now + EXPIRY_WINDOW, starts_at),
        )
        # Same transaction as the invitation: the event and the thing it describes are
        # committed together or not at all (rule 3, ADR-005). No email is sent here.
        append_outbox(
            EVENT_INVITATION_SENT,
            {RECIPIENT_KEY: recipient_id, "invitation_id": invitation.pk},
        )

    return SendResult(invitation_id=invitation.pk)
