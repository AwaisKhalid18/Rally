"""Public view models for M4's `compare()` (FR-17, ASR-04).

The same public fields a search result carries — display name, playing level, general
area, available times and an approximate distance. Nothing private, because the views
M4 reads hold nothing private (rules 6, 7).

Rule 13 is the whole job here: M4 hands over each field either resolved or **absent
with a reason**, and this turns that into text the page prints as it stands. "Clearly
indicate missing information" is a data-model rule, not a rendering one (§16.7), so the
reason is decided in M4 and only worded here.
"""
from __future__ import annotations

from dataclasses import dataclass

from rally.core.localtime import local_date_text, local_time_text, to_local
from rally.modules.search.api.facade import ComparedPlayer

LEVEL_LABELS = {
    "beginner": "Beginner",
    "intermediate": "Intermediate",
    "advanced": "Advanced",
}


@dataclass(frozen=True)
class ComparedSlotView:
    summary: str


@dataclass(frozen=True)
class ComparedPlayerView:
    account_id: int
    found: bool
    display_name: str
    playing_level: str
    area_name: str
    slots: tuple[ComparedSlotView, ...]
    # Each is "" when the field is present, and a printable reason when it is not.
    distance_text: str
    distance_reason: str
    no_slots_reason: str
    not_found_reason: str


def _slot_view(slot) -> ComparedSlotView:
    day = to_local(slot.starts_at).strftime("%a")
    return ComparedSlotView(
        summary=(
            f"{day} {local_date_text(slot.starts_at)}, "
            f"{local_time_text(slot.starts_at)}-{local_time_text(slot.ends_at)}"
        )
    )


def compared_player_view(player: ComparedPlayer) -> ComparedPlayerView:
    return ComparedPlayerView(
        account_id=player.account_id,
        found=player.found,
        display_name=player.display_name or "",
        playing_level=LEVEL_LABELS.get(player.playing_level or "", ""),
        area_name=player.area_name or "",
        slots=tuple(_slot_view(slot) for slot in player.slots),
        # Always labelled approximate: it is measured between area centres (rule 7).
        distance_text=(
            "" if player.distance_km is None
            else f"about {round(player.distance_km)} km away"
        ),
        distance_reason=player.no_distance_reason or "",
        no_slots_reason=player.no_slots_reason or "",
        not_found_reason=player.not_found_reason or "",
    )


def compared_player_views(players) -> list[ComparedPlayerView]:
    return [compared_player_view(player) for player in players]
