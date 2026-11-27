"""The `PendingInvitationCanceller` port — declared by M6, implemented by M5.

AGENTS.md §3 and rule 15, ADR-007 R-02.

Blocking must cancel the pending invitations between the two players (PRD §12.5), and
that must happen **inside M6's transaction**: a block that committed without the
cascade would leave an invitation the pair can still act on.

But M6 depends on nothing and may never import M5 (`safety → nothing`). So M6 declares
the shape of the call it needs, M5 implements it, and Platform's startup wiring binds
them. The source dependency runs one way — `invitations → safety` — and the call crosses
back at run time only through this port. There is no reverse import anywhere.

The implementation is called inside M6's transaction and must not open or commit one of
its own (rule 4), and must not notify anybody: M6 appends the outbox records, because
M6 is the module that knows a block caused this.
"""
from __future__ import annotations

from typing import Protocol

from rally.core.wiring import registry

PENDING_INVITATION_CANCELLER = "PendingInvitationCanceller"


class PendingInvitationCanceller(Protocol):
    def cancel_pending_between(
        self, first_account_id: int, second_account_id: int
    ) -> list[int]:
        """Cancel every Pending invitation between the two players, **either
        direction**, and return their ids.

        The ids come back so that M6 can append one outbox record per cancelled
        invitation without reading M5's tables (rule 1).
        """


def pending_invitation_canceller() -> PendingInvitationCanceller:
    """Resolve the implementation registered at startup.

    A `LookupError` here means the wiring is missing, which is a startup fault and not
    something to work around: the cascade is not optional (ASR-10).
    """
    return registry.resolve(PENDING_INVITATION_CANCELLER)
