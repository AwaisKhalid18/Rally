"""Public view models for M1 Identity.

Deliberately tiny: an account id and a verification state. Email and phone exist only
inside M1 and appear in no view model (rule 6, ASR-04).
"""
from __future__ import annotations

from dataclasses import dataclass

from rally.modules.identity.api.facade import AccountSummary


@dataclass(frozen=True)
class ViewerView:
    """Everything a template or a response may know about the signed-in player."""

    account_id: int
    is_verified: bool

    @property
    def verification_notice(self) -> str | None:
        """Absent values carry a reason; they are never blank (rule 13, FE-6)."""
        if self.is_verified:
            return None
        return "Your email address is not verified yet."


def viewer_view(summary: AccountSummary) -> ViewerView:
    return ViewerView(account_id=summary.account_id, is_verified=summary.is_verified)
