# M5 — Invitation & Games

The invitation state machine, acceptance, confirmed games, cancellation and the
no-double-booking invariant. The system's only multi-actor stateful workflow.

| | |
| --- | --- |
| **Owns** | `invitation`, `confirmed_game`, `game_participant` |
| **Depends on** | M3 Availability, M6 Safety, M2 Profile — **not M1** |
| **Serves** | FR-08, FR-09, FR-10, FR-11, FR-15; ASR-07 … ASR-11 |
| **Slice** | S7 send and list · S8 accept, decline, confirmed game · S9 cancel and expiry · S11 the games screen and `cancelGame`. `cancelPendingBetween` is S12. |

## Published interface — today

| Operation | Notes |
| --- | --- |
| `send(sender, recipient, starts_at, ends_at, venue)` | Returns the new id, or a field → message mapping. |
| `list_for_player(account_id)` | `(sent, received)`, newest first. |
| `accept(invitation_id, account_id)` | One transaction. Returns the game id, or a **domain reason** — never a database error. |
| `decline(invitation_id, account_id)` | No reason required (PRD §12.3). |
| `cancel_invitation(invitation_id, account_id)` | The **sender** withdraws a pending invitation; the recipient is notified. |
| `expire_pending()` | Worker only. Refreshes stored status; notifies nobody. |
| `get_game_for_invitation(invitation_id, account_id)` | The game an accepted invitation created, for a participant only. |
| `list_games_for_player(account_id)` | `(upcoming, finished)`. Both participants see the same game; only *who cancelled it* differs. |
| `get_game_for_participant(game_id, account_id)` | `None` for anyone else — a not-found, never a "forbidden" (ASR-05). |
| `cancel_game(game_id, account_id)` | **Either** participant, any time before the start. No reason. The other player is notified. |
| `get_for_participant(invitation_id, account_id)` | `None` for a non-participant — the caller turns that into a **not-found**, never a "forbidden", which would itself confirm the invitation exists (ASR-05). |

Still to come: `cancelPendingBetween` (S12, M6's port).

## The state machine (PRD §12.3)

```
            accept()  ──▶ Accepted   (+ a separate confirmed_game)
           decline()  ──▶ Declined
Pending ─┤ cancel()   ──▶ Cancelled  (sender only)
           deadline   ──▶ Expired
```

All four are terminal. Nothing leaves a terminal status, and nothing outside M5 may
change one (ASR-07). Every transition re-reads the row under `FOR UPDATE` and judges it
afresh, so **the first committed action wins** and the loser is told why.

## Expiry: authoritative at commit, swept for display

`expires_at = min(created + 24h, proposed start)`, stamped from the server clock
(PRD §12.3, ASR-09). The deadline is **inclusive**: at `expires_at` exactly the
invitation has expired; one second earlier it can still be answered.

Every transition — accept, decline and cancel alike — re-checks it. So an expired
invitation cannot be acted on **whether or not the sweep has ever run**.
`expire_pending()` only refreshes the stored status so the listing reads correctly. A
stalled worker therefore makes the display stale and nothing worse (ADR-005).

Expiry **notifies nobody**: the PRD sends no reminders and no expiry notice.

The reason given is stable. An invitation past its deadline says *"this invitation has
expired"* whether or not the sweep has already refreshed its stored status — the expiry
check is named before the generic "no longer pending". The sweep-vs-accept race found
this: before the fix the wording depended on who won, and both answers refused the
acceptance correctly but only one of them said why.

## Accepting: the transaction (ASR-08, ADR-004)

```
BEGIN
  re-read the invitation FOR UPDATE
  still Pending?   not expired by server UTC?
  recipient still available?            (M3, a read, inside this transaction)
  no overlapping confirmed game for EITHER player?
  insert confirmed_game and two game_participant rows
  set the invitation Accepted
  append the outbox record
COMMIT
```

Every transition re-reads and re-judges under a row lock, so **the first committed
action wins** and the loser is told why (ASR-07). Expiry is judged here, at commit —
never by whenever the sweep last ran (ASR-09).

### Why `game_participant` exists

A `confirmed_game` row carries *both* players, and a PostgreSQL exclusion constraint
compares **rows**, so keyed there it could only ever protect one of them. One row per
player lets a single constraint say "no player has two overlapping games". This is the
gap the agent validation recorded as **AV-05**, closed here.

Double-booking is enforced **twice** (ADR-004):

1. an application check, so the player gets a sentence;
2. `game_participant_no_overlap`, an exclusion constraint on `(account_id, [start, end))`
   where `cancelled_at IS NULL` — which is what actually holds under concurrency.

The range is half-open, so **back-to-back games do not conflict**. The insert runs in a
savepoint, so losing the race to the constraint leaves the transaction usable and the
player still gets a sentence rather than an `IntegrityError`.

Cancelled participations are outside the constraint, so cancelling a game frees the time
immediately without any slot being written (G-10).

## Cancelling a confirmed game (S11, PRD §12.4)

**Either** participant, at any time **before** the start — the boundary is inclusive, so
at the start time exactly it is too late. No reason is asked for, and the caller must
have presented an explicit confirmation step first. A non-participant is told the game
does not exist (ASR-05).

Cancelling stamps `cancelled_at` on the game and on **both** participant rows, and
records who did it. It does **not** touch the invitation: that stays Accepted for good.
Cancelling a game is not un-accepting an invitation (PRD §12.3).

Only the other player is notified. Nobody is told about their own action.

### Why no availability slot is written (G-10)

PRD §12.4 says the slot "is restored for both players", and architecture §8.5 repeats
it. Nothing ever consumed one: accepting writes participant rows, never a slot. The time
is free again the instant `cancelled_at` is set, because both the overlap check and the
exclusion constraint ignore cancelled participations — tested by cancelling a game and
then successfully accepting an invitation that overlaps it. The outcome the PRD asks for
is reached with no slot write, which is AGENTS.md §9 **G-10**. The architecture wording
should be amended to match; recorded as an open item.

## Why M5 does not call M1

The allowlist grants `invitations → availability, safety, profile` and nothing else. The
sender's verification gate (ASR-06) is therefore read through **M2**, which relays M1's
published view — exactly the route architecture §6.3 describes, "verify sender is
verified (M1 via M2)". M5 never sees a contact address because it has no path to one.

## Sending: the rules, and where they run

Refused, each with its own message (PRD §12.3, §12.4):

unverified sender · inviting yourself · a recipient who does not exist · a block in
**either** direction · end ≤ start · a start already past · the recipient not available
for the **whole** window · an overlapping Pending invitation from the same sender to the
same recipient.

Availability and the duplicate rule are re-checked **inside** the transaction that
creates the invitation, because another request could have changed either since the
first look. The facades M5 calls are reads, so none opens a transaction of its own
(rule 4), and nothing external is touched inside it (rule 5).

`expires_at = min(created + 24h, proposed start)`, stamped from the server clock
(ASR-09). It is re-evaluated at every transition, so a late sweep can never let an
expired invitation be acted on.

## The outbox

The invitation and its `invitation.sent` event are committed **together or not at all**,
through Platform's `OutboxAppender` port. M5 does not import M7 (rule 3), and the event
carries ids only — no venue, no time, no name. The email M7 composes is a nudge with a
link; the in-app record stays the source of truth for what the invitation says
(architecture §6.6, ASR-11).

## Honest feedback

Success is reported **only after commit** (FR-08). A refused send creates nothing,
queues nothing, and never shows a success message.

## Rules this module carries

- **ASR-07.** M5 exclusively owns invitation state. Nothing else may change a status.
- **Rule 6.** M5 holds no contact data; a participant sees the other party by display
  name only, and nothing becomes visible because an invitation exists (PRD §12.2).
- **PRD §12.4.** A pending invitation reserves nothing. Only a confirmed game blocks
  time, and it does so through the participant rows, not by consuming a slot (G-10).
- **PRD §12.3.** An *accepted invitation* and a *confirmed game* are different things.
  The invitation stays Accepted and the game is its own record.

## Open items that touch this module

- **G-12** — the venue bounds (2–100) are a proposed resolution, not a decision.
- **A-08** — `has_availability` requires one slot to cover the whole window; two
  adjoining slots do not add up.
