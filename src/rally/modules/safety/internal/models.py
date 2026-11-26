"""M6's table: `block`.

A directed relationship: `blocker` has blocked `blocked`. The *effect* is symmetric —
neither player sees the other — but that symmetry belongs to the rule M6 publishes, not
to the row (PRD §12.5).

`report` arrives with S12.
"""
from __future__ import annotations

from django.db import models

from rally.core import clock


class Block(models.Model):
    blocker_account_id = models.BigIntegerField(db_index=True)
    blocked_account_id = models.BigIntegerField(db_index=True)
    created_at = models.DateTimeField(default=clock.now, editable=False)

    class Meta:
        db_table = "block"
        constraints = [
            models.UniqueConstraint(
                fields=["blocker_account_id", "blocked_account_id"], name="block_once_per_pair"
            ),
            models.CheckConstraint(
                condition=~models.Q(blocker_account_id=models.F("blocked_account_id")),
                name="block_not_self",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"block:{self.blocker_account_id}->{self.blocked_account_id}"
