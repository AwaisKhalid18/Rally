# M1 — Identity

Accounts, credentials, sessions and the email-verification lifecycle.

| | |
| --- | --- |
| **Owns** | `account` (email *private*, phone *private, optional*, password hash, verification state), `session` — Django's session table (AGENTS.md §3.1) |
| **Depends on** | Nothing |
| **Serves** | FR-01, FR-14; ASR-04, ASR-05, ASR-06 |
| **Slice** | S1 (register, sign in, sign out). Verification lands in S2. |

## Published interface — `rally.modules.identity.api.facade`

| Operation | Returns | Notes |
| --- | --- | --- |
| `register(email, password)` | `RegistrationResult` | Creates an **unverified** account. Errors are a field → message mapping. |
| `authenticate(email, password)` | `AuthenticationResult` | One generic reason on failure (PRD §12.2). |
| `account_summary(account_id)` | `AccountSummary \| None` | Account id and verification state. No contact data. |
| `is_verified(account_id)` | `bool` | The gate M2 folds into searchability and M5 checks before a send (ASR-06). |
| `get_delivery_address(account_id)` | `str \| None` | **M7 only, at send time.** Never stored, never logged (architecture §6.1). |

## Published read view

`v_verified_account(account_id, is_verified)` — defined in `migrations/0002_v_verified_account.py`,
declared in `views/__init__.py`. Permitted consumer: `profile` (M2). Changing a column is a
contract change, not an internal refactor (ADR-002).

## Rules this module carries

- **Rule 6.** `email` and `phone` exist only here. They are in no view, payload, notification or log.
- **Rule 7.** There is no location field in this schema.
- **ADR-003.** M1 verifies credentials; Platform binds the session; M1 authorises access to
  its own records.

## Not here

Profile content, availability, search, invitations, games, blocks — and no knowledge that
any of them exist.
