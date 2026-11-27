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


class ConfirmedGame(models.Model):
    """The arrangement created the moment an invitation is accepted (PRD §12.3).

    It is a **separate record** from the invitation, which stays Accepted. The two are
    distinct concepts and the PRD forbids treating them as one (PRD §6.1).
    """

    invitation = models.OneToOneField(
        Invitation, on_delete=models.PROTECT, related_name="confirmed_game"
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    venue = models.CharField(max_length=100)
    created_at = models.DateTimeField(default=clock.now, editable=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by_account_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "confirmed_game"
        ordering = ["starts_at"]

    @property
    def is_cancelled(self) -> bool:
        return self.cancelled_at is not None

    def __str__(self) -> str:  # pragma: no cover
        return f"game:{self.pk}"


class GameParticipant(models.Model):
    """One row per player per confirmed game — the shape the invariant needs.

    `confirmed_game` holds both players on a single row, and a database exclusion
    constraint compares *rows*, so it could only ever protect one of them. Giving each
    player their own row lets one constraint say "no player has two overlapping games"
    (ADR-004; the gap the agent validation recorded as AV-05).

    `cancelled_at` mirrors the game's, so a cancelled game stops blocking time at once
    without deleting the history (PRD §12.4).
    """

    game = models.ForeignKey(ConfirmedGame, on_delete=models.CASCADE, related_name="participants")
    account_id = models.BigIntegerField(db_index=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "game_participant"
        constraints = [
            models.UniqueConstraint(fields=["game", "account_id"], name="participant_once_per_game"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"participant:{self.account_id}@{self.game_id}"
