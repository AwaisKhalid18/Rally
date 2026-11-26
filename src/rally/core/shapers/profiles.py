"""Public view models for M2 Profile.

A profile that is missing is reported with a reason, never as a blank card (rule 13,
FE-6). Nothing here can carry an email or a phone number: M2 does not hold them.
"""
from __future__ import annotations

from dataclasses import dataclass

from rally.modules.profiles.api.facade import PublicProfile

NO_PROFILE_YET = "This player has not set up their profile yet."


@dataclass(frozen=True)
class PublicProfileView:
    account_id: int
    display_name: str
    playing_level: str
    area_name: str


@dataclass(frozen=True)
class AbsentProfileView:
    account_id: int
    reason: str = NO_PROFILE_YET


def public_profile_view(account_id: int, profile: PublicProfile | None):
    if profile is None:
        return AbsentProfileView(account_id=account_id)
    return PublicProfileView(
        account_id=profile.account_id,
        display_name=profile.display_name,
        playing_level=profile.playing_level_label,
        area_name=profile.area_name,
    )
