"""Public view models for confirmed games (FR-15, PRD §12.4).

A participant sees the other player by **display name only**. Nothing becomes visible
because a game exists: acceptance shares no contact detail (PRD §12.2, ASR-04, rule 6).

Every judgement — whether the game may still be cancelled, whether it has started — is
M5's and arrives already decided on `GameDetail`. This file words it (rule 14, FE-4).
"""
from __future__ import annotations

from dataclasses import dataclass

from rally.core.localtime import local_date_text, local_time_text, to_local
from rally.modules.invitations.api.facade import GameDetail

UNKNOWN_PLAYER = "A player who is no longer available"


@dataclass(frozen=True)
class GameView:
    game_id: int
    invitation_id: int
    # Needed to offer a message to the other player (M9). An account id is not
    # private: it already appears in every profile URL.
    other_party_account_id: int
    other_party_name: str
    when_text: str
    venue: str
    status_label: str
    status: str                 # "confirmed" | "cancelled" | "played"
    can_cancel: bool
    cancelled_note: str         # "" unless it was cancelled


def _status(detail: GameDetail) -> tuple[str, str]:
    if detail.is_cancelled:
        return "cancelled", "Cancelled"
    if detail.has_ended:
        return "played", "Played"
    return "confirmed", "Confirmed"


def game_view(detail: GameDetail, other_party_name: str | None) -> GameView:
    starts = to_local(detail.starts_at)
    status, label = _status(detail)
    return GameView(
        game_id=detail.game_id,
        invitation_id=detail.invitation_id,
        other_party_account_id=detail.other_party_account_id,
        # Rule 13: a name that cannot be resolved is replaced by a reason, not a blank.
        other_party_name=other_party_name or UNKNOWN_PLAYER,
        when_text=(
            f"{starts.strftime('%a')} {local_date_text(detail.starts_at)}, "
            f"{local_time_text(detail.starts_at)}-{local_time_text(detail.ends_at)}"
        ),
        venue=detail.venue,
        status=status,
        status_label=label,
        can_cancel=detail.can_cancel,
        cancelled_note=(
            ""
            if not detail.is_cancelled
            else (
                "You cancelled this game."
                if detail.cancelled_by_you
                else "The other player cancelled this game."
            )
        ),
    )
