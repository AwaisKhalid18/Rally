"""M9's tables: `conversation` and `message`.

A conversation is between exactly two players. The pair is stored **ordered** — the
lower account id first — so one pair can only ever have one conversation, and a unique
constraint can say so.

Neither table carries contact data. A message holds the words a player typed, and M9
refuses to store any that look like an email address or a phone number, so rule 6 holds
on this path too: contact details stay inside M1 and never travel between players.
"""
from __future__ import annotations

from django.db import models

from rally.core import clock

BODY_MAX_LENGTH = 1000


class Conversation(models.Model):
    """The thread between two players who have a confirmed game.

    Both ids are plain integers, not `ForeignKey`s: a relation would need an import of
    M1's model and break rule 2 (AGENTS.md §3.1).
    """

    # Always stored with lower_account_id < higher_account_id, so the pair is unique
    # whichever way round the two players arrive.
    lower_account_id = models.BigIntegerField(db_index=True)
    higher_account_id = models.BigIntegerField(db_index=True)
    created_at = models.DateTimeField(default=clock.now, editable=False)
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "conversation"
        ordering = ["-last_message_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["lower_account_id", "higher_account_id"],
                name="conversation_once_per_pair",
            ),
            models.CheckConstraint(
                condition=models.Q(lower_account_id__lt=models.F("higher_account_id")),
                name="conversation_pair_is_ordered",
            ),
        ]

    def other_party(self, account_id: int) -> int:
        return (
            self.higher_account_id
            if account_id == self.lower_account_id
            else self.lower_account_id
        )

    def includes(self, account_id: int) -> bool:
        return account_id in (self.lower_account_id, self.higher_account_id)

    def __str__(self) -> str:  # pragma: no cover
        return f"conversation:{self.lower_account_id}+{self.higher_account_id}"


class Message(models.Model):
    """One message. The words are the player's; nothing else is stored.

    `read_at` is the *recipient's* — a message has exactly one of each, so a single
    column is enough and no join is needed to count what is unread.
    """

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    sender_account_id = models.BigIntegerField(db_index=True)
    body = models.CharField(max_length=BODY_MAX_LENGTH)
    sent_at = models.DateTimeField(default=clock.now, editable=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "message"
        ordering = ["sent_at", "id"]
        indexes = [
            models.Index(fields=["conversation", "sent_at"], name="message_thread_idx"),
            models.Index(fields=["sender_account_id", "read_at"], name="message_unread_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"message:{self.pk}"
