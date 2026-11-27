# M4 — Search & Matching

The filter predicate, the ranking, and result composition.

| | |
| --- | --- |
| **Owns** | **No tables.** M4 is read-only (rule 9). There is no `migrations/` folder and this is not a Django app — that absence is the point. |
| **Depends on** | The published read views of M2, M3 and M6, and nothing else |
| **Serves** | FR-02, FR-03, FR-05, FR-07, FR-13; ASR-01, ASR-02, ASR-10, ASR-13 |
| **Slice** | S5 (core search) and S6 (filters, full ranking, bounding box). `compare()` arrives in S14. |

## Published interface

`search(searcher_id, window_start, window_end, area_code, area_centroid,
        playing_level=None, max_distance_km=None) -> SearchOutcome`

`compare()` arrives with S14. M4 is called by no module — only Platform calls it.

## One query, one owner

`internal/query.py` holds a single SQL statement joining the three published views:

| View | From | Gives |
| --- | --- | --- |
| `v_searchable_profile` | M2 | name, level, level rank, area, centroid, and `searchable` — which already folds in M1's verification gate (ASR-06) |
| `v_active_availability` | M3 | future slots only, filtered on the database clock |
| `v_block_pairs` | M6 | directed blocks, checked in **both** directions |

It is deliberately one statement. ASR-01 gives the path a 2 s budget at 100 concurrent
users over 10,000 profiles; fan-out calls and an in-memory join would not hold it, and
splitting the predicate would let the rules drift (ASR-02). A test asserts the search
runs as exactly one query however many players match.

## The rules it applies (PRD §12.1)

**Excluded, all together — the filters combine with AND:** no slot strictly overlapping
the window · outside the maximum distance · a level other than the one chosen, when one
is chosen · an incomplete or unverified profile · a block in either direction · the
searcher themselves.

**Ranked by:** distance ascending → closeness to the searcher own playing level →
earliest overlapping slot. The searcher own level rank is read in the same statement;
when they have no profile the closeness term collapses to zero and leaves the order to
the other two.

An overlap is strict: a slot that ends exactly when the window opens does not match.

## Distance

Great-circle, computed in SQL from the two **area centres** — never from a player's
position, which Rally does not store (rule 7, ASR-03). The unrounded value drives
ordering and, from S6, the maximum-distance filter; the display rounds to the nearest
kilometre and says "about" (G-12). A player exactly at the limit is inside it.

The optional filters: playing level (empty means every level) and maximum distance
(5, 10, 20 or 50 km, default 10; anything else is rejected) - PRD 12.1.

When it cannot be worked out, `distance_km` is `None` and the card shows a reason. It is
never `0` and never a placeholder (rule 13, FE-6).

## The reference point comes from the caller

M4 may read M2 only through its published views, and the area list is not one of them.
So Platform resolves the chosen area's centre through M2's facade and passes it in — as
architecture §6.2 shows, `search(criteria, searcherId)` with criteria carrying the
location. M4 still decides whether that location is acceptable.

## Rules this module carries

- **Rule 9.** Read-only, owns nothing, called only by Platform.
- **Rule 1.** Three views, nothing else. No table of another module is touched.
- **Rule 13.** An absent distance is absent with a reason.
- **FR-13 / FE-7.** Criteria are never silently widened or narrowed. A search that
  matches nobody is a result, not an error.

## Measured

Against the 10,000-profile seed (`manage.py load_areas && manage.py seed_players`),
sequential single-client: p50 24.7 ms, p95 45.5 ms, 50 results. S5 measured 23.5 ms at
p95 before the refinement; the CTE and the level-rank lookup roughly doubled it, which
leaves it about forty times inside the budget. The 100-concurrent-user run that NFR-01
actually asks for belongs to S16.

## The bounding box (ASR-01)

Before any great-circle arithmetic the query narrows the scan to a latitude/longitude
box around the reference point. The box is deliberately generous: it may admit extra
rows, which costs a little, but it must never reject a real match, which would be a bug.
It is widened by the cosine at the edge **furthest** from the equator, and wherever it
would reach a pole or cross the antimeridian the longitude bound is dropped and latitude
alone narrows the scan.

The exact `distance_km <= max_distance_km` filter after the box is what actually decides.
