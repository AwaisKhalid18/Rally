# ADR-006 — Ownership of Personal Collections and Extension of Read Views

- **Status:** Proposed — November 11 amendment is not included in the supplied Final Validated PRD
- **Decision owner:** Fazeel (ADR lead), recording the team's amendment decision
- **Requirements:** FR-16 (favorites), FR-17 (compare up to three players), FR-18 (saved searches)
- **Drivers:** ASR-02, ASR-03, ASR-04, ASR-05, ASR-10; QA-06
- **Source:** `architecture.md` §16.1–§16.13; *Architecture Process Evidence*, Part 3 amendment D-09–D-11 and ADR input

## Context

After the original architecture was agreed, three requirements were added: players may favorite other players, compare up to three partners, and save/reuse named searches. The architecture already has a **read-only, table-free** search module (M4) and a **safety** module (M6). New saved data therefore requires an owner without weakening those established boundaries.

Favorites are owner-private lists, and saved searches contain search criteria including an area reference. Neither should expose another player's email or exact location. Favorites display current public profile and availability details, so copying those details into personal collections risks stale information.

## Alternatives considered

| Alternative | Why rejected or accepted |
| --- | --- |
| Store `saved_search` inside M4 | Rejected: M4 would no longer be read-only or table-free. |
| Store `favorite` inside M6 Safety | Rejected: a convenience list and a safety-enforcement relationship have different responsibilities. |
| Create separate favorites and saved-search modules | Rejected: largely identical ownership, access, and lifecycle rules would be duplicated. |
| Cache copied profile/availability fields in collection records | Rejected: duplicates information that can change and expands the risk of exposing other players' data. |
| **Create M8 Player Collections, referencing the published public views** | Selected: preserves M4/M6 boundaries and keeps only owner-private references and criteria. |

## Decision

Add **M8 Player Collections**. It owns:

- `favorite`: owner reference, favorited account reference, creation time;
- `saved_search`: owner reference, name, date, time window, area reference, optional playing level/max distance, and audit timestamps.

M8 performs its own owner-based authorisation, exposes add/remove/list favorites and create/edit/list/reuse/delete saved searches, and resolves current public display fields via the published read views of M2, M3, and M6. It stores **no** copied profile, availability, email, phone, or coordinate data. The views already allowed for M4 are now also allowed for M8; their exposed columns and privacy restrictions do not change.

**M8 must not call M4; M4 must not read M8.** Reusing a named search is orchestrated by Platform: load criteria from M8, then call the existing M4 search function. FR-17 is handled by **M4 `compare()`** as a stateless operation with a server-enforced limit of three; the comparison selection is not stored.

On a favorites list, an unavailable or incomplete player can remain visible with missing details clearly marked, but a blocked pair is omitted in both directions. Adding a favorite sends no notification. Returned missing fields are truly absent or accompanied by a reason; do not invent zero distance or empty string values.

## Rationale

M8 is a separate owner for user-curated, owner-private data, so the critical read-only search and safety rules remain intact. Reusing the same published read views avoids copying changing information. The new features do not require a new service, transactional confirmation flow, or architectural style.

## Trade-offs and consequences

- A published view now has **two consumers** (M4 and M8), so changing its contract requires reviewing both.
- Resolving public information on each favorites request costs database work but avoids stale copies.
- Server-side compare limits and owner checks cannot rely on the browser UI alone.
- Three new requirements have been treated as an **unvalidated amendment** in the uploaded architecture; they should not be represented as approved by the client without actual validation.

## Open items before acceptance

- **G-05:** A saved search with an absolute past date may be unusable; the team must choose literal date, relative pattern, or another approved rule before implementing the schema.
- **G-06:** Behavior when the favorited account is deleted depends on unresolved account-retention rules (G-04).
- **G-07:** No maximum count is defined for favorites and saved searches; an agreed cap or pagination/performance plan is needed.

## Consistency and verification

- Confirm M4 remains table-free and M8 does not depend on M4.
- Confirm privacy and block rules apply to favorites, comparison, and saved-search execution.
- Verify the named-search schema against the team's resolved G-05 decision.
- Amend the validated PRD and record actual TA/client approval if FR-16–FR-18 are to be treated as validated requirements.
