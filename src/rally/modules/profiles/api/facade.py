"""M2 Profile — facade.

Published (AGENTS.md §3): `get_public_profile`, `is_complete`, and the read view
`v_searchable_profile`. S3 adds the owner-side operations the profile screen needs.

Nothing here returns a model instance, and nothing here can return an email address or a
phone number, because M2 does not hold them (rule 6).
"""
from __future__ import annotations

from dataclasses import dataclass

from rally.modules.profiles.internal import rules
from rally.modules.profiles.internal.models import LEVEL_RANK, Area, PlayingLevel, Profile

DISPLAY_NAME_MIN_LENGTH = rules.DISPLAY_NAME_MIN_LENGTH
DISPLAY_NAME_MAX_LENGTH = rules.DISPLAY_NAME_MAX_LENGTH

NAME_REQUIRED = rules.NAME_REQUIRED
NAME_TOO_SHORT = rules.NAME_TOO_SHORT
NAME_TOO_LONG = rules.NAME_TOO_LONG
LEVEL_REQUIRED = rules.LEVEL_REQUIRED
LEVEL_INVALID = rules.LEVEL_INVALID
AREA_REQUIRED = rules.AREA_REQUIRED
AREA_INVALID = rules.AREA_INVALID

SEARCHABLE_PROFILE_VIEW = "v_searchable_profile"


@dataclass(frozen=True)
class AreaOption:
    code: str
    name: str


@dataclass(frozen=True)
class PublicProfile:
    """Exactly what one player may know about another (PRD §12.2).

    Availability slots join this in S4 and approximate distance is derived per request
    by M4; neither is stored here.
    """

    account_id: int
    display_name: str
    playing_level: str
    playing_level_label: str
    level_rank: int
    area_code: str
    area_name: str


@dataclass(frozen=True)
class OwnProfile:
    """The owner's own view of their profile. Still carries no contact data: email and
    phone stay in M1 and are asked of M1 (rule 6)."""

    display_name: str = ""
    playing_level: str = ""
    area_code: str = ""

    @property
    def exists(self) -> bool:
        return bool(self.display_name)


@dataclass(frozen=True)
class SaveResult:
    account_id: int | None = None
    errors: dict[str, str] | None = None

    @property
    def ok(self) -> bool:
        return self.account_id is not None


def playing_levels() -> list[AreaOption]:
    """The three levels, in the order the PRD lists them."""
    return [AreaOption(code=value, name=label) for value, label in PlayingLevel.choices]


def list_areas() -> list[AreaOption]:
    """The fixed general-area list. No free text, no geocoding (PRD §12.1)."""
    return [AreaOption(code=a.code, name=a.name) for a in Area.objects.all()]


def save_profile(account_id: int, display_name: str, playing_level: str, area_code: str) -> SaveResult:
    """Create or replace the caller's own profile.

    Authorisation belongs to the owning module (ADR-003): there is no parameter for
    "whose profile", only the account the caller is acting as.
    """
    saved = rules.save(account_id, display_name, playing_level, area_code)
    return SaveResult(account_id=saved.account_id, errors=dict(saved.errors or {}))


def get_own_profile(account_id: int) -> OwnProfile:
    row = (
        Profile.objects.filter(account_id=account_id)
        .values("display_name", "playing_level", "area__code")
        .first()
    )
    if row is None:
        return OwnProfile()
    return OwnProfile(
        display_name=row["display_name"],
        playing_level=row["playing_level"],
        area_code=row["area__code"],
    )


def get_public_profile(account_id: int) -> PublicProfile | None:
    """What another player may see. None when there is no profile yet - the caller shows
    a reason rather than an empty card (rule 13)."""
    row = (
        Profile.objects.filter(account_id=account_id)
        .values("account_id", "display_name", "playing_level", "area__code", "area__name")
        .first()
    )
    if row is None:
        return None
    level = PlayingLevel(row["playing_level"])
    return PublicProfile(
        account_id=row["account_id"],
        display_name=row["display_name"],
        playing_level=level.value,
        playing_level_label=level.label,
        level_rank=LEVEL_RANK[level],
        area_code=row["area__code"],
        area_name=row["area__name"],
    )


def is_complete(account_id: int) -> bool:
    """Display name, playing level, general area and a verified email (PRD §12.1)."""
    return rules.is_complete(account_id)


def replace_areas(rows: list[dict]) -> int:
    """Load the fixed area list. Called by the `load_areas` command; the file is data,
    the schema is not (R-11, G-02)."""
    for row in rows:
        Area.objects.update_or_create(
            code=row["code"],
            defaults={
                "name": row["name"],
                "centroid_lat": row["centroid_lat"],
                "centroid_lon": row["centroid_lon"],
            },
        )
    return len(rows)


def area_centroid(area_code: str) -> tuple[float, float] | None:
    """The centre of one general area, or None when the code is not in the fixed list.

    M4 may read M2 only through its published views and the area list is not one of
    them, so Platform resolves the searcher's chosen area here and passes the point to
    M4 as part of the criteria (architecture §6.2). It is an area centre, never a
    player's position (rule 7).
    """
    row = Area.objects.filter(code=area_code).values("centroid_lat", "centroid_lon").first()
    if row is None:
        return None
    return float(row["centroid_lat"]), float(row["centroid_lon"])


def seed_profiles(rows: list[dict]) -> int:
    """Bulk-create profiles for the CON-03 performance dataset. Operations only.

    Each row is {account_id, display_name, playing_level, area_code}. M2 owns `profile`,
    so M2 writes it (rule 1).
    """
    areas = {area.code: area for area in Area.objects.all()}
    Profile.objects.bulk_create(
        [
            Profile(
                account_id=row["account_id"],
                display_name=row["display_name"],
                playing_level=row["playing_level"],
                area=areas[row["area_code"]],
            )
            for row in rows
        ],
        batch_size=1000,
    )
    return len(rows)


def area_codes() -> list[str]:
    return [area.code for area in Area.objects.all()]


def is_verified_player(account_id: int) -> bool:
    """Whether M1 says this account's email is verified.

    M2 relays it because the dependency allowlist does not grant
    `invitations -> identity`: architecture §6.3 routes the check "M1 via M2", and M2
    already reads `v_verified_account` for its own completeness rule. No contact data
    crosses — only the flag (ASR-06).
    """
    from rally.modules.profiles.internal.verification import account_is_verified

    return account_is_verified(account_id)
