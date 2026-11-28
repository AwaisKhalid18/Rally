"""M8 Player Collections — facade.

Architecture §16.4 lists `addFavorite`, `removeFavorite`, `listFavorites`, `saveSearch`,
`updateSearch`, `deleteSearch`, `listSearches` and `getSearch`. S13 published the
favorites half and **S15 the saved searches**.

M8 is a leaf: nothing depends on it. These operations exist for Platform's web host.

M8 stores references, never copies (rule 11), does not execute a search and never calls
M4 (rule 12) — reusing a saved search is composed in Platform, which fetches the
criteria from M8 and then calls `M4.search()`.
"""
from __future__ import annotations

from rally.modules.player_collections.internal import favorites, saved_searches

FavoriteEntry = favorites.FavoriteEntry
FavoriteSlot = favorites.FavoriteSlot
FavoriteResult = favorites.FavoriteResult

CANNOT_FAVORITE_YOURSELF = favorites.CANNOT_FAVORITE_YOURSELF
ALREADY_A_FAVORITE = favorites.ALREADY_A_FAVORITE
NOT_A_FAVORITE = favorites.NOT_A_FAVORITE

# Rule 13: an absent field carries one of these, never a blank or a zero.
NO_AVAILABILITY_REASON = favorites.NO_AVAILABILITY_REASON
UNAVAILABLE_ACCOUNT_REASON = favorites.UNAVAILABLE_ACCOUNT_REASON


def max_favorites() -> int:
    """The cap (R-15, closing G-07). A configuration value: changing it needs no
    architecture change."""
    return favorites.max_favorites()


def cap_reached_message() -> str:
    """What the player is told when the list is full. Published so the page and the
    rule cannot drift apart."""
    return favorites.cap_reached_message()


def add_favorite(owner_account_id: int, favorited_account_id: int) -> FavoriteResult:
    """Add a player to your own list (FR-16).

    Self and duplicates are refused, and so is the one past the cap. Nothing is
    notified and no outbox record is written: the list is private (§16.8).
    """
    return favorites.add(owner_account_id, favorited_account_id)


def remove_favorite(owner_account_id: int, favorited_account_id: int) -> FavoriteResult:
    """Remove from your own list only. Works even when the account is unresolvable."""
    return favorites.remove(owner_account_id, favorited_account_id)


def list_favorites(owner_account_id: int) -> list[FavoriteEntry]:
    """Your own favorites, newest first, composed from the published read views.

    A player with no future times is **shown** with a reason, not hidden; one whose
    account cannot be resolved is shown as no longer available and can be removed; a
    blocked pair is omitted in both directions (ASR-10).
    """
    return favorites.list_for_owner(owner_account_id)


def is_favorite(owner_account_id: int, favorited_account_id: int) -> bool:
    """Whether this player is already on your list — so a page can offer Add or
    Remove rather than guessing."""
    return favorites.is_favorite(owner_account_id, favorited_account_id)


def count_favorites(owner_account_id: int) -> int:
    return favorites.count_for_owner(owner_account_id)


# --- Saved searches (S15, FR-18, ADR-006) ------------------------------------
#
# M8 stores the criteria and **never runs them**. Reusing one is composed in Platform:
# `get_search()` here, then `M4.search()` — the same entry point a typed search uses,
# so every rule in ASR-02 and ASR-10 applies identically (rule 12, §16.8).

SavedSearchRecord = saved_searches.SavedSearchRecord
SaveResult = saved_searches.SaveResult

DAY_RULE_CHOICES = saved_searches.DAY_RULE_CHOICES
SEARCH_NAME_MAX_LENGTH = saved_searches.NAME_MAX_LENGTH

NAME_REQUIRED = saved_searches.NAME_REQUIRED
NAME_TOO_LONG = saved_searches.NAME_TOO_LONG
NAME_TAKEN = saved_searches.NAME_TAKEN
DAY_REQUIRED = saved_searches.DAY_REQUIRED
DAY_AMBIGUOUS = saved_searches.DAY_AMBIGUOUS
DAY_RULE_UNKNOWN = saved_searches.DAY_RULE_UNKNOWN
TIMES_REQUIRED = saved_searches.TIMES_REQUIRED
SEARCH_END_BEFORE_START = saved_searches.END_BEFORE_START
AREA_REQUIRED = saved_searches.AREA_REQUIRED
SEARCH_NOT_FOUND = saved_searches.NOT_FOUND

# G-05: a fixed date that has passed is reported, never silently moved to today.
NEEDS_A_NEW_DATE = saved_searches.NEEDS_A_NEW_DATE


def max_saved_searches() -> int:
    """The cap (R-15, closing G-07). Configuration, not an architecture change."""
    return saved_searches.max_saved_searches()


def saved_search_cap_message() -> str:
    return saved_searches.cap_reached_message()


def save_search(
    owner_account_id: int,
    name: str,
    start_time,
    end_time,
    area_code: str,
    fixed_date=None,
    day_rule: str = "",
    playing_level: str = "",
    max_distance_km=None,
) -> SaveResult:
    """Save named criteria. Exactly one of `fixed_date` and `day_rule` carries the day."""
    return saved_searches.save(
        owner_account_id, name, start_time, end_time, area_code,
        fixed_date, day_rule, playing_level, max_distance_km,
    )


def update_search(
    saved_search_id: int,
    owner_account_id: int,
    name: str,
    start_time,
    end_time,
    area_code: str,
    fixed_date=None,
    day_rule: str = "",
    playing_level: str = "",
    max_distance_km=None,
) -> SaveResult:
    """Edit your own. Editing is a write to M8 and never triggers a search (§16.8)."""
    return saved_searches.update(
        saved_search_id, owner_account_id, name, start_time, end_time, area_code,
        fixed_date, day_rule, playing_level, max_distance_km,
    )


def delete_search(saved_search_id: int, owner_account_id: int) -> bool:
    """Delete your own. False for somebody else's — the same answer as for one that
    does not exist (ASR-05)."""
    return saved_searches.delete(saved_search_id, owner_account_id)


def list_searches(owner_account_id: int) -> list[SavedSearchRecord]:
    """Your own, most recently changed first. Each carries the date it would run for,
    or the reason it cannot (G-05)."""
    return saved_searches.list_for_owner(owner_account_id)


def get_search(saved_search_id: int, owner_account_id: int) -> SavedSearchRecord | None:
    """The criteria Platform hands to `M4.search()`. `None` for anybody else."""
    return saved_searches.get_for_owner(saved_search_id, owner_account_id)


def count_searches(owner_account_id: int) -> int:
    return saved_searches.count_for_owner(owner_account_id)
