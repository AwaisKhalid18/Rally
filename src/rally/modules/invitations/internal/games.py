"""Confirmed games: the listing, and cancelling one (FR-15, PRD §12.4).

A *confirmed game* is its own record. The invitation that produced it stays Accepted
for good: cancelling the game does not reopen, undo or re-answer the invitation
(PRD §12.3, §6.1). The two are different things and this module keeps them apart.

Cancelling is one transaction owned by M5 (architecture §8.4):

    BEGIN
      re-read the game FOR UPDATE
      is the caller a participant?       (a stranger gets the same answer as for a
                                          game that does not exist - ASR-05)
      still live?  not started yet?      (judged on server UTC, rule 8)
      stamp cancelled_at on the game and on BOTH participant rows
      append the outbox record for the other player
    COMMIT

**Why no slot is written.** PRD §12.4 says the slot "is restored for both players",
and architecture §8.5 repeats it. Nothing ever consumed one: accepting an invitation
writes participant rows, never a slot, so there is nothing to give back. The time is
free again the moment `cancelled_at` is set, because the exclusion constraint and the
overlap check both ignore cancelled participations. That is AGENTS.md §9 **G-10**, and
the outcome the PRD asks for is reached without a slot write.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from django.db import transaction

from rally.core import clock
from rally.core.logging import log_operation
from rally.core.ports.outbox import EVENT_GAME_CANCELLED, RECIPIENT_KEY, append_outbox
from rally.modules.invitations.internal.models import (
    ConfirmedGame,
    GameParticipant,
    Invitation,
)

GAME_NOT_FOUND = "No such game."
ALREADY_CANCELLED = "This game has already been cancelled."
ALREADY_STARTED = (
    "This game has already started, so it can no longer be cancelled. "
    "Speak to the other player."
)


@dataclass(frozen=True)
class GameDetail:
    """One confirmed game as a participant may see it.

    `can_cancel` and `has_started` are decided **here**, on the server clock: whether an
    action is still allowed is a business rule and may not be re-derived by a template
    or a view (rule 14, FE-4, rule 8).
    """

    game_id: int
    invitation_id: int
    other_party_account_id: int
    starts_at: _dt.datetime
    ends_at: _dt.datetime
    venue: str
    is_cancelled: bool
    cancelled_at: _dt.datetime | None
    cancelled_by_you: bool
    has_started: bool
    has_ended: bool
    can_cancel: bool


def _detail(game: ConfirmedGame, invitation: Invitation, account_id: int, now) -> GameDetail:
    other = (
        invitation.recipient_account_id
        if account_id == invitation.sender_account_id
        else invitation.sender_account_id
    )
    cancelled = game.cancelled_at is not None
    started = game.starts_at <= now
    return GameDetail(
        game_id=game.pk,
        invitation_id=invitation.pk,
        other_party_account_id=other,
        starts_at=game.starts_at,
        ends_at=game.ends_at,
        venue=game.venue,
        is_cancelled=cancelled,
        cancelled_at=game.cancelled_at,
        cancelled_by_you=game.cancelled_by_account_id == account_id,
        has_started=started,
        has_ended=game.ends_at <= now,
        # PRD §12.4: either player, at any time before the start time.
        can_cancel=not cancelled and not started,
    )


def _participant_games(account_id: int):
    """The games this player is in, found through their own participant rows."""
    game_ids = GameParticipant.objects.filter(account_id=account_id).values_list(
        "game_id", flat=True
    )
    return ConfirmedGame.objects.filter(pk__in=game_ids).select_related("invitation")


def list_for_player(account_id: int) -> tuple[list[GameDetail], list[GameDetail]]:
    """`(upcoming, finished)` for one player.

    *Upcoming* is a live game whose end time has not passed. *Finished* holds everything
    else — played and cancelled alike — because a cancelled game is history a player may
    need to see, not something to hide (PRD §12.4). Both participants see the same game
    with the same facts; only `cancelled_by_you` differs.
    """
    now = clock.now()
    upcoming: list[GameDetail] = []
    finished: list[GameDetail] = []
    for game in _participant_games(account_id).order_by("starts_at"):
        detail = _detail(game, game.invitation, account_id, now)
        if detail.is_cancelled or detail.has_ended:
            finished.append(detail)
        else:
            upcoming.append(detail)
    finished.reverse()  # newest first: the most recent history matters most
    return upcoming, finished


def get_for_participant(game_id: int, account_id: int) -> GameDetail | None:
    """One game, for a participant only. `None` for anyone else (ASR-05)."""
    game = ConfirmedGame.objects.filter(pk=game_id).select_related("invitation").first()
    if game is None:
        return None
    if not GameParticipant.objects.filter(game_id=game_id, account_id=account_id).exists():
        return None
    return _detail(game, game.invitation, account_id, clock.now())


@dataclass(frozen=True)
class CancelGameResult:
    game_id: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def cancel_game(game_id: int, account_id: int) -> CancelGameResult:
    """Either participant cancels, any time before the start (PRD §12.4, FR-15).

    No reason is asked for. The explicit confirmation step the PRD requires is the
    caller's to present; by the time this runs the player has confirmed.
    """
    with transaction.atomic():
        game = (
            ConfirmedGame.objects.select_for_update()
            .filter(pk=game_id)
            .select_related("invitation")
            .first()
        )
        if game is None:
            return CancelGameResult(error=GAME_NOT_FOUND)
        if not GameParticipant.objects.filter(game_id=game_id, account_id=account_id).exists():
            # The same answer a non-existent game gets: anything else would confirm
            # that this one exists (ASR-05).
            return CancelGameResult(error=GAME_NOT_FOUND)
        if game.cancelled_at is not None:
            # Two participants can race each other; the first commit wins and the other
            # is told plainly (PRD §12.3 'first committed action wins').
            return CancelGameResult(error=ALREADY_CANCELLED)

        now = clock.now()
        if game.starts_at <= now:
            # The boundary is inclusive: at the start time exactly it is too late.
            return CancelGameResult(error=ALREADY_STARTED)

        ConfirmedGame.objects.filter(pk=game_id).update(
            cancelled_at=now, cancelled_by_account_id=account_id
        )
        # Both rows, so neither player's time is blocked any longer. The exclusion
        # constraint and the overlap check both skip cancelled participations, so the
        # time is free at once and no slot is written (G-10).
        GameParticipant.objects.filter(game_id=game_id).update(cancelled_at=now)

        invitation = game.invitation
        other = (
            invitation.recipient_account_id
            if account_id == invitation.sender_account_id
            else invitation.sender_account_id
        )
        # The other player only: nobody is told about their own action (PRD §12.4).
        append_outbox(
            EVENT_GAME_CANCELLED,
            {RECIPIENT_KEY: other, "game_id": game_id, "invitation_id": invitation.pk},
        )

    # The invitation is untouched and stays Accepted. Cancelling a game is not
    # un-accepting an invitation (PRD §12.3).
    log_operation(
        "game.cancel", "cancelled", account_id=account_id, game_id=game_id,
        invitation_id=invitation.pk,
    )
    return CancelGameResult(game_id=game_id)



def have_confirmed_game_between(first_account_id: int, second_account_id: int) -> bool:
    """Do these two players share a live confirmed game?

    Used by M9 to decide whether they may message each other. A **cancelled** game does
    not count — the pair agreed to play and then did not, so the thread closes with it.
    A game whose start time has passed does: people need to talk after playing.
    """
    theirs = GameParticipant.objects.filter(
        account_id=first_account_id, cancelled_at__isnull=True
    ).values_list("game_id", flat=True)
    return GameParticipant.objects.filter(
        game_id__in=theirs, account_id=second_account_id, cancelled_at__isnull=True
    ).exists()
