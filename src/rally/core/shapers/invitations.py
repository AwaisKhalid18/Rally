"""Public view models for M5 Invitation & Games.

A participant sees the other party by **display name only** (AC5): no email, no phone,
and nothing becomes visible because an invitation exists (PRD §12.2, ASR-04).
"""
from __future__ import annotations

from dataclasses import dataclass

from rally.core.localtime import local_date_text, local_time_text, to_local
from rally.modules.invitations.api.facade import InvitationRecord

UNKNOWN_PLAYER = "A player who is no longer available"


@dataclass(frozen=True)
class InvitationView:
    invitation_id: int
    # The id is needed to offer blocking and reporting from the invitation (S12).
    # An account id is not private: it already appears in every profile URL.
    other_party_account_id: int
    other_party_name: str
    direction: str            # "sent" or "received"
    when_text: str
    venue: str
    status: str
    status_label: str
    expires_text: str
    is_pending: bool


def invitation_view(record: InvitationRecord, viewer_account_id: int, other_party_name: str | None) -> InvitationView:
    starts = to_local(record.starts_at)
    return InvitationView(
        invitation_id=record.invitation_id,
        other_party_account_id=record.other_party(viewer_account_id),
        # Rule 13: a name that cannot be resolved is replaced by a reason, not a blank.
        other_party_name=other_party_name or UNKNOWN_PLAYER,
        direction="sent" if record.was_sent_by(viewer_account_id) else "received",
        when_text=(
            f"{starts.strftime('%a')} {local_date_text(record.starts_at)}, "
            f"{local_time_text(record.starts_at)}-{local_time_text(record.ends_at)}"
        ),
        venue=record.venue,
        status=record.status,
        status_label=record.status_label,
        expires_text=(
            f"{local_date_text(record.expires_at)} {local_time_text(record.expires_at)}"
        ),
        is_pending=record.status == "pending",
    )
