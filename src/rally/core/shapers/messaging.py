"""Public view models for M9 Messaging.

A conversation shows the other player by **display name only** — the same public field
every other screen shows. M9 holds no contact data and refuses to store a message that
looks like it carries any, so there are two barriers on this path as well (rule 6).
"""
from __future__ import annotations

from dataclasses import dataclass

from rally.core.localtime import local_date_text, local_time_text, to_local

UNKNOWN_PLAYER = "A player who is no longer available"


@dataclass(frozen=True)
class ConversationView:
    conversation_id: int
    other_party_name: str
    other_party_account_id: int
    preview: str
    when_text: str
    unread_count: int
    has_unread: bool


@dataclass(frozen=True)
class MessageView:
    message_id: int
    body: str
    when_text: str
    is_mine: bool
    author: str


def _when(instant) -> str:
    if instant is None:
        return ""
    return f"{local_date_text(instant)} {local_time_text(instant)}"


def conversation_view(record, profile) -> ConversationView:
    return ConversationView(
        conversation_id=record.conversation_id,
        # Rule 13: a name that cannot be resolved becomes a reason, not a blank.
        other_party_name=profile.display_name if profile else UNKNOWN_PLAYER,
        other_party_account_id=record.other_party_account_id,
        preview=record.last_message_body or "No messages yet.",
        when_text=_when(record.last_message_at),
        unread_count=record.unread_count,
        has_unread=record.unread_count > 0,
    )


def conversation_views(records, profiles_by_id) -> list[ConversationView]:
    return [
        conversation_view(record, profiles_by_id.get(record.other_party_account_id))
        for record in records
    ]


def message_view(record, viewer_account_id: int) -> MessageView:
    mine = record.was_sent_by(viewer_account_id)
    return MessageView(
        message_id=record.message_id,
        body=record.body,
        when_text=_when(record.sent_at),
        is_mine=mine,
        author="You" if mine else "Them",
    )


def message_views(records, viewer_account_id: int) -> list[MessageView]:
    return [message_view(record, viewer_account_id) for record in records]
