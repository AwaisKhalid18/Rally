# M6 — Safety

Block relationships and their cascade; reports.

| | |
| --- | --- |
| **Owns** | `block`, `report` |
| **Depends on** | Nothing |
| **Serves** | FR-03, FR-08, FR-14, PRD §12.5; ASR-10 |
| **Slice** | S5 built the stub: the `block` table and `v_block_pairs`, so M4's predicate could honour blocking from its first line. **S12 is the feature**: the screens, the unblock list, `report`, and the cancellation cascade through the `PendingInvitationCanceller` port. |

## Why M6 publishes rather than applies

A block changes behaviour in search *and* in invitation eligibility. If M6 called into
those paths it would invert the dependency and create a cycle (architecture §5.1). So M6
publishes one rule and its consumers apply it:

- **M4** reads `v_block_pairs` inside the search query (S5).
- **M5** asks `is_blocked_between()` before a send (S7).
- **M8** will read it for the favorites list (S13).

The one thing M6 *does* reach out for is the cancellation cascade, and that goes through
a port — see below.

That is also what stops the duplicate implementations ASR-10 warns about.

## Published read view

`v_block_pairs(blocker_account_id, blocked_account_id)` — one row per *directed* block.

The row is directed; the **effect is symmetric**. A consumer must check both directions,
because blocking hides the pair from each other (PRD §12.5). M4's query does.

## Published interface

| Operation | Notes |
| --- | --- |
| `is_blocked_between(a, b)` | Symmetric: true when **either** has blocked the other. |
| `block(blocker, blocked)` | One transaction: the row, the cascade, the outbox records. |
| `unblock(blocker, blocked)` | Your own block only. Restores visibility, not invitations. |
| `list_blocked(blocker)` | Who **you** blocked. Never who blocked you. |
| `report(reporter, reported, category, details, invitation_id)` | Category required, text optional. |
| `REPORT_CATEGORIES` | The four G-13 categories, published so the form and the rule cannot drift apart. |

There is deliberately **no operation that reads a report back**, and none that tells a
player who blocked them. Both absences are the feature.

`block_for_test()` is gone: S12 replaced it with the real `block()`.

## The cascade, and why it needs a port

Blocking must cancel the pending invitations between the pair (PRD §12.5), and that must
commit **with** the block — a block that committed while the cancellation failed would
leave the pair an invitation they can still act on, which is the hole ASR-10 exists to
close. There is a test for exactly that: make the cascade raise, and the block must not
survive it.

But `safety → nothing`, so M6 may never import M5. So:

```
M6.block()  --cancel_pending_between-->  port PendingInvitationCanceller
   (M6's transaction)                      |  declared by M6, bound at startup
                                           v
                                      M5 cancels its own rows, opens no
                                      transaction, notifies nobody
```

The source dependency runs `invitations → safety`, which the allowlist grants; the call
crosses back at run time only (rule 15, ADR-007 R-02). `import-linter` names
`rally.modules.invitations` in M6's forbidden list so a direct import can never creep in.

**M6 appends the outbox records, not M5.** M6 is the module that knows a block caused
this, so only M6 can word it safely — and the ids come back from the port so M6 never
reads M5's tables (rule 1).

### What the blocked player is told

That an invitation is gone. **Not that they were blocked.** The PRD does not resolve
whether a blocked player learns of the block, and telling them would make blocking
unsafe to use, so the cascade raises its own event type
(`invitation.cancelled_by_block`) whose wording never mentions it. Reusing
`invitation.cancelled` would have said "the player who sent it withdrew" — false here,
and a pointer straight at the block. A test asserts the words "block", "blocked" and
"blocking" appear in neither the page nor the email.

Only the player who did *not* block is notified. Nobody is told of their own action.

## Reports

Stored and never read back. PRD §12.5 says reports are "stored for review by the project
administrators"; review happens directly in the database and there is no admin screen
(an accepted limitation, AGENTS.md §5). A report a player could read would turn into a
channel between the two of them, and Rally has no chat (§7). The reported player is not
notified either.

The four categories — Harassment, Fake profile, Inappropriate content, Other — are
**G-13's proposal and not yet client-confirmed**.

## Rules this module carries

- **Rule 1 / 2.** M6 depends on nothing and imports no module. `account_id` values are
  plain integers.
- **Rule 15.** The block cascade crosses back to M5 through a port, never a reverse
  import (ADR-007 R-02). Enforced by contract, and the wiring is tested.
- **Rule 3.** M6 does not import M7 either. It appends through Platform's port.
- **Unblocking** restores visibility and does **not** resurrect cancelled invitations.
- **Confirmed games are untouched** by a block (PRD §12.5). Blocking is not a way out of
  a game; either player cancels it the normal way.
