"""M3 Availability — facade.

Published (AGENTS.md §3): `has_availability`, `list_slots`, `remove_expired_slots`, and
the read view `v_active_availability`. S4 adds the owner-side operations the availability
screen needs.

M3 answers questions about time. It never decides whether a game may be confirmed — M5
asks, M5 decides (architecture §5).
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from rally.core import clock
from rally.modules.availability.internal import rules
from rally.modules.availability.internal.models import AvailabilitySlot

END_BEFORE_START = rules.END_BEFORE_START
ALREADY_PASSED = rules.ALREADY_PASSED
OVERLAPS_OWN_SLOT = rules.OVERLAPS_OWN_SLOT
NOT_YOURS = rules.NOT_YOURS
NOT_FOUND = rules.NOT_FOUND

ACTIVE_AVAILABILITY_VIEW = "v_active_availability"


@dataclass(frozen=True)
class Slot:
    """One slot as any caller may see it. Carries no contact data — M3 has none."""

    slot_id: int
    account_id: int
    starts_at: _dt.datetime
    ends_at: _dt.datetime


@dataclass(frozen=True)
class SlotResult:
    slot_id: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _as_slot(row: AvailabilitySlot) -> Slot:
    return Slot(
        slot_id=row.pk,
        account_id=row.account_id,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
    )


def add_slot(account_id: int, starts_at, ends_at) -> SlotResult:
    result = rules.add(account_id, starts_at, ends_at)
    return SlotResult(slot_id=result.slot_id, error=result.error)


def edit_slot(account_id: int, slot_id: int, starts_at, ends_at) -> SlotResult:
    result = rules.edit(account_id, slot_id, starts_at, ends_at)
    return SlotResult(slot_id=result.slot_id, error=result.error)


def remove_slot(account_id: int, slot_id: int) -> SlotResult:
    result = rules.remove(account_id, slot_id)
    return SlotResult(slot_id=result.slot_id, error=result.error)


def get_slot(account_id: int, slot_id: int) -> Slot | None:
    """The owner's own slot, for the edit form. None when it is missing or not theirs."""
    row = AvailabilitySlot.objects.filter(pk=slot_id, account_id=account_id).first()
    return _as_slot(row) if row else None


def list_slots(account_id: int, include_past: bool = False) -> list[Slot]:
    """A player's slots, earliest first. Past slots are left out unless asked for."""
    query = AvailabilitySlot.objects.filter(account_id=account_id)
    if not include_past:
        query = query.filter(ends_at__gt=clock.now())
    return [_as_slot(row) for row in query]


def has_availability(account_id: int, starts_at, ends_at) -> bool:
    """Is the player free for the whole of [starts_at, ends_at)?

    One slot must cover the window; two adjoining slots do not add up, because a game is
    a single continuous booking. M5 calls this when an invitation is sent and again when
    it is accepted (PRD §12.4, ASR-08).
    """
    return AvailabilitySlot.objects.filter(
        account_id=account_id, starts_at__lte=starts_at, ends_at__gte=ends_at
    ).exists()


def remove_expired_slots() -> int:
    """Called by the worker's sweep. Returns how many slots were removed."""
    return rules.remove_expired()
