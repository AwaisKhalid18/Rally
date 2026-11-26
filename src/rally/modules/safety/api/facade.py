"""M6 Safety — facade.

AGENTS.md §3 lists `block`, `unblock`, `isBlockedBetween`, `report`, `v_block_pairs` and
the `PendingInvitationCanceller` port. **Slice S5 publishes only what search needs**;
the rest arrives with S12, together with the cascade and the UI.

M6 never applies a block. It publishes the rule and M4 and M5 apply it.
"""
from __future__ import annotations

from django.db.models import Q

from rally.modules.safety.internal.models import Block

BLOCK_PAIRS_VIEW = "v_block_pairs"


def is_blocked_between(first_account_id: int, second_account_id: int) -> bool:
    """True when either player has blocked the other. Symmetric, deliberately: a block
    hides the pair from each other in both directions (PRD §12.5)."""
    return Block.objects.filter(
        Q(blocker_account_id=first_account_id, blocked_account_id=second_account_id)
        | Q(blocker_account_id=second_account_id, blocked_account_id=first_account_id)
    ).exists()


def block_for_test(blocker_account_id: int, blocked_account_id: int) -> int:
    """Create a block row.

    S5 needs blocked pairs to exist so the search predicate can be proved to honour
    them, but the blocking *feature* — its transaction, its cancellation cascade through
    the port, and its screens — belongs to S12. This is the narrow seam until then, and
    S12 replaces it with the real `block()`.
    """
    row, _ = Block.objects.get_or_create(
        blocker_account_id=blocker_account_id, blocked_account_id=blocked_account_id
    )
    return row.pk
