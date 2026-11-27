"""The block cascade, from M5's side (PRD §12.5, ASR-10, ADR-007 R-02).

Called through M6's port, **inside M6's transaction**. It therefore opens none of its
own (rule 4), makes no external call (rule 5) and notifies nobody — M6 does that.

Each row is re-read `FOR UPDATE` and re-judged, exactly as every other transition is, so
an invitation being accepted at the same moment either loses the race and is cancelled,
or wins it and is left Accepted. Whichever happens, the pair never ends up with a live
invitation and a block at the same time, and never with a cancelled invitation that
somehow produced a game (ASR-07, ASR-10).
"""
from __future__ import annotations

from django.db.models import Q

from rally.modules.invitations.internal.models import Invitation, InvitationStatus


def cancel_pending_between(first_account_id: int, second_account_id: int) -> list[int]:
    """Cancel every Pending invitation between the two players, either direction.

    Returns the ids actually cancelled, so M6 can append one outbox record each. An
    invitation already Accepted, Declined, Expired or Cancelled is left alone: nothing
    leaves a terminal status (ASR-07).
    """
    between = Q(
        sender_account_id=first_account_id, recipient_account_id=second_account_id
    ) | Q(sender_account_id=second_account_id, recipient_account_id=first_account_id)

    # The lock matters: an accept running at the same instant holds this row, so one of
    # the two waits and then sees the other's committed status.
    rows = list(
        Invitation.objects.select_for_update()
        .filter(between, status=InvitationStatus.PENDING)
        .order_by("pk")
    )
    if not rows:
        return []

    ids = [row.pk for row in rows]
    # Re-filtered on Pending: nothing can have changed them between the read and this
    # update, because the rows are locked, but the condition states the invariant rather
    # than relying on the lock alone.
    Invitation.objects.filter(pk__in=ids, status=InvitationStatus.PENDING).update(
        status=InvitationStatus.CANCELLED
    )
    return ids
