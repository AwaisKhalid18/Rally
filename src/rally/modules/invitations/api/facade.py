"""M5 Invitation & Games — facade.

AGENTS.md §3 lists `send`, `accept`, `decline`, `cancelInvitation`, `cancelGame`,
`listForPlayer`, `expirePending` and `cancelPendingBetween`. **S7 publishes the send and
the listing**; acceptance and the confirmed game are S8, cancellation and expiry S9, the
games screen S11, and `cancelPendingBetween` (M6's port) S12.

M5 exclusively owns invitation state. No other module may change a status, and M5 calls
no module to do it (ASR-07).
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from rally.modules.invitations.internal import responding, sending
from rally.modules.invitations.internal.models import (
    ConfirmedGame,
    Invitation,
    InvitationStatus,
)

EXPIRY_WINDOW = sending.EXPIRY_WINDOW
VENUE_MIN_LENGTH = sending.VENUE_MIN_LENGTH
VENUE_MAX_LENGTH = sending.VENUE_MAX_LENGTH

SENDER_UNVERIFIED = sending.SENDER_UNVERIFIED
RECIPIENT_IS_SELF = sending.RECIPIENT_IS_SELF
RECIPIENT_UNKNOWN = sending.RECIPIENT_UNKNOWN
BLOCKED = sending.BLOCKED
END_BEFORE_START = sending.END_BEFORE_START
START_IN_PAST = sending.START_IN_PAST
VENUE_REQUIRED = sending.VENUE_REQUIRED
VENUE_TOO_SHORT = sending.VENUE_TOO_SHORT
VENUE_TOO_LONG = sending.VENUE_TOO_LONG
RECIPIENT_UNAVAILABLE = sending.RECIPIENT_UNAVAILABLE
DUPLICATE_PENDING = sending.DUPLICATE_PENDING

STATUS_LABELS = dict(InvitationStatus.choices)


@dataclass(frozen=True)
class InvitationRecord:
    """One invitation as a participant may see it.

    Both account ids are here because the caller is always a participant and needs to
    know which side it was on. No contact data: M5 holds none (rule 6).
    """

    invitation_id: int
    sender_account_id: int
    recipient_account_id: int
    starts_at: _dt.datetime
    ends_at: _dt.datetime
    venue: str
    status: str
    status_label: str
    created_at: _dt.datetime
    expires_at: _dt.datetime

    def other_party(self, viewer_account_id: int) -> int:
        return (
            self.recipient_account_id
            if viewer_account_id == self.sender_account_id
            else self.sender_account_id
        )

    def was_sent_by(self, viewer_account_id: int) -> bool:
        return viewer_account_id == self.sender_account_id


@dataclass(frozen=True)
class SendResult:
    invitation_id: int | None = None
    errors: dict[str, str] | None = None

    @property
    def ok(self) -> bool:
        return self.invitation_id is not None


def _record(row: Invitation) -> InvitationRecord:
    return InvitationRecord(
        invitation_id=row.pk,
        sender_account_id=row.sender_account_id,
        recipient_account_id=row.recipient_account_id,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        venue=row.venue,
        status=row.status,
        status_label=STATUS_LABELS[row.status],
        created_at=row.created_at,
        expires_at=row.expires_at,
    )


def send(sender_account_id: int, recipient_account_id: int, starts_at, ends_at, venue: str) -> SendResult:
    """Send an invitation. FR-08, PRD §12.3, ASR-06, ASR-10.

    Returns the new invitation's id, or a field -> message mapping saying exactly why it
    was refused. Success is reported only after the transaction has committed.
    """
    result = sending.send(sender_account_id, recipient_account_id, starts_at, ends_at, venue)
    return SendResult(invitation_id=result.invitation_id, errors=dict(result.errors or {}))


def list_for_player(account_id: int) -> tuple[list[InvitationRecord], list[InvitationRecord]]:
    """(sent, received), newest first. FR-10, bounded by ASR-05."""
    sent = [
        _record(row) for row in Invitation.objects.filter(sender_account_id=account_id)
    ]
    received = [
        _record(row) for row in Invitation.objects.filter(recipient_account_id=account_id)
    ]
    return sent, received


def get_for_participant(invitation_id: int, account_id: int) -> InvitationRecord | None:
    """One invitation, but only for a player who sent or received it.

    Authorisation belongs to the module that owns the record (ADR-003, ASR-05). A
    non-participant gets None, which the caller turns into a not-found — never a
    "forbidden", which would itself confirm the invitation exists.
    """
    row = Invitation.objects.filter(pk=invitation_id).first()
    if row is None:
        return None
    if account_id not in (row.sender_account_id, row.recipient_account_id):
        return None
    return _record(row)


# --- Responding (S8) ---------------------------------------------------------

NOT_FOUND = responding.NOT_FOUND
NOT_THE_RECIPIENT = responding.NOT_THE_RECIPIENT
NO_LONGER_PENDING = responding.NO_LONGER_PENDING
HAS_EXPIRED = responding.HAS_EXPIRED
NO_LONGER_AVAILABLE = responding.NO_LONGER_AVAILABLE
OVERLAPPING_GAME = responding.OVERLAPPING_GAME


@dataclass(frozen=True)
class ResponseResult:
    invitation_id: int | None = None
    game_id: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def accept(invitation_id: int, account_id: int) -> ResponseResult:
    """Accept an invitation and create the confirmed game, atomically.

    FR-09, FR-15, PRD §12.3, §12.4; ASR-07, ASR-08; ADR-004.

    Only the recipient may accept. A rejection carries the domain reason - never a raw
    database error.
    """
    result = responding.accept(invitation_id, account_id)
    return ResponseResult(
        invitation_id=result.invitation_id, game_id=result.game_id, error=result.error
    )


def decline(invitation_id: int, account_id: int) -> ResponseResult:
    """Decline an invitation. No reason is required (PRD §12.3)."""
    result = responding.decline(invitation_id, account_id)
    return ResponseResult(invitation_id=result.invitation_id, error=result.error)


@dataclass(frozen=True)
class GameRecord:
    game_id: int
    invitation_id: int
    starts_at: _dt.datetime
    ends_at: _dt.datetime
    venue: str
    is_cancelled: bool


def get_game_for_invitation(invitation_id: int, account_id: int) -> GameRecord | None:
    """The game an accepted invitation created, for a participant only (ASR-05).

    The full games screen is S11; this is what the invitation page needs to say that
    the game exists.
    """
    record = get_for_participant(invitation_id, account_id)
    if record is None:
        return None
    game = ConfirmedGame.objects.filter(invitation_id=invitation_id).first()
    if game is None:
        return None
    return GameRecord(
        game_id=game.pk,
        invitation_id=invitation_id,
        starts_at=game.starts_at,
        ends_at=game.ends_at,
        venue=game.venue,
        is_cancelled=game.is_cancelled,
    )
