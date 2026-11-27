"""M6's table: `block`.

`block` is a directed relationship: `blocker` has blocked `blocked`. The *effect* is
symmetric — neither player sees the other — but that symmetry belongs to the rule M6
publishes, not to the row (PRD §12.5).

`report` is write-only as far as players are concerned. M6 publishes no way to read one
back: reports are "stored for review by the project administrators" (PRD §12.5), review
happens directly in the database, and there is no admin screen (AGENTS.md §5, an
accepted limitation).

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


class ReportCategory(models.TextChoices):
    """The list the PRD leaves open; AGENTS.md §9 **G-13** proposes exactly these four
    and they are not yet confirmed by the client."""

    HARASSMENT = "harassment", "Harassment"
    FAKE_PROFILE = "fake_profile", "Fake profile"
    INAPPROPRIATE_CONTENT = "inappropriate_content", "Inappropriate content"
    OTHER = "other", "Other"


DETAILS_MAX_LENGTH = 1000


class Report(models.Model):
    """One player's report about another (PRD §12.5, FR-14).

    Free-text `details` is optional. Nothing here is ever shown to a player, not even to
    the reporter: a report that could be read back would turn into a channel between the
    two players, and there is no chat in Rally (§7).
    """

    reporter_account_id = models.BigIntegerField(db_index=True)
    reported_account_id = models.BigIntegerField(db_index=True)
    category = models.CharField(max_length=32, choices=ReportCategory.choices)
    details = models.TextField(blank=True, default="")
    # The invitation the report was made from, when it was made from one. A plain
    # integer, never a relation to M5's table (AGENTS.md §3.1).
    invitation_id = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(default=clock.now, editable=False)

    class Meta:
        db_table = "report"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(reporter_account_id=models.F("reported_account_id")),
                name="report_not_self",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"report:{self.pk}"
