"""Public view models for M3 Availability.

A slot is shown in the one configured display time zone; it is stored in UTC. Nothing
here can carry contact data or a location: M3 holds neither.
"""
from __future__ import annotations

from dataclasses import dataclass

from rally.core.localtime import local_date_text, local_time_text, to_local
from rally.modules.availability.api.facade import Slot

NO_SLOTS = "No available playing times yet."
NO_SLOTS_OTHER = "This player has not listed any available playing times."


@dataclass(frozen=True)
class SlotView:
    slot_id: int
    date_text: str
    start_text: str
    end_text: str
    day_text: str

    @property
    def summary(self) -> str:
        return f"{self.day_text} {self.date_text}, {self.start_text}-{self.end_text}"


def slot_view(slot: Slot) -> SlotView:
    return SlotView(
        slot_id=slot.slot_id,
        date_text=local_date_text(slot.starts_at),
        start_text=local_time_text(slot.starts_at),
        end_text=local_time_text(slot.ends_at),
        day_text=to_local(slot.starts_at).strftime("%a"),
    )


def slot_views(slots: list[Slot]) -> list[SlotView]:
    return [slot_view(slot) for slot in slots]
