"""Favorites: add, list, remove (FR-16, ADR-006, architecture §16.7, §16.8).

Two rules shape this file.

**References, never copies (rule 11).** Nothing about the other player is stored. The
display is composed on every request from the published read views of M2, M3 and M6 —
one SQL statement, the same way M4 composes a search — so the list cannot go stale.

**Shown, not hidden (rule 13, §16.8).** A favorite whose player has no future times
still appears, with the reason in place of the times; so does one whose account can no
longer be resolved, and that one can still be removed. The single exception is a
**blocked pair**, which is omitted in both directions, because blocking is a safety
rule and applies wherever one player can see another (ASR-10).

That asymmetry is deliberate: search excludes incomplete and inactive profiles because
relevance is search's business, while a favorites list is one the player curated and
dropping an entry silently would be the behaviour FR-13 forbids for search criteria.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from django.conf import settings
from django.db import IntegrityError, connection, transaction

from rally.core import clock
from rally.core.logging import log_operation
from rally.modules.player_collections.internal.models import Favorite

# R-15 closes G-07: a cap, adjustable by configuration without an architecture change.
DEFAULT_MAX_FAVORITES = 50

CANNOT_FAVORITE_YOURSELF = "You cannot add yourself to your favorites."
ALREADY_A_FAVORITE = "That player is already in your favorites."
NOT_A_FAVORITE = "That player is not in your favorites."
UNKNOWN_PLAYER = "No such player."

# Rule 13: the two reasons a field can be absent. Neither is a blank or a zero.
NO_AVAILABILITY_REASON = "No playing times recorded"
UNAVAILABLE_ACCOUNT_REASON = "No longer available"


def max_favorites() -> int:
    return int(getattr(settings, "RALLY_MAX_FAVORITES", DEFAULT_MAX_FAVORITES))


def cap_reached_message() -> str:
    return (
        f"Your favorites list is full at {max_favorites()} players. "
        "Remove someone before adding another."
    )


@dataclass(frozen=True)
class FavoriteSlot:
    starts_at: _dt.datetime
    ends_at: _dt.datetime


@dataclass(frozen=True)
class FavoriteEntry:
    """One row of the list, with every field either resolved or absent with a reason."""

    favorited_account_id: int
    created_at: _dt.datetime
    # Absent when the account can no longer be resolved at all (G-06).
    display_name: str | None
    playing_level: str | None
    area_name: str | None
    slots: tuple[FavoriteSlot, ...]
    # Why something is missing, when it is. "" when nothing is.
    unavailable_reason: str | None
    no_slots_reason: str | None

    @property
    def is_resolvable(self) -> bool:
        return self.display_name is not None


@dataclass(frozen=True)
class FavoriteResult:
    favorite_id: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def count_for_owner(owner_account_id: int) -> int:
    return Favorite.objects.filter(owner_account_id=owner_account_id).count()


def add(owner_account_id: int, favorited_account_id: int) -> FavoriteResult:
    """Add a player to your own list (FR-16).

    M8 cannot check that the account exists — it reads published views, not M1 — so the
    caller resolves the player first and M8 judges only what is its own (ASR-05).
    """
    if owner_account_id == favorited_account_id:
        return FavoriteResult(error=CANNOT_FAVORITE_YOURSELF)

    if count_for_owner(owner_account_id) >= max_favorites():
        return FavoriteResult(error=cap_reached_message())

    try:
        # A savepoint, so that losing the race to the unique constraint leaves the
        # caller's transaction usable and the player gets a sentence instead of a
        # database error. Without it the failed INSERT poisons the surrounding
        # transaction and nothing further can be executed in it.
        with transaction.atomic():
            row = Favorite.objects.create(
                owner_account_id=owner_account_id,
                favorited_account_id=favorited_account_id,
                created_at=clock.now(),
            )
    except IntegrityError:
        # The constraint, not a check-then-act test: two requests adding the same player
        # at once leave one row and the second is told plainly.
        return FavoriteResult(error=ALREADY_A_FAVORITE)

    # Favoriting writes no outbox record and notifies nobody (AC3, §16.8): the list is
    # private and adding an event would disclose it.
    log_operation("favorite.add", "added", account_id=owner_account_id)
    return FavoriteResult(favorite_id=row.pk)


def remove(owner_account_id: int, favorited_account_id: int) -> FavoriteResult:
    """Remove a player from your own list. Only your own (ASR-05).

    It works whether or not the account can still be resolved, so an entry showing
    "no longer available" is never stuck on the list (AC2).
    """
    removed, _ = Favorite.objects.filter(
        owner_account_id=owner_account_id, favorited_account_id=favorited_account_id
    ).delete()
    if not removed:
        # The same answer for somebody else's favorite and for one that never existed.
        return FavoriteResult(error=NOT_A_FAVORITE)

    log_operation("favorite.remove", "removed", account_id=owner_account_id)
    return FavoriteResult()


def is_favorite(owner_account_id: int, favorited_account_id: int) -> bool:
    return Favorite.objects.filter(
        owner_account_id=owner_account_id, favorited_account_id=favorited_account_id
    ).exists()


# One statement, composed from the published read views only (rule 1). It reads
# `v_searchable_profile`, `v_active_availability` and `v_block_pairs` and no base table
# of another module.
#
# `v_active_availability` already drops slots whose end time has passed, using the
# database's own `now()`. The extra `ends_at > %(now)s` makes the injectable clock
# authoritative instead, so a frozen test clock governs this path too (rule 8).
_LIST_SQL = """
SELECT f.favorited_account_id            AS account_id,
       f.created_at                      AS created_at,
       p.display_name                    AS display_name,
       p.playing_level                   AS playing_level,
       p.area_name                       AS area_name,
       s.starts_at                       AS starts_at,
       s.ends_at                         AS ends_at
FROM favorite f
LEFT JOIN v_searchable_profile p
       ON p.account_id = f.favorited_account_id
LEFT JOIN v_active_availability s
       ON s.account_id = f.favorited_account_id
      AND s.ends_at > %(now)s
WHERE f.owner_account_id = %(owner_id)s
  -- A blocked pair is omitted in both directions (ASR-10, §16.8).
  AND NOT EXISTS (
        SELECT 1 FROM v_block_pairs b
         WHERE (b.blocker_account_id = %(owner_id)s
                AND b.blocked_account_id = f.favorited_account_id)
            OR (b.blocker_account_id = f.favorited_account_id
                AND b.blocked_account_id = %(owner_id)s)
  )
ORDER BY f.created_at DESC, f.favorited_account_id, s.starts_at
"""


def list_for_owner(owner_account_id: int) -> list[FavoriteEntry]:
    """One player's favorites, newest first, with their slots in time order.

    Each favorite yields one entry however many slots it has; the join is flattened
    here rather than in SQL so the absent cases stay explicit.
    """
    with connection.cursor() as cursor:
        cursor.execute(_LIST_SQL, {"owner_id": owner_account_id, "now": clock.now()})
        rows = cursor.fetchall()

    order: list[int] = []
    gathered: dict[int, dict] = {}
    for account_id, created_at, name, level, area, starts_at, ends_at in rows:
        if account_id not in gathered:
            order.append(account_id)
            gathered[account_id] = {
                "created_at": created_at,
                "name": name,
                "level": level,
                "area": area,
                "slots": [],
            }
        if starts_at is not None:
            gathered[account_id]["slots"].append(FavoriteSlot(starts_at, ends_at))

    entries: list[FavoriteEntry] = []
    for account_id in order:
        found = gathered[account_id]
        resolvable = found["name"] is not None
        entries.append(
            FavoriteEntry(
                favorited_account_id=account_id,
                created_at=found["created_at"],
                display_name=found["name"],
                playing_level=found["level"],
                area_name=found["area"],
                slots=tuple(found["slots"]),
                # An account with no profile at all: gone, or never completed one. It
                # stays on the list and can be removed (AC2, G-06).
                unavailable_reason=None if resolvable else UNAVAILABLE_ACCOUNT_REASON,
                # Shown, not hidden: a player with no future times still appears.
                no_slots_reason=(
                    NO_AVAILABILITY_REASON if resolvable and not found["slots"] else None
                ),
            )
        )
    return entries
