"""M2's profile rules.

What makes a display name acceptable, which levels exist, which areas are selectable and
what "complete" means all live here - not in a form and not in Platform (rule 14).
"""
from __future__ import annotations

from dataclasses import dataclass

from rally.modules.profiles.internal.models import Area, PlayingLevel, Profile
from rally.modules.profiles.internal.verification import account_is_verified

# G-12 input bounds, still open in AGENTS.md §9: the PRD does not state a length.
DISPLAY_NAME_MIN_LENGTH = 2
DISPLAY_NAME_MAX_LENGTH = 40

NAME_REQUIRED = "Enter a display name."
NAME_TOO_SHORT = f"Use at least {DISPLAY_NAME_MIN_LENGTH} characters."
NAME_TOO_LONG = f"Use at most {DISPLAY_NAME_MAX_LENGTH} characters."
LEVEL_REQUIRED = "Choose your playing level."
LEVEL_INVALID = "Choose Beginner, Intermediate or Advanced."
AREA_REQUIRED = "Choose your general area."
AREA_INVALID = "Choose a general area from the list."


@dataclass(frozen=True)
class Saved:
    account_id: int | None = None
    errors: dict[str, str] | None = None

    @property
    def ok(self) -> bool:
        return self.account_id is not None


def validate(display_name: str, playing_level: str, area_code: str) -> dict[str, str]:
    errors: dict[str, str] = {}

    name = (display_name or "").strip()
    if not name:
        errors["display_name"] = NAME_REQUIRED
    elif len(name) < DISPLAY_NAME_MIN_LENGTH:
        errors["display_name"] = NAME_TOO_SHORT
    elif len(name) > DISPLAY_NAME_MAX_LENGTH:
        errors["display_name"] = NAME_TOO_LONG

    if not playing_level:
        errors["playing_level"] = LEVEL_REQUIRED
    elif playing_level not in PlayingLevel.values:
        errors["playing_level"] = LEVEL_INVALID

    if not area_code:
        errors["area_code"] = AREA_REQUIRED
    elif not Area.objects.filter(code=area_code).exists():
        errors["area_code"] = AREA_INVALID

    return errors


def save(account_id: int, display_name: str, playing_level: str, area_code: str) -> Saved:
    errors = validate(display_name, playing_level, area_code)
    if errors:
        return Saved(errors=errors)

    Profile.objects.update_or_create(
        account_id=account_id,
        defaults={
            "display_name": display_name.strip(),
            "playing_level": playing_level,
            "area": Area.objects.get(code=area_code),
        },
    )
    return Saved(account_id=account_id, errors={})


def is_complete(account_id: int) -> bool:
    """PRD §12.1: complete means display name, playing level, general area **and** a
    verified email. The verification state is M1's, read through its published view.
    """
    has_profile = Profile.objects.filter(account_id=account_id).exclude(display_name="").exists()
    return has_profile and account_is_verified(account_id)
