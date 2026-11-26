"""M2's tables: `profile` and `area`.

`area` holds a name and a **centroid** - the centre of a district or neighbourhood, not a
player's position. There is no exact-location field here or anywhere else in the schema,
and adding one is forbidden (rule 7, ASR-03). Distance is derived per request from these
centroids and shown rounded and labelled approximate.

No contact data lives here. Email and phone belong to M1 (rule 6).
"""
from __future__ import annotations

from django.db import models


class PlayingLevel(models.TextChoices):
    """PRD §12.1: three self-reported levels, never assigned by the system."""

    BEGINNER = "beginner", "Beginner"
    INTERMEDIATE = "intermediate", "Intermediate"
    ADVANCED = "advanced", "Advanced"


# Ranking by "level closeness" (PRD §12.1) needs an order, not just a label. The rank is
# published alongside the label in `v_searchable_profile` so M4 never has to encode the
# ordering itself.
LEVEL_RANK = {
    PlayingLevel.BEGINNER: 1,
    PlayingLevel.INTERMEDIATE: 2,
    PlayingLevel.ADVANCED: 3,
}


class Area(models.Model):
    """One general area from the fixed list (`ops/seed/areas.csv`). No geocoding."""

    code = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=80)
    centroid_lat = models.DecimalField(max_digits=8, decimal_places=4)
    centroid_lon = models.DecimalField(max_digits=9, decimal_places=4)

    class Meta:
        db_table = "area"
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class Profile(models.Model):
    """A player's public profile.

    `account_id` is a plain integer, not a ForeignKey: a relation would need an import of
    M1's model and break rule 2 (AGENTS.md §3.1).
    """

    account_id = models.BigIntegerField(unique=True)
    display_name = models.CharField(max_length=40)
    playing_level = models.CharField(max_length=16, choices=PlayingLevel.choices)
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="profiles")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "profile"

    def __str__(self) -> str:  # pragma: no cover - never shown to a player
        return f"profile:{self.account_id}"
