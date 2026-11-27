"""The matching predicate and the ranking — one query, one owner (ASR-01, ASR-02).

Everything the search path needs is read from the three published views, and nothing
else (rule 1, ADR-002):

    v_searchable_profile   M2  display name, level, level rank, area, centroid,
                               and `searchable`, which already folds in M1's
                               verification gate (ASR-06)
    v_active_availability  M3  future slots only, filtered on the database clock
    v_block_pairs          M6  directed blocks, checked in both directions

It is deliberately one statement, including the searcher's own level rank, which the
ranking needs. ASR-01 gives the whole path a 2 s budget at 100 concurrent users over
10,000 profiles; fan-out calls and an in-memory join would not hold it, and splitting
the predicate would let the rules drift apart (ASR-02).

No column selected here is private. The views carry no email, no phone and no player
location — only the centre of a general area (rules 6 and 7).
"""
from __future__ import annotations

import datetime as _dt
import math
from dataclasses import dataclass

from django.db import connection

EARTH_RADIUS_KM = 6371.0
KM_PER_DEGREE_LATITUDE = math.pi * EARTH_RADIUS_KM / 180.0

# G-12 (still an open proposal): a search returns at most this many players.
RESULT_LIMIT = 50

# Great-circle distance between the reference point and the other player's area centre.
# LEAST/GREATEST clamp the cosine, because floating point can push it just outside
# [-1, 1] for identical points and acos() would then fail.
_DISTANCE_KM = f"""
    CASE
        WHEN p.centroid_lat IS NULL OR p.centroid_lon IS NULL THEN NULL
        ELSE {EARTH_RADIUS_KM} * acos(LEAST(1.0, GREATEST(-1.0,
              cos(radians(%(ref_lat)s)) * cos(radians(p.centroid_lat::double precision))
            * cos(radians(p.centroid_lon::double precision) - radians(%(ref_lon)s))
            + sin(radians(%(ref_lat)s)) * sin(radians(p.centroid_lat::double precision))
        )))
    END
"""

_SQL = f"""
WITH matched AS (
    SELECT
        p.account_id,
        p.display_name,
        p.playing_level,
        p.level_rank,
        p.area_name,
        {_DISTANCE_KM} AS distance_km,
        MIN(a.starts_at) AS earliest_overlap,
        ARRAY_AGG(a.starts_at ORDER BY a.starts_at) AS slot_starts,
        ARRAY_AGG(a.ends_at   ORDER BY a.starts_at) AS slot_ends
    FROM v_searchable_profile p
    JOIN v_active_availability a
           ON a.account_id = p.account_id
          -- A strict overlap: the slot must still be running when the window opens and
          -- must start before it closes. Touching at an endpoint is not an overlap.
          AND a.starts_at < %(window_end)s
          AND a.ends_at   > %(window_start)s
    WHERE p.searchable                      -- complete profile AND verified (ASR-06)
      AND p.account_id <> %(searcher_id)s   -- never the searcher themselves
      -- Optional level filter. Omitted means every level (PRD 12.1).
      AND (%(playing_level)s IS NULL OR p.playing_level = %(playing_level)s)
      -- Cheap bounding box before the great-circle arithmetic (ASR-01). It can only
      -- admit extra rows, never reject a real match, and the exact filter below is
      -- what actually decides.
      AND p.centroid_lat BETWEEN %(lat_min)s AND %(lat_max)s
      AND (%(lon_wraps)s OR p.centroid_lon BETWEEN %(lon_min)s AND %(lon_max)s)
      AND NOT EXISTS (
            SELECT 1 FROM v_block_pairs b
            WHERE (b.blocker_account_id = %(searcher_id)s AND b.blocked_account_id = p.account_id)
               OR (b.blocker_account_id = p.account_id AND b.blocked_account_id = %(searcher_id)s)
          )
    GROUP BY p.account_id, p.display_name, p.playing_level, p.level_rank,
             p.area_name, p.centroid_lat, p.centroid_lon
)
SELECT account_id, display_name, playing_level, level_rank, area_name,
       distance_km, earliest_overlap, slot_starts, slot_ends
FROM matched
-- The exact limit, on the unrounded distance; the display rounds separately (G-12).
-- A player at exactly the limit is inside it.
WHERE distance_km IS NOT NULL AND distance_km <= %(max_distance_km)s
-- PRD 12.1 ranking: distance, then closeness to the searcher's own level, then the
-- earliest overlapping slot. The searcher's rank is read in the same statement; when
-- they have no profile the term collapses to zero and leaves the order to the others.
ORDER BY distance_km ASC,
         abs(level_rank - COALESCE(
             (SELECT s.level_rank FROM v_searchable_profile s
               WHERE s.account_id = %(searcher_id)s),
             level_rank)) ASC,
         earliest_overlap ASC
LIMIT %(limit)s
"""


@dataclass(frozen=True)
class MatchedSlot:
    starts_at: _dt.datetime
    ends_at: _dt.datetime


@dataclass(frozen=True)
class Match:
    account_id: int
    display_name: str
    playing_level: str
    level_rank: int
    area_name: str
    # None when the distance cannot be worked out. It is never 0 and never a placeholder
    # (rule 13); the caller shows a reason instead.
    distance_km: float | None
    overlapping_slots: tuple[MatchedSlot, ...]


def bounding_box(lat: float, lon: float, radius_km: float) -> dict:
    """A latitude/longitude box that certainly contains everything within `radius_km`.

    Generous on purpose: it is a cheap pre-filter, so admitting a few extra rows costs
    nothing while excluding a real match would be a bug. Near the poles, and wherever
    the box would cross the antimeridian, the longitude bound is dropped altogether and
    only latitude narrows the scan.
    """
    delta_lat = radius_km / KM_PER_DEGREE_LATITUDE
    lat_min = max(-90.0, lat - delta_lat)
    lat_max = min(90.0, lat + delta_lat)

    # A degree of longitude shrinks towards the poles, so the box must be widened by the
    # cosine at its WORST latitude - the edge furthest from the equator. Using the
    # nearest edge would make the box too narrow and could drop a real match.
    shrink = math.cos(math.radians(max(abs(lat_min), abs(lat_max))))
    if shrink <= 1e-6:
        return {"lat_min": lat_min, "lat_max": lat_max, "lon_min": -180.0, "lon_max": 180.0, "lon_wraps": True}

    delta_lon = delta_lat / shrink
    lon_min, lon_max = lon - delta_lon, lon + delta_lon
    wraps = lon_min < -180.0 or lon_max > 180.0
    return {
        "lat_min": lat_min,
        "lat_max": lat_max,
        "lon_min": lon_min,
        "lon_max": lon_max,
        "lon_wraps": wraps,
    }


def run(
    searcher_id: int,
    window_start: _dt.datetime,
    window_end: _dt.datetime,
    reference_lat: float,
    reference_lon: float,
    max_distance_km: float,
    playing_level: str | None = None,
    limit: int = RESULT_LIMIT,
) -> list[Match]:
    params = {
        "searcher_id": searcher_id,
        "window_start": window_start,
        "window_end": window_end,
        "ref_lat": reference_lat,
        "ref_lon": reference_lon,
        "max_distance_km": max_distance_km,
        "playing_level": playing_level or None,
        "limit": limit,
    }
    params.update(bounding_box(reference_lat, reference_lon, max_distance_km))

    with connection.cursor() as cursor:
        cursor.execute(_SQL, params)
        rows = cursor.fetchall()

    matches: list[Match] = []
    for (
        account_id,
        display_name,
        playing_level_value,
        level_rank,
        area_name,
        distance_km,
        _earliest,
        slot_starts,
        slot_ends,
    ) in rows:
        matches.append(
            Match(
                account_id=account_id,
                display_name=display_name,
                playing_level=playing_level_value,
                level_rank=level_rank,
                area_name=area_name,
                distance_km=float(distance_km) if distance_km is not None else None,
                overlapping_slots=tuple(
                    MatchedSlot(starts_at=start, ends_at=end)
                    for start, end in zip(slot_starts, slot_ends)
                ),
            )
        )
    return matches
