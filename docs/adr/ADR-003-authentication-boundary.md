# ADR-003 — Authentication and Authorisation Boundary

- **Status:** Proposed — pending final team review and clarification of public account-setup endpoints
- **Decision owner:** Fazeel (ADR lead), recording the team's decision
- **Drivers:** ASR-04, ASR-05, ASR-06; QA-02; PRD §§12.2 and 12.6
- **Source:** `architecture.md` §§5 (M1, M2, Platform), 6.1, 6.7, 12, 16.7; *Architecture Process Evidence*, Part 3 D-06/D-07

## Context

Rally requires email/password registration, email verification, and session-based access. Players should be able to edit only their own account/profile, and view only invitations they sent or received. An unverified profile must not appear in search; unverified players cannot send invitations. The system must not accidentally return another player's email, phone, or exact location.

There are **two different questions**: (1) Is the request made by a valid signed-in player? (2) Is that player allowed to operate on the particular record? The first is platform-wide; the second depends on business meaning and data ownership.

## Alternatives considered

| Alternative | Advantage | Why not chosen |
| --- | --- | --- |
| All authentication and ownership checks in Platform | One location for every check | The platform would need to understand invitation participants, profile owners, favorites owners, and other business rules. This mixes domain policy into the transport layer. |
| Each module authenticates and authorises every request | Domain logic stays local | Repeats session verification in many places; increases the risk that one endpoint forgets to authenticate. |
| **Split authentication and authorisation** | Consistent session enforcement plus domain-specific record checks | Ownership checks are distributed and require systematic review. |

## Decision

Use **two levels of enforcement**:

1. **Platform:** Validate the session on protected requests *before* dispatching to a business module. M1 Identity is the authority for accounts, sessions, and email-verification state.
2. **Owning modules:** Enforce record-level authorisation. For example, M1 permits only the account owner to access private account data; M2 permits only the profile owner to edit a profile; M5 checks that the player is a participant in the invitation/game; M8 restricts favorites and saved searches to their owner.

Verification state is provided through M1's narrow published state and respected by M2 for searchability and M5 for invitation eligibility. Response shaping in Platform emits explicit public view models, never raw domain entities. Contact information stays within M1 and does not appear in other players' search, invitation, or notification payloads.

## Rationale

The shared pipeline makes authentication consistent. The owner of a record knows its permission rules best, so authorisation belongs there. This avoids a Platform component that becomes coupled to every domain model and is clearer for an AI coding agent to follow.

## Trade-offs and consequences

- Every owning module must define and test its access rules, including direct API requests that bypass the user interface.
- Platform must not replace ownership checks with a client-supplied user ID or assume a hidden button provides security.
- Authentication and public response shaping are separate barriers; both are needed for the confidentiality target.
- Session mechanism specifics are not selected in the source documents and require approval if they materially shape the design.

## Open consistency question before acceptance

The baseline contains a blanket statement that no handler is reachable without an authenticated session, yet the PRD also requires **registration, sign-in, and email verification**. The final architecture and `AGENTS.md` need an explicit, tightly scoped rule for which account-setup endpoints are accessible without an established session; otherwise the design would prevent new players from joining. This is a clarification, not permission to expose protected profile/search/invitation operations anonymously.

## Consistency and verification

- Check unauthenticated and other-player direct API requests against NFR-03 privacy test cases.
- Check an unverified account is excluded from search and cannot send invitations.
- Check M5 and M8 enforce owner/participant access even when called with a valid session.
- Review `AGENTS.md` for the approved public-endpoint exceptions and privacy field restrictions.
