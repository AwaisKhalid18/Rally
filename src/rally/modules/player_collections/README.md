# M8 — Player Collections

A player's own favorites and named searches. The module's logical name is
`collections`; the folder is `player_collections` because a top-level package called
`collections` would shadow the Python standard library (AGENTS.md §3.1).

| | |
| --- | --- |
| **Owns** | `favorite` · `saved_search` **arrives in S15** |
| **Depends on** | the published read views of M2, M3 and M6 — for composing the display only |
| **Serves** | FR-16, FR-18; ASR-03, ASR-04, ASR-05, ASR-10 |
| **Slice** | S13 favorites. Compare is **M4's** `compare()` (S14) and stores nothing; saved searches are S15. |

> **FR-16 and FR-18 are not part of the Final Validated PRD.** They arrived on
> 2026-11-11, after the baseline was agreed, and are recorded with the same discipline
> as the originals — but they have **not** been through the client's validation
> (architecture §16.1, `plan.md` item A-00). Nothing here may be presented as approved.

## Published interface — today

| Operation | Notes |
| --- | --- |
| `add_favorite(owner, favorited)` | Self, duplicates and the one past the cap are refused, each with its own message. |
| `remove_favorite(owner, favorited)` | Your own list only. Works even when the account cannot be resolved. |
| `list_favorites(owner)` | Newest first, composed from the read views on every request. |
| `is_favorite(owner, favorited)` | So a page can offer Add or Remove rather than guessing. |
| `count_favorites(owner)` · `max_favorites()` · `cap_reached_message()` | The cap, and what the player is told about it. |

Still to come in S15: `save_search`, `update_search`, `delete_search`, `list_searches`,
`get_search`.

## Published read view

**None, and nothing depends on M8** (architecture §16.6). M8 is a leaf. The `views/`
package exists only to make that absence deliberate.

## References, never copies (rule 11)

`favorite` holds three things: the owner, the favorited account, and when it was added.
No display name, no playing level, no area, no availability, no contact detail, no
coordinate pair. Every display field is resolved from the published views on each
request, so a favorite can never serve a playing level or an area the other player has
since changed — there is a test that changes a profile and reads the list again.

This is also why both ids are plain integers rather than `ForeignKey`s: a relation would
need an import of another module's model (AGENTS.md §3.1). It follows that a favorite can
outlive the account it points at, which is wanted — see below.

## Shown, not hidden

One statement composes the list from `v_searchable_profile`, `v_active_availability` and
`v_block_pairs`. What it does with a gap matters more than the join:

| Case | Behaviour | Why |
| --- | --- | --- |
| No future playing times | **Shown**, with "No playing times recorded" in place of the times | The player curated this list; dropping an entry silently is the behaviour FR-13 forbids for search criteria (§16.8) |
| Account cannot be resolved | **Shown** as "No longer available", and still removable | A favorite outlives the account (G-06); an entry you cannot remove would be worse than one that is gone |
| Incomplete or inactive profile | **Shown** | Profile completeness is a *relevance* rule and belongs to search, not here |
| **Blocked pair** | **Omitted, both directions** | Blocking is a *safety* rule and applies wherever one player can see another (ASR-10) |

That asymmetry — search excludes incomplete profiles, the favorites list does not, and
both exclude blocks — is deliberate and is the point of §16.8.

### The clock

`v_active_availability` drops past slots using the database's own `now()`. The list adds
`ends_at > %(now)s` from Platform's injectable clock, so the clock stays authoritative
and a frozen test clock governs this path too (rule 8).

## The cap

50 favorites, from `RALLY_MAX_FAVORITES`. **R-15 closes G-07**, and the number is a
configuration value: changing it needs no architecture change. It is enforced
server-side, never by the page, so the 51st is refused with a sentence that names the
limit.

## Favoriting is silent

No outbox record, no notification, and the favorited player is never told they are on a
list (§16.8, AC3). Adding an event would disclose a private list and would put traffic
on the path ASR-12 keeps clear for email.

## Rules this module carries

- **Rule 1.** M8 reads the published views and no base table of another module.
- **Rule 11.** References, never copies. No profile field, availability value, contact
  detail or coordinate pair goes into `favorite`.
- **Rule 12.** M8 does not call M4 and M4 does not read M8. Reusing a saved search is
  composed in Platform: criteria from M8, then `M4.search()`.
- **Rule 13.** An absent field carries a reason — never `""`, `0` or a placeholder.
- **ASR-05.** M8 does its own ownership check: you see and change only your own list.
- **ASR-10.** Blocked pairs are omitted both ways.

## Open items that touch this module

- **A-00** — FR-16 to FR-18 are not in the Validated PRD.
- **G-06** — what becomes of a favorite when the account is gone depends on the
  unresolved retention rules (G-04). Until then it shows "No longer available" and can be
  removed; there is no account deletion in the MVP (R-13).
- **A-25** — the wording the block cascade uses, since this list is the second consumer
  of the block rule.
