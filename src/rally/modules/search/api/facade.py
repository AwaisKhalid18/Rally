"""M4 Search & Matching — facade.

Published (AGENTS.md §3): `search()`. `compare()` arrives with S14.

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
    limit: int = RESULT_LIMIT,
) -> SearchOutcome:
    """Filter and rank the players who could play in this window.

    Excluded, all together (PRD §12.1, ASR-02): no slot overlapping the window; an
    incomplete or unverified profile; a block in either direction; and the searcher.

    Ranked by distance ascending, then earliest overlapping slot. Level closeness is
    inserted between them in S6.
    """
    checked = criteria_rules.validate(
        window_start=window_start,
        window_end=window_end,
        area_code=area_code,
        area_centroid=area_centroid,
        now=clock.now(),
    )
    if not checked.ok:
        return SearchOutcome(errors=dict(checked.errors or {}))

    found = query.run(
        searcher_id=searcher_id,
        window_start=checked.criteria.window_start,
        window_end=checked.criteria.window_end,
        reference_lat=checked.criteria.reference_lat,
        reference_lon=checked.criteria.reference_lon,
        limit=limit,
    )
    return SearchOutcome(results=tuple(found), errors={})
