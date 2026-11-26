"""M3's slot rules.

What makes a slot acceptable is decided here, not in a Platform form (rule 14). Every
comparison uses the server clock in UTC; a time the player typed is only ever an input,
never the authority for a state change (rule 8).
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from django.db import IntegrityError, transaction

from rally.core import clock
from rally.modules.availability.internal.models import AvailabilitySlot

END_BEFORE_START = "The end time must be after the start time."
ALREADY_PASSED = "That slot has already ended. Choose a time in the future."
OVERLAPS_OWN_SLOT = "That overlaps one of your own slots. Change the time or edit the existing slot."
NOT_YOURS = "That slot is not yours."
NOT_FOUND = "That slot no longer exists."

# The database constraint uses the half-open range [start, end), so a slot that ends
# exactly when the next one starts does not overlap it. Back-to-back slots are fine.
_OVERLAP_CONSTRAINT = "availability_slot_no_overlap"


@dataclass(frozen=True)
class SlotResult:
    slot_id: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _validate(starts_at: _dt.datetime, ends_at: _dt.datetime) -> str | None:
    if ends_at <= starts_at:
        return END_BEFORE_START
    # "Already ended" is judged by the end, not the start: a slot that is under way is
    # still usable (PRD §12.1 - a slot is valid until its end time passes).
    if ends_at <= clock.now():
        return ALREADY_PASSED
    return None


def _overlaps(account_id: int, starts_at, ends_at, exclude_id: int | None = None) -> bool:
    """The readable half of the check. The database constraint is the backstop that
    actually holds under concurrency - this exists so the player gets a sentence rather
    than a constraint error."""
    query = AvailabilitySlot.objects.filter(
        account_id=account_id, starts_at__lt=ends_at, ends_at__gt=starts_at
    )
    if exclude_id is not None:
        query = query.exclude(pk=exclude_id)
    return query.exists()


def add(account_id: int, starts_at, ends_at) -> SlotResult:
    error = _validate(starts_at, ends_at)
    if error:
        return SlotResult(error=error)
    if _overlaps(account_id, starts_at, ends_at):
        return SlotResult(error=OVERLAPS_OWN_SLOT)

    try:
        with transaction.atomic():
            slot = AvailabilitySlot.objects.create(
                account_id=account_id, starts_at=starts_at, ends_at=ends_at
            )
    except IntegrityError as raised:
        if _OVERLAP_CONSTRAINT in str(raised):
            return SlotResult(error=OVERLAPS_OWN_SLOT)
        raise
    return SlotResult(slot_id=slot.pk)


def edit(account_id: int, slot_id: int, starts_at, ends_at) -> SlotResult:
    """Only the owner may change a slot. M3 authorises its own records (ADR-003)."""
    slot = AvailabilitySlot.objects.filter(pk=slot_id).first()
    if slot is None:
        return SlotResult(error=NOT_FOUND)
    if slot.account_id != account_id:
        return SlotResult(error=NOT_YOURS)

    error = _validate(starts_at, ends_at)
    if error:
        return SlotResult(error=error)
    if _overlaps(account_id, starts_at, ends_at, exclude_id=slot_id):
        return SlotResult(error=OVERLAPS_OWN_SLOT)

    try:
        with transaction.atomic():
            AvailabilitySlot.objects.filter(pk=slot_id).update(
                starts_at=starts_at, ends_at=ends_at
            )
    except IntegrityError as raised:
        if _OVERLAP_CONSTRAINT in str(raised):
            return SlotResult(error=OVERLAPS_OWN_SLOT)
        raise
    return SlotResult(slot_id=slot_id)


def remove(account_id: int, slot_id: int) -> SlotResult:
    slot = AvailabilitySlot.objects.filter(pk=slot_id).first()
    if slot is None:
        return SlotResult(error=NOT_FOUND)
    if slot.account_id != account_id:
        return SlotResult(error=NOT_YOURS)
    AvailabilitySlot.objects.filter(pk=slot_id).delete()
    return SlotResult(slot_id=slot_id)


def remove_expired() -> int:
    """PRD §12.1: a slot is valid until its end time passes, then it is removed.

    A slot ending exactly now counts as passed. The sweep keeps the stored data tidy;
    `v_active_availability` filters by time as well, so a late sweep never shows a
    stale slot (ADR-005: a stalled worker degrades freshness, never correctness).
    """
    removed, _ = AvailabilitySlot.objects.filter(ends_at__lte=clock.now()).delete()
    return removed
