"""M8 Player Collections — facade.

Architecture §16.4 lists `addFavorite`, `removeFavorite`, `listFavorites`, `saveSearch`,
`updateSearch`, `deleteSearch`, `listSearches` and `getSearch`. **S13 publishes the
favorites half**; saved searches are S15.

M8 is a leaf: nothing depends on it. These operations exist for Platform's web host.

M8 stores references, never copies (rule 11), does not execute a search and never calls
M4 (rule 12) — reusing a saved search is composed in Platform, which fetches the
criteria from M8 and then calls `M4.search()`.
"""
from __future__ import annotations

from rally.modules.player_collections.internal import favorites

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
