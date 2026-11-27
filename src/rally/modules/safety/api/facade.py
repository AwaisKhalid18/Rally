"""M6 Safety — facade.

AGENTS.md §3 lists `block`, `unblock`, `isBlockedBetween`, `report`, `v_block_pairs` and
the `PendingInvitationCanceller` port. S5 published what search needs; **S12 publishes
the rest**, together with the cascade and the screens.

M6 never applies a block. It publishes the rule and M4, M5 and M8 apply it. M6 publishes
no way to **read** a report: reports are stored for the administrators to review in the
database, and a report a player could read back would become a message between the two
of them (PRD §12.5).
"""
from __future__ import annotations

from rally.modules.safety.internal import blocking
from rally.modules.safety.internal.models import DETAILS_MAX_LENGTH, ReportCategory

BLOCK_PAIRS_VIEW = "v_block_pairs"

BlockResult = blocking.BlockResult
BlockedPlayer = blocking.BlockedPlayer
ReportResult = blocking.ReportResult

CANNOT_BLOCK_YOURSELF = blocking.CANNOT_BLOCK_YOURSELF
ALREADY_BLOCKED = blocking.ALREADY_BLOCKED
NOT_BLOCKED = blocking.NOT_BLOCKED
CANNOT_REPORT_YOURSELF = blocking.CANNOT_REPORT_YOURSELF
CATEGORY_REQUIRED = blocking.CATEGORY_REQUIRED
CATEGORY_UNKNOWN = blocking.CATEGORY_UNKNOWN
DETAILS_TOO_LONG = blocking.DETAILS_TOO_LONG

# The four categories AGENTS.md §9 G-13 proposes. Published so the form offers exactly
# the list M6 will accept and the two can never drift apart.
REPORT_CATEGORIES = blocking.REPORT_CATEGORIES
REPORT_DETAILS_MAX_LENGTH = DETAILS_MAX_LENGTH


def is_blocked_between(first_account_id: int, second_account_id: int) -> bool:
    """True when either player has blocked the other. Symmetric, deliberately: a block
    hides the pair from each other in both directions (PRD §12.5)."""
    return blocking.is_blocked_between(first_account_id, second_account_id)


def block(blocker_account_id: int, blocked_account_id: int) -> BlockResult:
    """Block a player and cancel the pending invitations between the two, atomically.

    The cancellation crosses to M5 through the `PendingInvitationCanceller` port, inside
    M6's transaction (rule 15, ADR-007 R-02). Confirmed games are untouched.
    """
    return blocking.block(blocker_account_id, blocked_account_id)


def unblock(blocker_account_id: int, blocked_account_id: int) -> BlockResult:
    """Remove your own block. Visibility returns; cancelled invitations do not."""
    return blocking.unblock(blocker_account_id, blocked_account_id)


def list_blocked(blocker_account_id: int) -> list[BlockedPlayer]:
    """The players you have blocked, newest first. Never the ones who blocked you."""
    return blocking.list_blocked(blocker_account_id)


def report(
    reporter_account_id: int,
    reported_account_id: int,
    category: str,
    details: str = "",
    invitation_id: int | None = None,
) -> ReportResult:
    """Store a report: a category and optional free text (PRD §12.5, FR-14).

    Returns the new id, or a field -> message mapping. The reported player is not told.
    """
    return blocking.report(
        reporter_account_id, reported_account_id, category, details, invitation_id
    )
