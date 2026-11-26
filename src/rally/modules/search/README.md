# M4 — Search & Matching

The filter predicate, the ranking, and result composition.

| | |
| --- | --- |
| **Owns** | **No tables.** M4 is read-only (rule 9). There is no `migrations/` folder and this is not a Django app — that absence is the point. |
| **Depends on** | The published read views of M2, M3 and M6, and nothing else |
| **Serves** | FR-02, FR-03, FR-05, FR-07, FR-13; ASR-01, ASR-02, ASR-10, ASR-13 |
| **Slice** | S5 (core search). Level filter, max distance and level-closeness ranking arrive in S6; `compare()` in S14. |

## Published interface

`search(searcher_id, window_start, window_end, area_code, area_centroid) -> SearchOutcome`

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

**Excluded, all together:** no slot strictly overlapping the window · an incomplete or
unverified profile · a block in either direction · the searcher themselves.

**Ranked by:** distance ascending → earliest overlapping slot. Level closeness is
inserted between them in S6. A player whose distance cannot be worked out sorts last,
never first.

An overlap is strict: a slot that ends exactly when the window opens does not match.

## Distance

Great-circle, computed in SQL from the two **area centres** — never from a player's
position, which Rally does not store (rule 7, ASR-03). The unrounded value drives
ordering and, from S6, the maximum-distance filter; the display rounds to the nearest
kilometre and says "about" (G-12).

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
sequential single-client: p50 10.5 ms, p95 23.5 ms, 50 results. The 100-concurrent-user
run that NFR-01 actually asks for belongs to S16.
