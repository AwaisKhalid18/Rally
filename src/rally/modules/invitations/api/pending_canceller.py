"""M5's implementation of M6's `PendingInvitationCanceller` port (rule 15, ADR-007 R-02).

M6 must cancel the pending invitations between a pair when one blocks the other, and it
may not import M5. M6 declares the port, this implements it, and Platform's startup
wiring binds them. The source dependency stays `invitations → safety`, which the
allowlist grants; nothing points the other way.

Three things this must not do:

* **Open a transaction.** It runs inside M6's (rule 4). M6 owns the invariant that the
  block and the cancellation commit together, so M6 owns the transaction.
* **Notify anybody.** M6 appends the outbox records, because M6 is the module that knows
  a block caused this and can word it without disclosing the block. That is why the ids
  come back from here.
* **Touch a confirmed game.** PRD §12.5: existing confirmed games are unaffected until
  either player cancels. Only *Pending* invitations are cancelled.

M5 still exclusively owns invitation state (ASR-07): this is M5's own code changing M5's
own rows. M6 asks; it does not reach in.
"""
from __future__ import annotations

from rally.modules.invitations.internal import cascade


class PendingInvitationCancellerImpl:
    def cancel_pending_between(
        self, first_account_id: int, second_account_id: int
    ) -> list[int]:
        return cascade.cancel_pending_between(first_account_id, second_account_id)


_canceller = PendingInvitationCancellerImpl()


def canceller() -> PendingInvitationCancellerImpl:
    return _canceller
