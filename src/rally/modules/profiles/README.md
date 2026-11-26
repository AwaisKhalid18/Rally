# M2 — Profile

Display name, playing level, general area, profile completeness and searchability.

| | |
| --- | --- |
| **Owns** | `profile` (account ref, display name, playing level, area ref), `area` (code, name, centroid) |
| **Depends on** | M1 Identity — the published view `v_verified_account` **only**. M2 does not import M1 at all; `internal/verification.py` queries the view, and import-linter enforces the absence of the import. |
| **Serves** | FR-01, FR-05, FR-06, FR-14; ASR-03, ASR-06, ASR-13 |
| **Slice** | S3 (profile create/edit, public profile). Availability joins the public page in S4. |

Physically `profiles`, because `profile` is a Python standard-library module name
(AGENTS.md §3.1).

## Published interface — `rally.modules.profiles.api.facade`

| Operation | Returns | Notes |
| --- | --- | --- |
| `save_profile(account_id, display_name, playing_level, area_code)` | `SaveResult` | Create or replace. There is no "whose profile" parameter — only the account the caller is acting as (ADR-003). |
| `get_own_profile(account_id)` | `OwnProfile` | `exists` is False when nothing is set yet. |
| `get_public_profile(account_id)` | `PublicProfile \| None` | What another player may see. `None` means the caller shows a reason (rule 13). |
| `is_complete(account_id)` | `bool` | Name + level + area **and** a verified email (PRD §12.1). |
| `list_areas()` / `playing_levels()` | `list[AreaOption]` | The fixed list and the three PRD levels. |
| `replace_areas(rows)` | `int` | Used by `manage.py load_areas`. |

## Published read view

`v_searchable_profile(account_id, display_name, playing_level, level_rank, area_code,
area_name, centroid_lat, centroid_lon, searchable)` — defined in
`migrations/0002_v_searchable_profile.py`, declared in `views/__init__.py`.

Permitted consumers: `search` (M4) and `collections` (M8) — ADR-002, ADR-006.

Two things it does on their behalf:

- **`searchable` already folds in the ASR-06 gate.** A profile is searchable only when
  M1 says the email is verified, so M4 cannot forget the rule.
- **`level_rank` publishes the ordering** (1/2/3) that "rank by level closeness"
  (PRD §12.1) needs, so M4 never has to encode the level order itself.

## Rules this module carries

- **Rule 6.** No contact data here. Email and phone stay in M1; the profile screen sends
  the optional phone number straight to M1's facade and M2 never sees it.
- **Rule 7.** No exact location, in the schema or in a form. `area` holds the **centre of
  a district**, which is not a player's position. Distance is derived per request from
  these centroids and shown rounded and labelled approximate (ASR-03).
- **Rule 1.** M2 reads M1 through `v_verified_account` and touches no table of M1's.
- **Rule 14.** Name length, the level set and the area list are decided here, not in a
  Platform form.

## The area list

`ops/seed/areas.csv`, loaded with `python manage.py load_areas`. A fixed list, so no
geocoding service enters the system (G-02, CON-01). The shipped rows are **placeholder
data for Islamabad and Rawalpindi pending R-11**; replacing them is a data change, not a
schema change.

## Open items that touch this module

- **R-11** — the pilot city's real area list.
- **G-12** — the display-name bounds (2–40) are a proposed resolution, not a decision.
