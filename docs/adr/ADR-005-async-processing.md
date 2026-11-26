# ADR-005 — Asynchronous Notifications and Authoritative Time Transitions

- **Status:** Proposed — pending final team review and resolution of the outbox-write contract
- **Decision owner:** Fazeel (ADR lead), recording the team's decision
- **Drivers:** ASR-09, ASR-11, ASR-12; QA-04; FR-04, FR-11, FR-12
- **Source:** `Final_Validated_PRD.md` §§12.1, 12.3, 12.6; `architecture.md` §§1.4, 6.3–6.6, 7, 8.4–8.5; *Architecture Process Evidence*, Part 3 D-08

## Context

Rally must notify players of invitation outcomes using in-app information and email. Email is an external dependency and can fail. The PRD calls for an attempt within five minutes and up to three retries within fifteen minutes. That work cannot block a player's invitation request or cause a valid committed game to fail simply because email is unavailable.

Time-driven maintenance also exists: invitations expire when their deadline arrives, and past availability slots should be removed. A background process can run late or stop temporarily, so **correctness must not depend on when a cleanup job happens to execute**.

## Alternatives considered

| Alternative | Advantage | Why not chosen |
| --- | --- | --- |
| Send email inside the request/transaction | Direct and simple | Provider failure or latency can delay/fail a business operation; email cannot be rolled back after a database failure. |
| External queue and separate notification service | Independent scaling | Adds infrastructure and a new operational boundary without a justified MVP need. |
| Sweep job as the only expiry authority | Straightforward scheduled code | A delayed sweep could let a logically expired invitation be accepted. |
| **Transactional outbox + worker; commit-time expiry checks** | Decouples external email failure while preserving authoritative state | Worker failure can delay notifications and displayed cleanup; the outbox ownership contract requires clarity. |

## Decision

Use an **outbox-backed background worker** built from the same codebase as the web application:

1. A business action creates the required outbox record atomically with its business-state update.
2. The worker polls due outbox records, creates or updates in-app notification state, resolves the email address through M1 at send time, and calls the external email provider via M7's adapter.
3. The worker records the actual provider outcome; failed email attempts are retried up to three times within fifteen minutes, then logged. It must not claim confirmed delivery without supporting provider evidence.
4. Every invitation transition evaluates its expiry using **server UTC at the point of commit**. The background sweep updates stored/displayed expiry state and removes past availability slots but is not the source of truth for whether acceptance is permitted.

The in-app invitation record remains the authoritative record of invitation state. Email address must never be copied into `outbox`, `notification`, or logs. There is no direct business-module dependency on M7 and no external call within a business transaction.

## Rationale

The outbox avoids losing an email event when a state-changing transaction commits while the email service is down. Keeping expiry authoritative at commit avoids false acceptance when the sweep is delayed. This meets the reliability constraint without introducing external messaging infrastructure.

## Trade-offs and consequences

- Worker outages can delay email and the freshness of displayed expired statuses, **but they must never create an invalid accepted invitation or overlapping game**.
- Notification delivery is eventually processed rather than guaranteed during the initial request.
- Retries require auditable attempt counts and failure logs without private contact details.
- The definition of a provider-confirmed delivery is an open item (G-03); provider acceptance of a send request is not necessarily proof the recipient read the email.
- The baseline says M7 owns `outbox` but M1/M5/M6 must write it atomically. An explicit append-only write contract or equally clear approved exception is required before this ADR can be considered fully settled (also flagged in ADR-002).

## Consistency and verification

- Simulate email-provider outage: invitation operations should still succeed if their own data transaction succeeds.
- Simulate a stopped worker: an expired invitation must still be impossible to accept.
- Check the three-retry/fifteen-minute policy and recording of genuine provider outcomes.
- Check that no log/outbox/notification payload stores email addresses.
- Compare `architecture.md`, the agreed outbox write policy, and `AGENTS.md` for consistency.
