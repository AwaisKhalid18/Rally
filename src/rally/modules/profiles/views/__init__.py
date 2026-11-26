"""M2's published database read view.

`v_searchable_profile` — account id, display name, playing level (label and rank),
area code, area name, centroid, and a `searchable` flag that already folds in profile
completeness and M1's verification state (ASR-06).

The SQL lives in this module's migrations. Permitted consumers: `search` (M4) and
`collections` (M8) — ADR-002 and ADR-006. Changing a column is a contract change, not an
internal refactor.

**No contact field and no player location may ever be added here** (rules 6 and 7). The
centroid is the area's centre, not a player's position.
"""

SEARCHABLE_PROFILE = "v_searchable_profile"
SEARCHABLE_PROFILE_COLUMNS = (
    "account_id",
    "display_name",
    "playing_level",
    "level_rank",
    "area_code",
    "area_name",
    "centroid_lat",
    "centroid_lon",
    "searchable",
)

__all__ = ["SEARCHABLE_PROFILE", "SEARCHABLE_PROFILE_COLUMNS"]
