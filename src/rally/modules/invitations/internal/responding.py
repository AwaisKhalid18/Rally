"""Accepting and declining — the system's defining transaction (ASR-07, ASR-08, ADR-004).

Accepting is one transaction owned by M5 (architecture §6.5, §8.4):

    BEGIN
      re-read the invitation FOR UPDATE
      still Pending?  not expired by server UTC?
      recipient still available?           (M3, a read, inside this transaction)
      no overlapping confirmed game for EITHER player?
      insert confirmed_game and two game_participant rows
      set the invitation Accepted
      append the outbox record
    COMMIT

Double-booking is enforced **twice** (ADR-004): the application check above, so the
player gets a sentence, and a PostgreSQL exclusion constraint, which is what actually
holds under concurrency. The application check alone is check-then-act and loses a race.

A rejected acceptance returns a domain reason. A raw constraint error never reaches a
player (PRD §12.4).
"""
from __future__ import annotations

from dataclasses import dataclass

from django.db import IntegrityError, transaction

from rally.core import clock
from rally.core.logging import log_operation
from rally.core.ports.outbox import (
    EVENT_INVITATION_ACCEPTED,
    EVENT_INVITATION_DECLINED,
    RECIPIENT_KEY,
    append_outbox,
)
from rally.modules.availability.api import facade as availability
from rally.modules.invitations.internal.models import (
    ConfirmedGame,
    GameParticipant,
    Invitation,
    InvitationStatus,
)

NOT_FOUND = "No such invitation."
NOT_THE_RECIPIENT = "Only the player who received an invitation can respond to it."
NO_LONGER_PENDING = "This invitation is no longer pending."
HAS_EXPIRED = "This invitation has expired."
NO_LONGER_AVAILABLE = (
    "You are no longer available for that time. Add the time back to your playing times, "
    "or ask for a different time."
)
OVERLAPPING_GAME = "You already have a confirmed game that overlaps that time."

# The constraint added in migration 0003. Its name is matched so that a genuine, unrelated
# integrity error is re-raised rather than silently reported as an overlap.
OVERLAP_CONSTRAINT = "game_participant_no_overlap"


@dataclass(frozen=True)
class ResponseResult:
    invitation_id: int | None = None
    game_id: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _locked_for_response(invitation_id: int, account_id: int):
    """Re-read the invitation under a row lock and judge it afresh.

    Every transition re-reads and re-validates inside its own transaction, so the first
    committed action wins and the losers are told why (ASR-07, PRD §12.3).
    """
    invitation = Invitation.objects.select_for_update().filter(pk=invitation_id).first()
    if invitation is None:
        return None, NOT_FOUND
    if account_id != invitation.recipient_account_id:
        # The sender gets the same answer as a stranger: only the recipient responds.
        return None, NOT_THE_RECIPIENT
    if invitation.status != InvitationStatus.PENDING:
        return None, NO_LONGER_PENDING
    # Expiry is authoritative here, at commit time - not whenever the sweep last ran
    # (ASR-09, ADR-005).
    if invitation.expires_at <= clock.now():
        return None, HAS_EXPIRED
    return invitation, None


def _overlapping_game_exists(account_ids, starts_at, ends_at) -> bool:
    """The readable half of the double-booking check (PRD §12.4).

    Two games overlap when one starts before the other ends and ends after the other
    starts, so back-to-back games do not conflict. Cancelled games do not count.
    """
    return GameParticipant.objects.filter(
        account_id__in=list(account_ids),
        cancelled_at__isnull=True,
        starts_at__lt=ends_at,
        ends_at__gt=starts_at,
    ).exists()


def accept(invitation_id: int, account_id: int) -> ResponseResult:
    with transaction.atomic():
        invitation, error = _locked_for_response(invitation_id, account_id)
        if error:
            return ResponseResult(error=error)

        if not availability.has_availability(
            invitation.recipient_account_id, invitation.starts_at, invitation.ends_at
        ):
            return ResponseResult(error=NO_LONGER_AVAILABLE)

        players = (invitation.recipient_account_id, invitation.sender_account_id)
        if _overlapping_game_exists(players, invitation.starts_at, invitation.ends_at):
            return ResponseResult(error=OVERLAPPING_GAME)

        try:
            # A savepoint, so that losing the race to the exclusion constraint leaves
            # this transaction usable and the player gets a sentence instead of a
            # database error. This is M5's own nesting, not another module's (rule 4).
            with transaction.atomic():
                game = ConfirmedGame.objects.create(
                    invitation=invitation,
                    starts_at=invitation.starts_at,
                    ends_at=invitation.ends_at,
                    venue=invitation.venue,
                    created_at=clock.now(),
                )
                GameParticipant.objects.bulk_create(
                    [
                        GameParticipant(
                            game=game,
                            account_id=player,
                            starts_at=invitation.starts_at,
                            ends_at=invitation.ends_at,
                        )
                        for player in players
                    ]
                )
        except IntegrityError as raised:
            if OVERLAP_CONSTRAINT in str(raised):
                log_operation(
                    "invitation.accept", "rejected", invitation_id=invitation_id, reason="overlap"
                )
                return ResponseResult(error=OVERLAPPING_GAME)
            raise

        # The invitation stays Accepted; the game is the separate record (PRD §12.3).
        Invitation.objects.filter(pk=invitation_id).update(status=InvitationStatus.ACCEPTED)
        append_outbox(
            EVENT_INVITATION_ACCEPTED,
            {
                RECIPIENT_KEY: invitation.sender_account_id,
                "invitation_id": invitation_id,
                "game_id": game.pk,
            },
        )

    return ResponseResult(invitation_id=invitation_id, game_id=game.pk)


def decline(invitation_id: int, account_id: int) -> ResponseResult:
    """Declining needs no reason (PRD §12.3) and creates nothing."""
    with transaction.atomic():
        invitation, error = _locked_for_response(invitation_id, account_id)
        if error:
            return ResponseResult(error=error)

        Invitation.objects.filter(pk=invitation_id).update(status=InvitationStatus.DECLINED)
        append_outbox(
            EVENT_INVITATION_DECLINED,
            {RECIPIENT_KEY: invitation.sender_account_id, "invitation_id": invitation_id},
        )

    return ResponseResult(invitation_id=invitation_id)
