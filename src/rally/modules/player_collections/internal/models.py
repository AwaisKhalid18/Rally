"""M8's tables: `favorite` and `saved_search`.

**References, never copies (rule 11).** The row holds the owner, the favorited account
and when it was added. Nothing else — no display name, no playing level, no area, no
availability, no contact detail, no coordinate pair. Every display field is resolved
from the published read views on each request, so a favorite can never serve a stale
playing level or an area the other player has since changed (architecture §16.7).

The table is private to its owner. The favorited player is never told they are on a
list, and no view exposes one (§16.8).

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


class DayRule(models.TextChoices):
    """How a saved search decides *which day* it is for (G-05, R-14).

    FR-18 says a saved search stores a date, but an absolute date goes stale the day
    after it passes, which makes a "reusable" search unusable. The resolution is to
    store **either** a fixed date or a rule that resolves to one at reuse time
    (AGENTS.md §5): today, tomorrow, or the next occurrence of a weekday.
    """

    TODAY = "today", "Today"
    TOMORROW = "tomorrow", "Tomorrow"
    MONDAY = "monday", "Next Monday"
    TUESDAY = "tuesday", "Next Tuesday"
    WEDNESDAY = "wednesday", "Next Wednesday"
    THURSDAY = "thursday", "Next Thursday"
    FRIDAY = "friday", "Next Friday"
    SATURDAY = "saturday", "Next Saturday"
    SUNDAY = "sunday", "Next Sunday"


NAME_MAX_LENGTH = 60


class SavedSearch(models.Model):
    """One player's named search criteria (FR-18, architecture §16.4, §16.7).

    **No coordinates (ASR-03).** The location is an `area_code`, a reference into M2's
    fixed list. The centroid distance needs is resolved from M2 at execution time, and
    storing the picked point as a latitude/longitude pair would put location data into
    the schema for the first time.

    **No copied profile data (rule 11).** These are the player's own criteria and
    nothing about anybody else.

    The time window is a time of day, not an instant: the date comes from `fixed_date`
    or from `day_rule` when the search is reused, so the same saved search means
    "Saturday evening" every week rather than one evening that has passed.
    """

    owner_account_id = models.BigIntegerField(db_index=True)
    name = models.CharField(max_length=NAME_MAX_LENGTH)
    # Exactly one of these two carries the day (G-05), enforced by a check constraint.
    fixed_date = models.DateField(null=True, blank=True)
    day_rule = models.CharField(max_length=16, choices=DayRule.choices, blank=True, default="")
    start_time = models.TimeField()
    end_time = models.TimeField()
    area_code = models.CharField(max_length=32)
    playing_level = models.CharField(max_length=16, blank=True, default="")
    max_distance_km = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(default=clock.now, editable=False)
    updated_at = models.DateTimeField(default=clock.now)

    class Meta:
        db_table = "saved_search"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner_account_id", "name"], name="saved_search_name_once_per_owner"
            ),
            # Exactly one way of saying which day: a fixed date or a rule, never both
            # and never neither (G-05).
            models.CheckConstraint(
                condition=(
                    models.Q(fixed_date__isnull=False, day_rule="")
                    | models.Q(fixed_date__isnull=True)
                    & ~models.Q(day_rule="")
                ),
                name="saved_search_one_day_source",
            ),
        ]
        indexes = [
            models.Index(fields=["owner_account_id", "updated_at"], name="saved_search_owner_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"saved_search:{self.pk}"
