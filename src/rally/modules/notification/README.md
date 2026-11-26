# M7 — Notification

In-app notifications, email dispatch, the retry policy and delivery state.

| | |
| --- | --- |
| **Owns** | `outbox`, `notification` |
| **Depends on** | M1 Identity only — the delivery address and the verification token, read at send time and dropped again (architecture §6.1 recorded refinement) |
| **Serves** | FR-10, FR-12; ASR-11, ASR-12 |
| **Slice** | S2 (outbox, worker, verification email). Invitation notifications arrive in S10. |

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

1. *transaction* — claim the row `FOR UPDATE SKIP LOCKED`, create the in-app
   notification (idempotent on `source_outbox`).
2. *no transaction* — compose the message, read the address from M1, call the adapter.
3. *transaction* — record what the provider actually reported.

The in-app notification always succeeds locally, so a provider outage degrades email
only (ASR-12).

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

## Published read view

None. Nothing depends on M7 (AGENTS.md §3).
