"""M4 Search & Matching — facade.

Published (AGENTS.md §3): `search()` and `compare()`.

M4 owns no tables and writes nothing. It is called by no module — only Platform calls it
(rule 9). It owns the matching predicate and the ranking, and no other module may
reimplement either (ASR-02).

**The reference point is supplied by the caller.** M4 may read M2, M3 and M6 only through
their published read views (AGENTS.md §3), and the area list is not one of them, so
Platform resolves the chosen area's centre through M2's facade and passes it in — which
is also what architecture §6.2 shows: `search(criteria, searcherId)`, criteria carrying
the location. M4 still decides whether that location is acceptable.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from rally.core import clock
from rally.modules.search.internal import comparison
from rally.modules.search.internal import criteria as criteria_rules
from rally.modules.search.internal import query

RESULT_LIMIT = query.RESULT_LIMIT

DATE_REQUIRED = criteria_rules.DATE_REQUIRED
START_REQUIRED = criteria_rules.START_REQUIRED
END_REQUIRED = criteria_rules.END_REQUIRED
END_BEFORE_START = criteria_rules.END_BEFORE_START
WINDOW_IN_PAST = criteria_rules.WINDOW_IN_PAST
LOCATION_REQUIRED = criteria_rules.LOCATION_REQUIRED
LOCATION_INVALID = criteria_rules.LOCATION_INVALID
LEVEL_INVALID = criteria_rules.LEVEL_INVALID
DISTANCE_INVALID = criteria_rules.DISTANCE_INVALID

PLAYING_LEVELS = criteria_rules.PLAYING_LEVELS
DISTANCE_CHOICES_KM = criteria_rules.DISTANCE_CHOICES_KM
DEFAULT_MAX_DISTANCE_KM = criteria_rules.DEFAULT_MAX_DISTANCE_KM

MatchedSlot = query.MatchedSlot
Match = query.Match


@dataclass(frozen=True)
class SearchOutcome:
    """Either a ranked list, or the reasons the search could not run.

    `results` being empty is not a failure: it is a search that matched nobody, and the
    caller shows guidance with the criteria unchanged (FR-13).
    """

    results: tuple[Match, ...] = ()
    errors: dict[str, str] | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


def search(
    searcher_id: int,
    window_start: _dt.datetime | None,
    window_end: _dt.datetime | None,
    area_code: str,
    area_centroid: tuple[float, float] | None,
    playing_level: str | None = None,
    max_distance_km=None,
    limit: int = RESULT_LIMIT,
) -> SearchOutcome:
    """Filter and rank the players who could play in this window.

    Excluded, all together — the filters combine with AND (PRD §12.1, ASR-02): no slot
    overlapping the window; outside the maximum distance; a playing level other than the
    one chosen, when one is chosen; an incomplete or unverified profile; a block in
    either direction; and the searcher.

    Ranked by distance ascending, then closeness to the searcher's own playing level,
    then earliest overlapping slot.

    `playing_level` empty means every level. `max_distance_km` empty means the 10 km
    default; the choices are 5, 10, 20 and 50 and anything else is rejected.
    """
    checked = criteria_rules.validate(
        window_start=window_start,
        window_end=window_end,
        area_code=area_code,
        area_centroid=area_centroid,
        now=clock.now(),
    )
    errors = dict(checked.errors or {})

    level, level_error = criteria_rules.normalise_level(playing_level)
    if level_error:
        errors["playing_level"] = level_error

    distance_km, distance_error = criteria_rules.normalise_max_distance(max_distance_km)
    if distance_error:
        errors["max_distance_km"] = distance_error

    if errors:
        return SearchOutcome(errors=errors)

    found = query.run(
        searcher_id=searcher_id,
        window_start=checked.criteria.window_start,
        window_end=checked.criteria.window_end,
        reference_lat=checked.criteria.reference_lat,
        reference_lon=checked.criteria.reference_lon,
        max_distance_km=distance_km,
        playing_level=level,
        limit=limit,
    )
    return SearchOutcome(results=tuple(found), errors={})


# --- Comparison (S14, FR-17, architecture §16.5) -----------------------------

MAX_COMPARED = comparison.MAX_COMPARED
ComparedPlayer = comparison.ComparedPlayer
ComparisonOutcome = comparison.ComparisonOutcome

NONE_SELECTED = comparison.NONE_SELECTED
TOO_MANY = comparison.TOO_MANY
DUPLICATE_SELECTED = comparison.DUPLICATE_SELECTED
CANNOT_COMPARE_YOURSELF = comparison.CANNOT_COMPARE_YOURSELF

NOT_FOUND_REASON = comparison.NOT_FOUND_REASON
NO_SLOTS_REASON = comparison.NO_SLOTS_REASON
NO_DISTANCE_REASON = comparison.NO_DISTANCE_REASON


def compare(viewer_id: int, account_ids, reference_centroid=None) -> ComparisonOutcome:
    """Compare up to three players side by side (FR-17).

    Stateless: the selection is passed in on every call and nothing is stored, so
    removing or replacing a player is simply a new call (§16.5). M4 stays read-only and
    still owns no tables.

    The cap of three is enforced **here**, not by the page. A blocked player and one who
    does not exist give the same answer, so neither can be told apart (AGENTS.md §5).
    A player with no future times is still comparable, with the times absent and a
    reason given (rule 13).
    """
    return comparison.compare(viewer_id, account_ids, reference_centroid)
