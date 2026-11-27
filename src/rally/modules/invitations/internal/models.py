"""M5's table: `invitation`.

`confirmed_game` and `game_participant` arrive with S8, when acceptance creates a game.
They are deliberately absent until then: an invitation reserves nothing, and only a
confirmed game blocks time (PRD §12.4).

Times are stored as two `timestamptz` instants, as everywhere else (AGENTS.md §5 [v5]).
`venue` is free text (PRD §12.3) and no part of this schema holds a location (rule 7).
"""
from __future__ import annotations

from django.db import models

from rally.core import clock


class InvitationStatus(models.TextChoices):
    """PRD §12.3. Pending is the only non-terminal status; the other four are final.

    Nothing outside M5 may change a status (AGENTS.md §3).
    """

    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    DECLINED = "declined", "Declined"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


TERMINAL_STATUSES = frozenset(
    {
        InvitationStatus.ACCEPTED,
        InvitationStatus.DECLINED,
        InvitationStatus.EXPIRED,
        InvitationStatus.CANCELLED,
    }
)


class Invitation(models.Model):
    """One player's request to another to play at a given time and place.

    `sender_account_id` and `recipient_account_id` are plain integers, not ForeignKeys:
    a relation would need an import of M1's model and break rule 2 (AGENTS.md §3.1).
    """

    sender_account_id = models.BigIntegerField(db_index=True)
    recipient_account_id = models.BigIntegerField(db_index=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    venue = models.CharField(max_length=100)
    status = models.CharField(
        max_length=16, choices=InvitationStatus.choices, default=InvitationStatus.PENDING
    )
    created_at = models.DateTimeField(default=clock.now, editable=False)
    # min(created + 24h, proposed start), stamped from the server clock at creation.
    # It is re-evaluated at every transition, so a late sweep can never let an expired
    # invitation be acted on (ASR-09, ADR-005).
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "invitation"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient_account_id", "status"], name="invitation_inbox_idx"),
            models.Index(fields=["sender_account_id", "status"], name="invitation_sent_idx"),
            models.Index(fields=["status", "expires_at"], name="invitation_expiry_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover - never shown to a player
        return f"invitation:{self.pk}"
