# ADR-004 — Atomic Invitation Acceptance and Double-Booking Prevention

- **Status:** Proposed — team decision recorded, pending final review and database-specific enforcement plan
- **Decision owner:** Fazeel (ADR lead), recording the team's decision
- **Drivers:** ASR-07, ASR-08, ASR-09; QA-03; FR-08, FR-09, FR-11, FR-15
- **Source:** `Final_Validated_PRD.md` §§12.3, 12.4; `architecture.md` §§6.4–6.5, 8.4; *Architecture Process Evidence*, Part 3 D-05

## Context

A recipient accepting an invitation immediately creates a confirmed badminton game. But pending invitations do not reserve a player's time, so a player can receive several invitations for overlapping periods. If two overlapping invitations are accepted at almost the same moment, both requests could check that the player is free and both could incorrectly create a game. A simple check made before saving is not sufficient under concurrency.

The PRD also requires a strict invitation lifecycle. Only **Pending** can transition to Accepted, Declined, Cancelled, or Expired; all other statuses are terminal. Expiry occurs 24 hours after creation, or at the proposed game start, whichever is earlier, measured using server time.

## Alternatives considered

| Alternative | Advantage | Limit |
| --- | --- | --- |
| Application-level check only | Easy to write and produce friendly errors | Both concurrent requests can pass before either inserts a confirmed game (race condition). |
| Optimistic concurrency/retries alone | Allows good throughput in many workloads | Needs carefully designed conflict detection for time overlaps, not just a version on one invitation. |
| Pessimistic locking alone | Serialises relevant work | Locking needs a consistent granularity and order; implementation mistakes can still leave gaps or cause contention. |
| **One M5 transaction plus database-enforced overlap integrity** | Protects the state transition and the cross-invitation game invariant at commit | Database-specific constraint/index strategy needs deliberate implementation and error translation. |

## Decision

**M5 Invitation & Games exclusively owns the confirmation invariant and its transaction.** When accepting an invitation, it performs the following as one atomic operation:

1. Start a transaction and lock/re-read the invitation.
2. Verify the caller is the recipient, the invitation remains Pending, and it has not expired according to server UTC.
3. Revalidate the recipient's availability through M3 using the same transaction context.
4. Check that **neither participant** already has an overlapping confirmed game.
5. Create the confirmed-game record, mark the invitation Accepted, and write the notification outbox entry.
6. Commit once; show success only after the commit succeeds.

An overlapping game means one interval begins before the other ends **and** ends after the other begins. Enforce the invariant through both a readable application-level check **and** a database-level mechanism that rejects conflicting commitments. Any module interface participating in M5's transaction must join it and must not independently commit. No database transaction may include an email/network call.

If two actions race, exactly one valid action may commit. The losing request receives a clear domain message (for example, 'This invitation is no longer pending' or 'You already have an overlapping game'), never a raw database error.

## Rationale

A single local transaction prevents half-completed acceptance, such as marking an invitation Accepted without creating a game. The database backstop is essential because application checks can race. The explicit M5 ownership makes it clear where this business invariant belongs and prevents an AI agent from reimplementing it in M3 Availability or M4 Search.

## Trade-offs and consequences

- Acceptance may incur locking/conflict handling overhead; correctness takes priority over throughput for this operation.
- The overlap mechanism must cover **both players** and all relevant confirmed-game records, not only duplicate invitation IDs.
- The exact locking, schema, and exclusion/index strategy depend on the relational database the team approves; do not assume every database supports the same constraint syntax.
- A rejected concurrent acceptance must be translated to a useful player-facing message.
- Confirmed-game cancellation is separate from invitation cancellation; cancelling a game must not rewrite the terminal Accepted invitation status.

## Consistency and verification

- Race-test two responses on the same pending invitation.
- Race-test simultaneous acceptance of two different invitations sharing a player and overlapping in time.
- Confirm zero overlapping committed games for either player, and no partial invitation/game/outbox records.
- Test expiry at the exact earlier of the two deadlines, and reject transitions from terminal states.
- Check `architecture.md` §6.5 and `AGENTS.md` state the same transaction rules.
