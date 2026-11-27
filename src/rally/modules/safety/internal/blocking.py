"""Blocking, unblocking and reporting (PRD §12.5, FR-14, ASR-10).

Blocking is one transaction owned by M6 (architecture §8.4):

    BEGIN
      create the block row
      cancel every Pending invitation between the pair   (M5, through the port)
      append one outbox record per cancelled invitation
    COMMIT

The cascade is **inside** the transaction on purpose. A block that committed while the
cancellation failed would leave the pair with a live invitation they can still act on,
which is precisely the hole ASR-10 exists to close. Either both happen or neither does.

Confirmed games are untouched. PRD §12.5: "existing confirmed games are unaffected
until either player cancels." Blocking is not a way to get out of a game.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.db.models import F, Q

from rally.core.logging import log_operation
from rally.core.ports.outbox import (
    EVENT_INVITATION_CANCELLED_BY_BLOCK,
    RECIPIENT_KEY,
    append_outbox,
)
from rally.modules.safety.api.ports import pending_invitation_canceller
from rally.modules.safety.internal.models import (
    Block,
    DETAILS_MAX_LENGTH,
    Report,
    ReportCategory,
)

CANNOT_BLOCK_YOURSELF = "You cannot block yourself."
ALREADY_BLOCKED = "You have already blocked this player."
NOT_BLOCKED = "You have not blocked this player."

CANNOT_REPORT_YOURSELF = "You cannot report yourself."
CATEGORY_REQUIRED = "Choose a category."
CATEGORY_UNKNOWN = "Choose one of the categories offered."
DETAILS_TOO_LONG = f"Keep the details under {DETAILS_MAX_LENGTH} characters."

REPORT_CATEGORIES = tuple(ReportCategory.choices)


@dataclass(frozen=True)
class BlockResult:
    block_id: int | None = None
    cancelled_invitation_ids: tuple[int, ...] = ()
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class BlockedPlayer:
    blocked_account_id: int
    created_at: object


def _pair(first_account_id: int, second_account_id: int) -> Q:
    return Q(
        blocker_account_id=first_account_id, blocked_account_id=second_account_id
    ) | Q(blocker_account_id=second_account_id, blocked_account_id=first_account_id)


def is_blocked_between(first_account_id: int, second_account_id: int) -> bool:
    """True when **either** player has blocked the other (PRD §12.5)."""
    return Block.objects.filter(_pair(first_account_id, second_account_id)).exists()


def block(blocker_account_id: int, blocked_account_id: int) -> BlockResult:
    """Block a player, cancelling the pending invitations between the two (PRD §12.5).

    M6 cannot check that the other account exists — it depends on nothing — so the
    caller resolves the player first and M6 refuses only what it can judge itself.
    """
    if blocker_account_id == blocked_account_id:
        return BlockResult(error=CANNOT_BLOCK_YOURSELF)

    with transaction.atomic():
        if Block.objects.filter(
            blocker_account_id=blocker_account_id, blocked_account_id=blocked_account_id
        ).exists():
            # Re-blocking is refused rather than silently repeated: the cascade has
            # already run and running it again would notify a second time.
            return BlockResult(error=ALREADY_BLOCKED)

        row = Block.objects.create(
            blocker_account_id=blocker_account_id, blocked_account_id=blocked_account_id
        )

        # The call crosses to M5 at run time only. M6 holds no import of it (rule 15).
        cancelled = tuple(
            pending_invitation_canceller().cancel_pending_between(
                blocker_account_id, blocked_account_id
            )
        )

        # M6 appends, not M5: M6 is the module that knows a block caused this, and the
        # records must commit with the block (rule 3 — through Platform's port).
        #
        # Only the player who did **not** block is told, and the wording never says a
        # block happened. The PRD does not resolve whether the blocked player learns of
        # the block; disclosing it would make blocking unsafe to use, so this says only
        # that the invitation is gone.
        for invitation_id in cancelled:
            append_outbox(
                EVENT_INVITATION_CANCELLED_BY_BLOCK,
                {RECIPIENT_KEY: blocked_account_id, "invitation_id": invitation_id},
            )

    log_operation(
        "safety.block",
        "blocked",
        account_id=blocker_account_id,
        other_account_id=blocked_account_id,
        invitations_cancelled=len(cancelled),
    )
    return BlockResult(block_id=row.pk, cancelled_invitation_ids=cancelled)


def unblock(blocker_account_id: int, blocked_account_id: int) -> BlockResult:
    """Remove your own block (PRD §12.5).

    Visibility returns at once, because every consumer reads the rule live. Cancelled
    invitations are **not** restored: they reached a terminal status and nothing leaves
    one (PRD §12.5, ASR-07).
    """
    removed, _ = Block.objects.filter(
        blocker_account_id=blocker_account_id, blocked_account_id=blocked_account_id
    ).delete()
    if not removed:
        # Only your own block, and the same answer whether it was someone else's or
        # never existed.
        return BlockResult(error=NOT_BLOCKED)

    log_operation(
        "safety.unblock",
        "unblocked",
        account_id=blocker_account_id,
        other_account_id=blocked_account_id,
    )
    return BlockResult()


def list_blocked(blocker_account_id: int) -> list[BlockedPlayer]:
    """The blocked-players list AC3 unblocks from. Your own blocks only.

    A block somebody placed on you is deliberately absent: being told you were blocked
    is exactly what must not happen.
    """
    return [
        BlockedPlayer(blocked_account_id=row.blocked_account_id, created_at=row.created_at)
        for row in Block.objects.filter(blocker_account_id=blocker_account_id).order_by(
            "-created_at"
        )
    ]


@dataclass(frozen=True)
class ReportResult:
    report_id: int | None = None
    errors: dict[str, str] | None = None

    @property
    def ok(self) -> bool:
        return self.report_id is not None


def report(
    reporter_account_id: int,
    reported_account_id: int,
    category: str,
    details: str = "",
    invitation_id: int | None = None,
) -> ReportResult:
    """Store one report (PRD §12.5, FR-14).

    A category is required and free text is optional. Nothing is sent anywhere and the
    reported player is not told: a notification would turn a report into a message.
    """
    errors: dict[str, str] = {}
    if reporter_account_id == reported_account_id:
        errors["reported"] = CANNOT_REPORT_YOURSELF
    if not category:
        errors["category"] = CATEGORY_REQUIRED
    elif category not in ReportCategory.values:
        errors["category"] = CATEGORY_UNKNOWN
    details = (details or "").strip()
    if len(details) > DETAILS_MAX_LENGTH:
        errors["details"] = DETAILS_TOO_LONG
    if errors:
        return ReportResult(errors=errors)

    row = Report.objects.create(
        reporter_account_id=reporter_account_id,
        reported_account_id=reported_account_id,
        category=category,
        details=details,
        invitation_id=invitation_id,
    )
    # The ids and the category only: the free text is a player's own words about another
    # player and has no place in a log.
    log_operation(
        "safety.report",
        "stored",
        account_id=reporter_account_id,
        other_account_id=reported_account_id,
        category=category,
    )
    return ReportResult(report_id=row.pk)
