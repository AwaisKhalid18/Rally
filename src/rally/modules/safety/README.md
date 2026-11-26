# M6 — Safety

Block relationships and their cascade; reports.

| | |
| --- | --- |
| **Owns** | `block` · `report` **arrives in S12** |
| **Depends on** | Nothing |
| **Serves** | FR-03, FR-08, FR-14, PRD §12.5; ASR-10 |
| **Slice** | **S5 builds a stub**: the `block` table and `v_block_pairs`, so M4's predicate can honour blocking from its first line. The feature — screens, unblock list, `report`, and the cancellation cascade through the `PendingInvitationCanceller` port — is S12. |

## Why M6 publishes rather than applies

A block changes behaviour in search *and* in invitation eligibility. If M6 called into
those paths it would invert the dependency and create a cycle (architecture §5.1). So M6
publishes one rule and its consumers apply it:

- **M4** reads `v_block_pairs` inside the search query (S5, done).
- **M8** will read it for the favorites list (S13).
- **M5** will ask `is_blocked_between()` before a send (S7).

That is also what stops the duplicate implementations ASR-10 warns about.

## Published read view

`v_block_pairs(blocker_account_id, blocked_account_id)` — one row per *directed* block.

The row is directed; the **effect is symmetric**. A consumer must check both directions,
because blocking hides the pair from each other (PRD §12.5). M4's query does.

## Published interface — today

| Operation | Notes |
| --- | --- |
| `is_blocked_between(a, b)` | Symmetric. |
| `block_for_test(blocker, blocked)` | The narrow seam S5 needs so the search predicate can be *proved* to honour blocks. **S12 replaces it** with the real `block()`, its transaction and its cascade. |

Still to come in S12: `block()`, `unblock()`, `report()`, and the
`PendingInvitationCanceller` port that M5 implements.

## Rules this module carries

- **Rule 1 / 2.** M6 depends on nothing and imports no module. `account_id` values are
  plain integers.
- **Rule 15.** The block cascade will cross back to M5 through a port, never a reverse
  import (ADR-007 R-02).
- **Unblocking** restores visibility but must not resurrect cancelled invitations (S12).
