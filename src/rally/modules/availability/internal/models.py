"""M3's table: `availability_slot`.

Individual date-and-time slots. There is no recurrence in the MVP (PRD §12.1), so there
is no rule, no schedule and no repeat field here.

Architecture §5 describes the row as "(account ref, date, start, end)". It is stored as
two `timestamptz` instants instead: AGENTS.md §5 [v5] requires every timestamp to be
stored in UTC, and overlap and expiry are comparisons between instants, not between a
date and two wall-clock times. The local date a player typed is derived back for display
at the Platform edge; nothing is lost.
"""
from __future__ import annotations

from django.db import models

from rally.core import clock


class AvailabilitySlot(models.Model):
    """One window in which a player is willing to play.

    `account_id` is a plain integer, not a ForeignKey: a relation would need an import of
    M1's model and break rule 2 (AGENTS.md §3.1).
    """

    account_id = models.BigIntegerField(db_index=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    created_at = models.DateTimeField(default=clock.now, editable=False)

    class Meta:
        db_table = "availability_slot"
        ordering = ["starts_at"]
        indexes = [
            # The search path asks "whose slot overlaps this window?" (ASR-01).
            models.Index(fields=["starts_at", "ends_at"], name="availability_window_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover - never shown to a player
        return f"slot:{self.pk}"
