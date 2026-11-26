# ADR-002 — Data Persistence, Ownership, and Published Read Views

- **Status:** Proposed — pending final team review and the open location-source decision (G-02)
- **Decision owner:** Fazeel (ADR lead), recording the team's decision
- **Drivers:** ASR-01, ASR-02, ASR-03, ASR-04, ASR-06, QA-06
- **Source:** `Final_Validated_PRD.md` §§12.1, 12.2, 12.6; `architecture.md` §§5, 6.1, 8.1–8.3, 16.6–16.7; *Architecture Process Evidence*, Part 3 D-03/D-04/D-06 and amendment D-09

## Context

Searching for a partner depends on profile information, future availability, verified account state, and blocking rules. A search should apply these restrictions together and rank results efficiently. But a module should not be able to change another module's records or retrieve sensitive contact information simply to perform its job. The design therefore needs a balance between **fast cross-module reads** and **clear ownership of data**.

The privacy requirements make two facts especially important: emails and phone numbers must stay private, and the MVP must not collect or store exact player locations. Distances are derived from general-area centroids and shown as approximate.

## Alternatives considered

| Alternative | Benefit | Concern |
| --- | --- | --- |
| Allow any module direct table access | Easy joins | Breaks ownership and makes privacy and data changes hard to audit. |
| Strict interface-only access for every read | Strong encapsulation | Forces a search to combine several interface calls and results in memory; complicates the defined single-query search approach. |
| Maintain a separate denormalised read model (CQRS) | Fast specialised reads | Adds synchronisation, duplication, and freshness concerns at a scale that does not justify them. |
| **Module-owned tables plus published read views** | Efficient SQL query with a controlled read contract | View changes need coordination with every consumer. |

## Decision

Use **one relational database**. Every business table has a designated owner; that owner controls updates to it. Other business modules use its published interface. To support search, owners publish carefully limited, **read-only database views**:

| View | Publishing module | Allowed public data |
| --- | --- | --- |
| `v_verified_account` | M1 Identity | Account reference and verification state; never email or phone. |
| `v_searchable_profile` | M2 Profile | Account reference, public display information, general area/centroid, searchable flag. |
| `v_active_availability` | M3 Availability | Future availability slots. |
| `v_block_pairs` | M6 Safety | Account references needed to enforce blocking. |

M4 Search & Matching may read the published views to perform filtering and ranking, but **must not write source tables**. The November 11 amendment permits M8 Player Collections to read the same public views for favorites display (ADR-006). No published view may contain contact information or a player's exact location. M1 owns account and session records; M2 owns profile and area; M3 owns availability; M5 owns invitations and games; M6 owns blocks and reports; M7 is listed as owner of notification and outbox records; M8 owns favorites and saved searches.

Do not choose a specific database product here without team approval; it was not fixed in the supplied architectural baseline.

## Rationale

A single relational database lets M4 execute the matching predicate efficiently while narrow views enforce a **public data contract**. Module ownership reduces accidental changes to another module's business data. Read views avoid the duplicate data and stale results that a separate search database could introduce.

## Trade-offs and consequences

- Read views become versioned **cross-module contracts**, not internal implementation details. Adding, removing, or renaming a column needs consumer review.
- Query tuning and indexes remain important to the ≤2-second search target; the architectural choice alone does not prove performance.
- Other modules must not write M1's contact information or introduce exact-location columns.
- For FR-16 and FR-18, M8 stores account/area references, not copies of profile information or coordinates.

## Open consistency questions before acceptance

1. **G-02 — general-area source:** The team has not settled a fixed list of areas versus geocoded free text. Geocoding would introduce another external service, contradicting the current one-provider assumption. Decide this before implementation or claiming ADR-002 is final.
2. **Outbox write boundary:** `architecture.md` says M7 *owns* `outbox`, but also says M1/M5/M6 write outbox entries inside their own transactions. That conflicts with the blanket rule that only the table owner writes it. Agree and document an explicit append-only transaction interface or another narrowly specified ownership arrangement; do not silently pretend the conflict is absent.
3. **Database selection:** The precise database engine remains open and needs to support the overlap-integrity strategy required by ADR-004.

## Consistency and verification

- Examine a proposed schema for any exact-location, public contact, or copied profile fields.
- Verify M4 and M8 access only the allowed views, not source tables.
- Review view changes against both M4 and M8, and ensure the final `AGENTS.md` records the chosen outbox-write contract.
