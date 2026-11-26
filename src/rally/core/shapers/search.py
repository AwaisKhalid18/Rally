"""Public view models for a search result (ASR-04, ASR-13).

A result card carries everything needed to decide — availability, approximate distance
and playing level together — so no follow-up call per player is needed (ASR-13).

Distance is rounded to the nearest kilometre and labelled approximate (PRD §12.1,
ASR-03). When it cannot be worked out it is **absent with a reason**, never 0 and never
a placeholder (rule 13, FE-6).
"""
from __future__ import annotations

from dataclasses import dataclass

from rally.core.shapers.availability import SlotView
from rally.core.localtime import local_date_text, local_time_text, to_local
from rally.modules.search.api.facade import Match

DISTANCE_UNAVAILABLE = "Distance is not available for this player."


def _slot_view(slot) -> SlotView:
    return SlotView(
        slot_id=0,  # a matched slot is shown, never acted on from here
        date_text=local_date_text(slot.starts_at),
        start_text=local_time_text(slot.starts_at),
        end_text=local_time_text(slot.ends_at),
        day_text=to_local(slot.starts_at).strftime("%a"),
    )


@dataclass(frozen=True)
class ResultView:
    account_id: int
    display_name: str
    playing_level: str
    area_name: str
    slots: tuple[SlotView, ...]
    distance_text: str | None
    distance_reason: str | None


def result_view(match: Match) -> ResultView:
    if match.distance_km is None:
        distance_text, distance_reason = None, DISTANCE_UNAVAILABLE
    else:
        distance_text = f"about {round(match.distance_km)} km away"
        distance_reason = None

    return ResultView(
        account_id=match.account_id,
        display_name=match.display_name,
        playing_level=match.playing_level.capitalize(),
        area_name=match.area_name,
        slots=tuple(_slot_view(slot) for slot in match.overlapping_slots),
        distance_text=distance_text,
        distance_reason=distance_reason,
    )


def result_views(matches) -> list[ResultView]:
    return [result_view(match) for match in matches]
