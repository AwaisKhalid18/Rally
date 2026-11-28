"""M9 Messaging — facade.

M9 is a leaf: nothing depends on it. These operations exist for Platform's web host.

Every rule lives here, not in the caller: who may talk to whom, what a block does, and
what a message may not contain. Platform collects the words and reports what M9 decided
(rule 14).
"""
from __future__ import annotations

from rally.modules.messaging.internal import conversations
from rally.modules.messaging.internal.models import BODY_MAX_LENGTH

ConversationRecord = conversations.ConversationRecord
MessageRecord = conversations.MessageRecord
OpenResult = conversations.OpenResult
PostResult = conversations.PostResult

MESSAGE_MAX_LENGTH = BODY_MAX_LENGTH

NO_CONFIRMED_GAME = conversations.NO_CONFIRMED_GAME
CANNOT_MESSAGE_YOURSELF = conversations.CANNOT_MESSAGE_YOURSELF
BLOCKED = conversations.BLOCKED
NOT_FOUND = conversations.NOT_FOUND
BODY_REQUIRED = conversations.BODY_REQUIRED
BODY_TOO_LONG = conversations.BODY_TOO_LONG
LOOKS_LIKE_CONTACT_DATA = conversations.LOOKS_LIKE_CONTACT_DATA


def open_conversation(account_id: int, other_account_id: int) -> OpenResult:
    """Find or start the thread with a player you have a confirmed game with.

    Idempotent, so a "Message" button can call it every time. Refused for yourself, for
    a blocked pair, and where there is no confirmed game.
    """
    return conversations.open_conversation(account_id, other_account_id)


def conversation_with(account_id: int, other_account_id: int) -> int | None:
    """An existing open thread with this player, or `None` — so a page can offer
    "Message" without opening one first."""
    return conversations.conversation_with(account_id, other_account_id)


def post_message(conversation_id: int, sender_account_id: int, body: str) -> PostResult:
    """Say something. Refused if it looks like it carries an email address or a phone
    number: contact data stays inside M1 (rule 6, ASR-04)."""
    return conversations.post_message(conversation_id, sender_account_id, body)


def list_messages(conversation_id: int, account_id: int) -> list[MessageRecord] | None:
    """The thread, oldest first. `None` for a non-participant, which the caller turns
    into a not-found (ASR-05)."""
    return conversations.list_messages(conversation_id, account_id)


def other_party(conversation_id: int, account_id: int) -> int | None:
    """Who the other player is, for a participant only."""
    return conversations.other_party(conversation_id, account_id)


def list_conversations(account_id: int) -> list[ConversationRecord]:
    """Your own threads, newest activity first. Blocked pairs are omitted."""
    return conversations.list_conversations(account_id)


def mark_read(conversation_id: int, account_id: int) -> int:
    """Mark what the other player sent as read. Returns how many."""
    return conversations.mark_read(conversation_id, account_id)


def unread_count(account_id: int) -> int:
    return conversations.unread_count(account_id)


def carries_contact_data(body: str) -> bool:
    """Published so a page can warn before sending, and so the rule has one home."""
    return conversations.carries_contact_data(body)
