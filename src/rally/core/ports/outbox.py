"""The `OutboxAppender` port (AGENTS.md rule 3, ADR-005).

M1, M5 and M6 must record a notification event atomically with the business state they
are changing, but none of them may import M7 and none of them may write M7's `outbox`
table. Platform declares this port, M7 implements it, and the wiring registry binds them
at startup.

The implementation is called **inside the caller's transaction** and must not open or
commit one of its own (rule 4). It performs no external call (rule 5): the provider is
reached later, by the worker.
"""
from __future__ import annotations

from typing import Any, Protocol

from rally.core.wiring import registry

OUTBOX_APPENDER = "OutboxAppender"

# Every event type Rally can raise. The key tells M7 which message to compose; the
# business module that appends it knows nothing about how it will be delivered.
EVENT_ACCOUNT_VERIFICATION_REQUESTED = "account.verification_requested"

# `entity_refs` carries identifiers only - never an email address, a phone number or any
# other private field (rule 6). It must name the account to notify.
RECIPIENT_KEY = "recipient_account_id"


class OutboxAppender(Protocol):
    def append(self, event_type: str, entity_refs: dict[str, Any]) -> int:
        """Record one event for later dispatch. Returns the outbox record id."""


def append_outbox(event_type: str, entity_refs: dict[str, Any]) -> int:
    """Convenience wrapper so a caller writes one line inside its transaction."""
    if RECIPIENT_KEY not in entity_refs:
        raise ValueError(f"entity_refs must name {RECIPIENT_KEY!r}")
    appender: OutboxAppender = registry.resolve(OUTBOX_APPENDER)
    return appender.append(event_type, entity_refs)


# Added by S7. The outbox carries the event and the ids it refers to — never the
# invitation's details. M7 composes a short message pointing at the in-app record,
# which is the source of truth for state (architecture §6.6, ASR-11).
EVENT_INVITATION_SENT = "invitation.sent"

# Added by S8. Both notify the **sender**: PRD §12.3 resolves that the sender is told
# when a recipient accepts or declines.
EVENT_INVITATION_ACCEPTED = "invitation.accepted"
EVENT_INVITATION_DECLINED = "invitation.declined"

# Added by S9. Told to the **recipient**: PRD §12.3 resolves that they are notified when
# a sender withdraws a pending invitation. Expiry notifies nobody — the PRD sends no
# reminders and no expiry notice.
EVENT_INVITATION_CANCELLED = "invitation.cancelled"

# Added by S11. Told to the **other participant**: PRD §12.4 resolves that they are
# informed by in-app notification and email when a confirmed game is cancelled. The
# player who cancelled is not notified of their own action.
EVENT_GAME_CANCELLED = "game.cancelled"

# Added by S12. The block cascade cancels the pending invitations between a pair, and
# the player who did **not** block is told that an invitation is gone. The wording M7
# and the shaper give it never says a block happened: the PRD does not resolve whether
# the blocked player learns of the block, and disclosing it would make blocking unsafe
# to use. A separate event type exists precisely so the wording can stay neutral -
# `invitation.cancelled` says "the player who sent it withdrew", which would be false
# here and would point straight at the block.
EVENT_INVITATION_CANCELLED_BY_BLOCK = "invitation.cancelled_by_block"
