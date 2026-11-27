"""Public view models for M8 Player Collections (FR-16, ASR-04).

The favorites list shows the same public fields a search result does: display name,
playing level, general area and available playing times. No contact detail and no exact
location, because M8 holds neither (rules 6, 7, 11).

Rule 13 is the shape of this file. M8 hands over each field either resolved or **absent
with a reason**, and this turns that into text the page prints as it stands — never a
blank, a zero or a placeholder (FE-6).

The file is named `collections` after the logical module name; the Django app folder is
`player_collections` to avoid shadowing the standard library (AGENTS.md §3.1). Inside
`rally.core.shapers` there is nothing to shadow.
"""
from __future__ import annotations

from dataclasses import dataclass

from rally.core.localtime import local_date_text, local_time_text, to_local
from rally.modules.player_collections.api.facade import FavoriteEntry

LEVEL_LABELS = {
    "beginner": "Beginner",
    "intermediate": "Intermediate",
    "advanced": "Advanced",
}


@dataclass(frozen=True)
class FavoriteSlotView:
    summary: str


@dataclass(frozen=True)
class FavoriteView:
    account_id: int
    display_name: str
    playing_level: str
    area_name: str
    slots: tuple[FavoriteSlotView, ...]
    # "" when the field is present; otherwise the reason, ready to print (FE-6).
    no_slots_reason: str
    unavailable_reason: str
    # A player whose account cannot be resolved has no profile to open, but the entry
    # must still be removable (AC2).
    is_resolvable: bool
    added_text: str


def _slot_view(slot) -> FavoriteSlotView:
    day = to_local(slot.starts_at).strftime("%a")
    return FavoriteSlotView(
        summary=(
            f"{day} {local_date_text(slot.starts_at)}, "
            f"{local_time_text(slot.starts_at)}-{local_time_text(slot.ends_at)}"
        )
    )


def favorite_view(entry: FavoriteEntry) -> FavoriteView:
    resolvable = entry.is_resolvable
    return FavoriteView(
        account_id=entry.favorited_account_id,
        # An unresolvable account has no name to show, so the reason takes its place.
        display_name=entry.display_name or entry.unavailable_reason or "",
        playing_level=LEVEL_LABELS.get(entry.playing_level or "", ""),
        area_name=entry.area_name or "",
        slots=tuple(_slot_view(slot) for slot in entry.slots),
        no_slots_reason=entry.no_slots_reason or "",
        unavailable_reason=entry.unavailable_reason or "",
        is_resolvable=resolvable,
        added_text=local_date_text(entry.created_at),
    )


def favorite_views(entries) -> list[FavoriteView]:
    return [favorite_view(entry) for entry in entries]
