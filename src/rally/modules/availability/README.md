# M3 — Availability

Availability slots, their validity, overlap queries and the slot lifecycle.

| | |
| --- | --- |
| **Owns** | `availability_slot` (account ref, start, end) |
| **Depends on** | Nothing |
| **Serves** | FR-04; ASR-08, ASR-09 |
| **Slice** | S4. M5 starts asking `has_availability()` in S7 and S8. |

## Published interface — `rally.modules.availability.api.facade`

| Operation | Returns | Notes |
| --- | --- | --- |
| `add_slot(account_id, starts_at, ends_at)` | `SlotResult` | Instants in UTC. One readable error at a time. |
| `edit_slot(account_id, slot_id, …)` / `remove_slot(…)` | `SlotResult` | Only the owner's own slot; M3 authorises its own records (ADR-003). |
| `get_slot(account_id, slot_id)` | `Slot \| None` | The owner's own slot, for the edit form. |
| `list_slots(account_id, include_past=False)` | `list[Slot]` | Earliest first. Past slots are filtered out at query time. |
| `has_availability(account_id, starts_at, ends_at)` | `bool` | **One slot must cover the whole window.** Two adjoining slots do not add up — a game is a single continuous booking. |
| `remove_expired_slots()` | `int` | The worker's sweep. |

## Published read view

`v_active_availability(slot_id, account_id, starts_at, ends_at)` — future slots only,
defined in `migrations/0003_v_active_availability.py`, declared in `views/__init__.py`.
Permitted consumers: `search` (M4) and `collections` (M8).

The view filters on the **database clock**, so a slot disappears the moment its end time
passes, whether or not the sweep has run. That is what keeps a stalled worker a freshness
problem and never a correctness one (ADR-005).

## What M3 does not decide

It answers *"is this player free then?"*. It never answers *"may this game be
confirmed?"* — M5 asks, M5 decides (architecture §5). There is nothing here about
invitations, games or double-booking.

## Rules this module carries

- **Rule 8.** Every comparison uses the server clock in UTC. A time the player typed is
  an input, never the authority for a state change; Platform converts at the edge
  (`rally/core/localtime.py`).
- **Rule 1 / 2.** M3 depends on nothing and imports no other module. `account_id` is a
  plain integer, not a ForeignKey.
- **No recurrence.** PRD §12.1 settles it: individual dates and times. There is no rule,
  schedule or repeat field, and the screen offers no way to make one.

## Own slots may not overlap

Enforced twice, the same way double-booking is (ADR-004's pattern):

1. an application check in `internal/rules.py`, so the player gets a sentence;
2. a PostgreSQL exclusion constraint, which is what actually holds under concurrency.

The range is half-open, `[start, end)`, so **back-to-back slots do not conflict**. The
constraint needs the standard `btree_gist` extension — the same one S8 needs for
`game_participant`.

## Open items that touch this module

- **G-12** — "own availability slots must not overlap each other" is implemented here,
  but G-12 as a whole is still a proposed resolution.
- **G-10** — accepting a game does **not** consume or split a slot. Nothing in this
  module reserves time; only confirmed games block time (PRD §12.4).
