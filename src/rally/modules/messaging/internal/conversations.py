"""Conversations and messages, and the three rules that bound them.

**1. A conversation exists only where a confirmed game does.** Chat is for arranging a
game the two players have already agreed to play — not a channel to anyone a search
turned up. M9 asks M5; it does not decide this itself and it does not read M5's tables.

**2. A block closes it, both directions.** The same rule M4, M5 and M8 apply (ASR-10).
A blocked pair cannot open a conversation, cannot post to one they already had, and
do not see it in their list. The history is not deleted — unblocking restores it, the
way unblocking restores visibility everywhere else.

**3. A message may not carry contact data.** This is the one that matters. Rule 6 and
ASR-04 keep email and phone inside M1, and two independent barriers enforce that: the
data lives only in M1, and every response is built from a public view model. A free-text
box between two players goes around both, by hand. So M9 refuses a message that looks
like it carries an address or a number, and says why.

That check is deliberately blunt. It will sometimes refuse a message that was innocent,
and it cannot stop somebody determined to spell a number out in words. It is a guard
rail, not a proof, and it is recorded as such.
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.db.models import Q

from rally.core import clock
from rally.core.logging import log_operation
from rally.modules.invitations.api import facade as invitations
from rally.modules.messaging.internal.models import (
    BODY_MAX_LENGTH,
    Conversation,
    Message,
)
from rally.modules.safety.api import facade as safety

NO_CONFIRMED_GAME = (
    "You can only message a player you have a confirmed game with. "
    "Send them an invitation first."
)
CANNOT_MESSAGE_YOURSELF = "You cannot message yourself."
BLOCKED = "You cannot message that player."
NOT_FOUND = "No such conversation."
BODY_REQUIRED = "Write something first."
BODY_TOO_LONG = f"Keep a message under {BODY_MAX_LENGTH} characters."
LOOKS_LIKE_CONTACT_DATA = (
    "Rally does not pass on email addresses or phone numbers, so this message was not "
    "sent. Arrange the game here instead."
)

# Rule 6's guard rail. An address is unmistakable; a number is any run of digits long
# enough to dial, however it is spaced, bracketed or dashed.
_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_PHONE = re.compile(r"(?:\+?\d[\s().-]*){9,}")


@dataclass(frozen=True)
class MessageRecord:
    message_id: int
    sender_account_id: int
    body: str
    sent_at: _dt.datetime
    is_read: bool

    def was_sent_by(self, account_id: int) -> bool:
        return self.sender_account_id == account_id


@dataclass(frozen=True)
class ConversationRecord:
    conversation_id: int
    other_party_account_id: int
    last_message_at: _dt.datetime | None
    last_message_body: str
    unread_count: int


@dataclass(frozen=True)
class PostResult:
    message_id: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class OpenResult:
    conversation_id: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _ordered(first: int, second: int) -> tuple[int, int]:
    return (first, second) if first < second else (second, first)


def carries_contact_data(body: str) -> bool:
    """True when the text looks like it holds an address or a dialable number."""
    return bool(_EMAIL.search(body) or _PHONE.search(body))


def _may_talk(first: int, second: int) -> str | None:
    """The two rules about *whether* a pair may have a conversation at all."""
    if first == second:
        return CANNOT_MESSAGE_YOURSELF
    if safety.is_blocked_between(first, second):
        # Same answer as a pair with no game: nothing here confirms a block (ASR-05).
        return BLOCKED
    if not invitations.have_confirmed_game_between(first, second):
        return NO_CONFIRMED_GAME
    return None


def open_conversation(account_id: int, other_account_id: int) -> OpenResult:
    """Find or start the conversation between two players.

    Idempotent: asking twice returns the same conversation, which is what a "Message"
    button needs.
    """
    refusal = _may_talk(account_id, other_account_id)
    if refusal:
        return OpenResult(error=refusal)

    lower, higher = _ordered(account_id, other_account_id)
    existing = Conversation.objects.filter(
        lower_account_id=lower, higher_account_id=higher
    ).first()
    if existing is not None:
        return OpenResult(conversation_id=existing.pk)

    try:
        # A savepoint: losing the race to the unique constraint must leave the caller's
        # transaction usable, and both players pressing Message at once is ordinary.
        with transaction.atomic():
            created = Conversation.objects.create(
                lower_account_id=lower, higher_account_id=higher, created_at=clock.now()
            )
    except IntegrityError:
        created = Conversation.objects.get(
            lower_account_id=lower, higher_account_id=higher
        )

    log_operation("message.conversation", "opened", account_id=account_id)
    return OpenResult(conversation_id=created.pk)


def _for_participant(conversation_id: int, account_id: int) -> Conversation | None:
    row = Conversation.objects.filter(pk=conversation_id).first()
    if row is None or not row.includes(account_id):
        # A stranger gets the same answer as for one that does not exist (ASR-05).
        return None
    return row


def post_message(conversation_id: int, sender_account_id: int, body: str) -> PostResult:
    """Say something. Every rule is re-checked here, not just when the thread opened."""
    text = (body or "").strip()
    if not text:
        return PostResult(error=BODY_REQUIRED)
    if len(text) > BODY_MAX_LENGTH:
        return PostResult(error=BODY_TOO_LONG)
    if carries_contact_data(text):
        # Refused before it is stored, so the address never reaches the database either.
        log_operation("message.post", "rejected", account_id=sender_account_id, reason="contact")
        return PostResult(error=LOOKS_LIKE_CONTACT_DATA)

    conversation = _for_participant(conversation_id, sender_account_id)
    if conversation is None:
        return PostResult(error=NOT_FOUND)

    other = conversation.other_party(sender_account_id)
    # Re-checked at post time: a block, or a cancelled game, since the thread opened.
    refusal = _may_talk(sender_account_id, other)
    if refusal:
        return PostResult(error=refusal)

    now = clock.now()
    with transaction.atomic():
        message = Message.objects.create(
            conversation=conversation,
            sender_account_id=sender_account_id,
            body=text,
            sent_at=now,
        )
        Conversation.objects.filter(pk=conversation_id).update(last_message_at=now)

    log_operation("message.post", "sent", account_id=sender_account_id)
    return PostResult(message_id=message.pk)


def list_messages(conversation_id: int, account_id: int) -> list[MessageRecord] | None:
    """The thread, oldest first. `None` when it is not this player's."""
    conversation = _for_participant(conversation_id, account_id)
    if conversation is None:
        return None
    return [
        MessageRecord(
            message_id=row.pk,
            sender_account_id=row.sender_account_id,
            body=row.body,
            sent_at=row.sent_at,
            is_read=row.read_at is not None,
        )
        for row in conversation.messages.all()
    ]


def other_party(conversation_id: int, account_id: int) -> int | None:
    conversation = _for_participant(conversation_id, account_id)
    return None if conversation is None else conversation.other_party(account_id)


def mark_read(conversation_id: int, account_id: int) -> int:
    """Mark what the *other* player sent as read. Never your own messages."""
    conversation = _for_participant(conversation_id, account_id)
    if conversation is None:
        return 0
    return Message.objects.filter(
        conversation_id=conversation_id, read_at__isnull=True
    ).exclude(sender_account_id=account_id).update(read_at=clock.now())


def _visible_pairs(account_id: int):
    """This player's conversations, minus any that a block has closed (ASR-10)."""
    rows = Conversation.objects.filter(
        Q(lower_account_id=account_id) | Q(higher_account_id=account_id)
    )
    return [row for row in rows if not safety.is_blocked_between(account_id, row.other_party(account_id))]


def list_conversations(account_id: int) -> list[ConversationRecord]:
    """Newest activity first, with what is unread."""
    records = []
    for row in _visible_pairs(account_id):
        last = row.messages.order_by("-sent_at", "-id").first()
        unread = (
            Message.objects.filter(conversation=row, read_at__isnull=True)
            .exclude(sender_account_id=account_id)
            .count()
        )
        records.append(
            ConversationRecord(
                conversation_id=row.pk,
                other_party_account_id=row.other_party(account_id),
                last_message_at=row.last_message_at,
                last_message_body=last.body if last else "",
                unread_count=unread,
            )
        )
    records.sort(key=lambda r: (r.last_message_at is not None, r.last_message_at), reverse=True)
    return records


def unread_count(account_id: int) -> int:
    """Everything unread across this player's visible conversations — the nav badge."""
    return sum(record.unread_count for record in list_conversations(account_id))


def conversation_with(account_id: int, other_account_id: int) -> int | None:
    """The existing conversation between two players, if there is one and it is open."""
    if safety.is_blocked_between(account_id, other_account_id):
        return None
    lower, higher = _ordered(account_id, other_account_id)
    row = Conversation.objects.filter(
        lower_account_id=lower, higher_account_id=higher
    ).first()
    return None if row is None else row.pk
