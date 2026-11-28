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

from rally.core.localtime import DATE_FORMAT, local_date_text, local_time_text, to_local
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


# --- Saved searches (S15) ----------------------------------------------------


@dataclass(frozen=True)
class SavedSearchView:
    saved_search_id: int
    name: str
    day_text: str
    when_text: str
    area_name: str
    level_text: str
    distance_text: str
    can_run: bool
    # "" when it can run; otherwise the reason, ready to print (G-05, FE-6).
    cannot_run_reason: str


def saved_search_view(record, area_names) -> SavedSearchView:
    if record.fixed_date is not None:
        # A plain date, already in the display time zone: it is formatted directly, not
        # through `local_date_text`, which converts an instant.
        day_text = record.fixed_date.strftime(DATE_FORMAT)
    else:
        day_text = record.day_rule_label

    return SavedSearchView(
        saved_search_id=record.saved_search_id,
        name=record.name,
        day_text=day_text,
        when_text=(
            f"{record.start_time.strftime('%H:%M')}-{record.end_time.strftime('%H:%M')}"
        ),
        # Rule 13: an area that is no longer on the list says so rather than vanishing.
        area_name=area_names.get(record.area_code) or "An area that is no longer listed",
        level_text=LEVEL_LABELS.get(record.playing_level, "Any level"),
        distance_text=(
            f"within {record.max_distance_km} km"
            if record.max_distance_km
            else "the default distance"
        ),
        can_run=record.can_run,
        cannot_run_reason=record.cannot_run_reason or "",
    )


def saved_search_views(records, area_names) -> list[SavedSearchView]:
    return [saved_search_view(record, area_names) for record in records]
