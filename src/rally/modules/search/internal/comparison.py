"""`compare()` — a bounded, stateless read (FR-17, architecture §16.5).

It is M4's second operation and it changes none of M4's properties: still read-only,
still owning no tables, still called only by Platform (rule 9). The comparison set is
**not persisted** — it is a transient selection the caller passes in on each call, so
removing or replacing a player is a new request and FR-17 adds no table (§16.5).

Three rules decide the shape of this file.

**The cap of three is enforced here, in the server** (§16.5, AGENTS.md §5). A request
naming four players is rejected; the limit is never left to the page.

**A blocked player is treated exactly like a non-existent account** (AGENTS.md §5,
ASR-10). Both come back as not found. Anything else — a distinct "you have blocked
this player" — would tell one player about the other's safety decision, and would let
the absence of a result confirm that an account exists.

**A player with no future times is still comparable.** Unlike search, which excludes
anyone with no overlapping slot because relevance is what search is for, compare shows
exactly the players the caller named: the times are absent with a reason (rule 13).
Only `searchable` — a complete profile and a verified account — is required, because an
incomplete profile has nothing to compare.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from django.db import connection

from rally.core import clock
from rally.modules.search.internal.query import _DISTANCE_KM, MatchedSlot

# §16.5: "the cap of three is enforced server-side in M4; a request with more is
# rejected". Also AGENTS.md §5 Compare.
MAX_COMPARED = 3

NONE_SELECTED = "Choose at least one player to compare."
TOO_MANY = f"You can compare at most {MAX_COMPARED} players at a time."
DUPLICATE_SELECTED = "A player can only appear once in a comparison."
CANNOT_COMPARE_YOURSELF = "You cannot compare yourself."

# Rule 13: the reasons a field is absent. Never a blank, a zero or a placeholder.
NOT_FOUND_REASON = "No longer available"
NO_SLOTS_REASON = "No playing times recorded"
NO_DISTANCE_REASON = "Distance unavailable"

_SQL = f"""
SELECT
    p.account_id,
    p.display_name,
    p.playing_level,
    p.area_name,
    {_DISTANCE_KM} AS distance_km,
    ARRAY_AGG(a.starts_at ORDER BY a.starts_at)
        FILTER (WHERE a.starts_at IS NOT NULL) AS slot_starts,
    ARRAY_AGG(a.ends_at   ORDER BY a.starts_at)
        FILTER (WHERE a.starts_at IS NOT NULL) AS slot_ends
FROM v_searchable_profile p
-- LEFT JOIN, not JOIN: a player with no future times is still comparable, shown with
-- a reason in place of the times (§16.5, rule 13).
LEFT JOIN v_active_availability a
       ON a.account_id = p.account_id
      AND a.ends_at > %(now)s
WHERE p.account_id = ANY(%(account_ids)s)
  AND p.searchable                        -- complete profile AND verified (ASR-06)
  AND p.account_id <> %(viewer_id)s
  -- A blocked player is simply not here, in either direction, and so is indistinguish-
  -- able from one who does not exist (ASR-10, AGENTS.md §5).
  AND NOT EXISTS (
        SELECT 1 FROM v_block_pairs b
        WHERE (b.blocker_account_id = %(viewer_id)s AND b.blocked_account_id = p.account_id)
           OR (b.blocker_account_id = p.account_id AND b.blocked_account_id = %(viewer_id)s)
      )
GROUP BY p.account_id, p.display_name, p.playing_level, p.area_name,
         p.centroid_lat, p.centroid_lon
"""


@dataclass(frozen=True)
class ComparedPlayer:
    """One column of the comparison. Every field is present, or absent with a reason."""

    account_id: int
    found: bool
    display_name: str | None
    playing_level: str | None
    area_name: str | None
    slots: tuple[MatchedSlot, ...]
    # None when it cannot be worked out. Never 0 and never a placeholder (rule 13).
    distance_km: float | None
    not_found_reason: str | None
    no_slots_reason: str | None
    no_distance_reason: str | None


@dataclass(frozen=True)
class ComparisonOutcome:
    """The columns in the order they were asked for, or why the request was refused."""

    players: tuple[ComparedPlayer, ...] = ()
    errors: dict[str, str] | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


def _absent(account_id: int) -> ComparedPlayer:
    return ComparedPlayer(
        account_id=account_id,
        found=False,
        display_name=None,
        playing_level=None,
        area_name=None,
        slots=(),
        distance_km=None,
        not_found_reason=NOT_FOUND_REASON,
        no_slots_reason=None,
        no_distance_reason=None,
    )


def compare(
    viewer_id: int,
    account_ids,
    reference_centroid: tuple[float, float] | None = None,
) -> ComparisonOutcome:
    """Compare the named players side by side (FR-17).

    `reference_centroid` is the point distances are measured from — §12.1's rule, which
    Platform resolves (the viewer's own general area by default). Without it every
    distance is absent with a reason; M4 never invents one.
    """
    selected = list(account_ids or [])

    if not selected:
        return ComparisonOutcome(errors={"players": NONE_SELECTED})
    if len(selected) > MAX_COMPARED:
        # Server-side, never the page (§16.5).
        return ComparisonOutcome(errors={"players": TOO_MANY})
    if len(set(selected)) != len(selected):
        return ComparisonOutcome(errors={"players": DUPLICATE_SELECTED})
    if viewer_id in selected:
        return ComparisonOutcome(errors={"players": CANNOT_COMPARE_YOURSELF})

    has_reference = reference_centroid is not None
    reference_lat, reference_lon = reference_centroid if has_reference else (0.0, 0.0)

    with connection.cursor() as cursor:
        cursor.execute(
            _SQL,
            {
                "account_ids": selected,
                "viewer_id": viewer_id,
                "now": clock.now(),
                "ref_lat": reference_lat,
                "ref_lon": reference_lon,
            },
        )
        found = {row[0]: row for row in cursor.fetchall()}

    players: list[ComparedPlayer] = []
    for account_id in selected:
        row = found.get(account_id)
        if row is None:
            # Blocked, unverified, incomplete or gone - all the same answer (ASR-05).
            players.append(_absent(account_id))
            continue

        _, display_name, playing_level, area_name, distance_km, starts, ends = row
        slots = tuple(
            MatchedSlot(starts_at=s, ends_at=e) for s, e in zip(starts or [], ends or [])
        )
        distance = float(distance_km) if (has_reference and distance_km is not None) else None
        players.append(
            ComparedPlayer(
                account_id=account_id,
                found=True,
                display_name=display_name,
                playing_level=playing_level,
                area_name=area_name,
                slots=slots,
                distance_km=distance,
                not_found_reason=None,
                no_slots_reason=None if slots else NO_SLOTS_REASON,
                no_distance_reason=None if distance is not None else NO_DISTANCE_REASON,
            )
        )

    return ComparisonOutcome(players=tuple(players), errors={})
