# M5 — Invitation & Games

The invitation state machine, acceptance, confirmed games, cancellation and the
no-double-booking invariant. The system's only multi-actor stateful workflow.

| | |
| --- | --- |
| **Owns** | `invitation`. `confirmed_game` and `game_participant` arrive with **S8** |
| **Depends on** | M3 Availability, M6 Safety, M2 Profile — **not M1** |
| **Serves** | FR-08, FR-09, FR-10, FR-11, FR-15; ASR-07 … ASR-11 |
| **Slice** | S7 builds **send and list**. Accept/decline S8, cancel and expiry S9, the games screen S11, `cancelPendingBetween` S12. |

## Published interface — today

| Operation | Notes |
| --- | --- |
| `send(sender, recipient, starts_at, ends_at, venue)` | Returns the new id, or a field → message mapping. |
| `list_for_player(account_id)` | `(sent, received)`, newest first. |
| `get_for_participant(invitation_id, account_id)` | `None` for a non-participant — the caller turns that into a **not-found**, never a "forbidden", which would itself confirm the invitation exists (ASR-05). |

Still to come: `accept`, `decline`, `cancelInvitation`, `cancelGame`, `expirePending`,
`cancelPendingBetween`.

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
  time — which is why there is no `confirmed_game` table yet.

## Open items that touch this module

- **G-12** — the venue bounds (2–100) are a proposed resolution, not a decision.
- **A-08** — `has_availability` requires one slot to cover the whole window; two
  adjoining slots do not add up.
