"""M8's table: `favorite`.

**References, never copies (rule 11).** The row holds the owner, the favorited account
and when it was added. Nothing else — no display name, no playing level, no area, no
availability, no contact detail, no coordinate pair. Every display field is resolved
from the published read views on each request, so a favorite can never serve a stale
playing level or an area the other player has since changed (architecture §16.7).

The table is private to its owner. The favorited player is never told they are on a
list, and no view exposes one (§16.8).

`saved_search` arrives in S15.
"""
from __future__ import annotations

from django.db import models

from rally.core import clock


class Favorite(models.Model):
    """One player's entry on another player's list.

    Both ids are plain integers, not `ForeignKey`s: a relation would need an import of
    M1's model and break rule 2 (AGENTS.md §3.1). That also means a favorite can outlive
    the account it points at, which is deliberate — the list shows "no longer available"
    rather than silently losing a row (AC2, G-06).
    """

    owner_account_id = models.BigIntegerField(db_index=True)
    favorited_account_id = models.BigIntegerField(db_index=True)
    created_at = models.DateTimeField(default=clock.now, editable=False)

    class Meta:
        db_table = "favorite"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner_account_id", "favorited_account_id"],
                name="favorite_once_per_pair",
            ),
            models.CheckConstraint(
                condition=~models.Q(owner_account_id=models.F("favorited_account_id")),
                name="favorite_not_self",
            ),
        ]
        indexes = [
            models.Index(fields=["owner_account_id", "created_at"], name="favorite_owner_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover - never shown to a player
        return f"favorite:{self.owner_account_id}->{self.favorited_account_id}"
