"""What makes a search valid (PRD §12.1).

Date, time window and location are mandatory; playing level and maximum distance are
optional and arrive with S6. The rule lives here, in M4, not in a Platform form
(rule 14).

M4 never alters what the player asked for. If a search cannot run it says so and the
criteria come back untouched — the system never silently widens or narrows them
(FR-13, FE-7).
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

DATE_REQUIRED = "Choose a date."
START_REQUIRED = "Choose a time to play from."
END_REQUIRED = "Choose a time to play until."
END_BEFORE_START = "The end time must be after the start time."
WINDOW_IN_PAST = "That time has already passed. Choose a time in the future."
LOCATION_REQUIRED = "Choose the area you want to play in."
LOCATION_INVALID = "Choose an area from the list."


@dataclass(frozen=True)
class SearchCriteria:
    """A validated search. The two instants are UTC; Platform converted them at the edge."""

    window_start: _dt.datetime
    window_end: _dt.datetime
    area_code: str
    reference_lat: float | None
    reference_lon: float | None


@dataclass(frozen=True)
class CriteriaResult:
    criteria: SearchCriteria | None = None
    errors: dict[str, str] | None = None

    @property
    def ok(self) -> bool:
        return self.criteria is not None


def validate(
    window_start: _dt.datetime | None,
    window_end: _dt.datetime | None,
    area_code: str,
    area_centroid: tuple[float, float] | None,
    now: _dt.datetime,
) -> CriteriaResult:
    errors: dict[str, str] = {}

    if window_start is None:
        errors["start"] = START_REQUIRED
    if window_end is None:
        errors["end"] = END_REQUIRED
    if window_start is not None and window_end is not None:
        if window_end <= window_start:
            errors["end"] = END_BEFORE_START
        elif window_end <= now:
            errors["date"] = WINDOW_IN_PAST

    if not area_code:
        errors["area_code"] = LOCATION_REQUIRED
    elif area_centroid is None:
        errors["area_code"] = LOCATION_INVALID

    if errors:
        return CriteriaResult(errors=errors)

    lat, lon = area_centroid
    return CriteriaResult(
        criteria=SearchCriteria(
            window_start=window_start,
            window_end=window_end,
            area_code=area_code,
            reference_lat=lat,
            reference_lon=lon,
        ),
        errors={},
    )
