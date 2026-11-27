# M7 — Notification

In-app notifications, email dispatch, the retry policy and delivery state.

| | |
| --- | --- |
| **Owns** | `outbox`, `notification` |
| **Depends on** | M1 Identity only — the delivery address and the verification token, read at send time and dropped again (architecture §6.1 recorded refinement) |
| **Serves** | FR-10, FR-12; ASR-11, ASR-12 |
| **Slice** | S2 (outbox, worker, verification email) · S10 (the in-app inbox, read/unread, honest email status). |

## How a module notifies without knowing M7 exists

```
M1/M5/M6  --append(event_type, entity_refs)-->  Platform port OutboxAppender
                                                        |  bound at startup
                                                        v
                                                M7 writes the outbox row
```

No business module imports M7 (rule 3) and M7 stays the only writer of `outbox`
(rule 1). The appender runs **inside the caller's transaction**, opens none of its own
(rule 4) and makes no external call (rule 5). It refuses any `entity_refs` value that
looks like a contact address.

## How a record is dispatched

The worker (`python manage.py run_worker`) drives it. Each record goes through three
steps so that **no transaction encloses the provider call** (rule 5):

1. *transaction* — claim the row `FOR UPDATE SKIP LOCKED`.
2. *no transaction* — compose the message, read the address from M1, call the adapter.
3. *transaction* — record what the provider actually reported.

The in-app notification is **not** created here. The appender writes it in the
transaction that changed the business state, so it is committed with the accept, decline
or cancellation that caused it and exists before the worker ever looks. A provider
outage — or a worker that never starts — therefore degrades email only, and the player's
inbox is still complete (S10 AC2, ASR-12).

## Retry policy (PRD §12.3)

| | |
| --- | --- |
| Attempts | 4 — the first attempt plus 3 retries |
| Interval | 5 minutes |
| Window | 15 minutes, then the record is marked `failed` and logged |

Status wording is `queued`, `sent`, `failed`. **`sent` means the provider accepted the
message; it never means delivered** — G-03 is still open and the product must not claim
a delivery the provider did not confirm.

## The external boundary

One provider, Brevo, behind `internal/adapters.py` and reached through Django's SMTP
backend — no new library. The default backend writes to the console, so the demo and the
tests never depend on a live provider (G-14); `RALLY_EMAIL_LIVE=1` switches it on.

## Rules this module carries

- **Rule 6.** No address in `outbox`, in `notification`, or in any log. Tested.
- **Rule 1.** Only M7 writes `outbox` and `notification`; nothing reads them.
- **Rule 3.** Nothing imports M7. Platform's worker host is its only caller.

## The in-app inbox (S10)

| Operation | Notes |
| --- | --- |
| `list_for_player(account_id, limit=50)` | Newest first. Event types and ids — no wording, no links, no address. |
| `unread_count(account_id)` | The header badge. |
| `mark_read(notification_id, account_id)` | Owner only. `False` for a stranger's row **and** for one that does not exist: a different answer would confirm it exists (ASR-05). |
| `mark_all_read(account_id)` | Returns how many were marked. |

M7 says *what* happened; Platform's shaper decides how it is worded and where it links.
A notification is never deleted when it is read — the inbox is a record of what happened.

### The email status a player sees

`queued`, `sent`, `failed`. Nothing else, and **never "delivered"**: `sent` means the
provider accepted the message (AGENTS.md §5 Honest feedback, FE-5, G-03). When a
notification has no outbox record at all, the page shows the reason, not a blank
(rule 13).

## Published read view

None, and nothing depends on M7 (AGENTS.md §3): no capability module may call it. The
facade's two groups of operations are both for **Platform** — the worker host dispatches
and the web host renders a player's own inbox, which is rule 14 doing its job.
