"""Public view models for M6 Safety (PRD §12.5).

Only one list is ever shown to a player: the people **they** have blocked. There is
deliberately no view model for a report — M6 publishes no way to read one back — and
none for "who blocked me", which must not exist at all.
"""
from __future__ import annotations

from dataclasses import dataclass

from rally.core.localtime import local_date_text

UNKNOWN_PLAYER = "A player who is no longer available"


@dataclass(frozen=True)
class BlockedPlayerView:
    account_id: int
    display_name: str
    since_text: str


def blocked_player_views(rows, profiles_by_id) -> list[BlockedPlayerView]:
    views = []
    for row in rows:
        profile = profiles_by_id.get(row.blocked_account_id)
        views.append(
            BlockedPlayerView(
                account_id=row.blocked_account_id,
                # Rule 13: a name that cannot be resolved becomes a reason, not a blank.
                display_name=profile.display_name if profile else UNKNOWN_PLAYER,
                since_text=local_date_text(row.created_at),
            )
        )
    return views
