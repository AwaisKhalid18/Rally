# ADR-001 — Architectural Style for Rally

- **Status:** Proposed — the process evidence records team agreement, pending final review
- **Decision owner:** Fazeel (ADR lead), recording the team's architecture decision
- **Scope:** Rally MVP, including the later FR-16–FR-18 amendment without changing this decision
- **Drivers:** QA-01, QA-02, QA-03, DR-F2, CON-05; ASR-02, ASR-04, ASR-08
- **Source:** `Final_Validated_PRD.md` §§5, 7, 12.3, 12.4, 12.6; `architecture.md` §§1, 2, 4, 5, 9, 16.9; *Architecture Process Evidence*, Part 2 and Part 3 D-01

## Context

Rally lets badminton players maintain profiles and availability, search for suitable partners, invite another player, and confirm games. The architecture must keep personal contact information private, return search results quickly, and prevent two overlapping confirmed games for a player. The agreed test target is search within two seconds for at least 95% of requests with 100 concurrent users against 10,000 profiles. The project is being prepared by a three-person student team for later AI-assisted implementation.

The difficult architectural requirement is acceptance of invitations: validating availability, changing invitation status, and creating the confirmed game must act as **one reliable operation**. Search also needs one efficient read path across several kinds of data. These needs favour a local transaction and clearly owned modules, not a large distributed system.

## Alternatives considered

| Alternative | Advantage | Why not chosen |
| --- | --- | --- |
| Layered monolith (controllers, services, repositories) | Simple deployment and familiar organisation | Layers do not provide clear ownership of the invitation state machine, privacy boundary, or blocking rule. AI-generated code could duplicate these rules across services. |
| Microservices (separate services and databases) | Potential for independent deployment and scaling | A game confirmation would require cross-service coordination or a saga; search would require cross-service joining or replicated data. The operational overhead is disproportionate to the MVP and three-person team. |
| **Modular monolith** (business-capability modules within one application) | Local ACID transactions, efficient queries, explicit ownership and interfaces | Modules are not protected by network boundaries; discipline and review are required to keep them isolated. |

## Decision

Use a **modular monolith** for the MVP: a web application organised around business capabilities, one relational database, and a background worker built from the same codebase for notification dispatch and maintenance jobs.

Modules are M1 Identity, M2 Profile, M3 Availability, M4 Search & Matching, M5 Invitation & Games, M6 Safety, M7 Notification, and the shared Platform layer. The later FR-16–FR-18 amendment adds M8 Player Collections without changing the architectural style (see ADR-006).

Business modules communicate through published in-process interfaces. Data is module-owned, with narrow published read views as the documented exception (ADR-002). M5 owns the invitation/game transaction (ADR-004). Notification delivery is separated from business requests (ADR-005).

## Rationale

The modular monolith meets the main quality drivers **without sacrificing comprehensibility**. Local transactions protect game confirmation (ASR-08); a single read query can serve matching (ASR-01/02); and capability ownership keeps privacy and blocking rules from being scattered across unrelated files. The background worker provides asynchronous email delivery without introducing independently networked services.

## Trade-offs and consequences

- **Accepted cost:** The application generally scales and deploys as a unit; search cannot be independently scaled without future extraction.
- **Accepted risk:** A fault in one part of the application may affect the whole process.
- **Architectural obligation:** Module internals must not be imported across boundaries; an AI agent must follow `architecture.md`, `AGENTS.md`, and these ADRs.
- **Future option:** Extract Search & Matching only if measurements justify it; this requires a new approved architectural decision.
- **Review condition:** An alternative style should be reconsidered if the real workload or integration requirements materially change, not merely because microservices are fashionable.

## Consistency and verification

- Confirm `architecture.md` §§4–6 and `AGENTS.md` use the same module names and boundaries.
- Confirm an AI-proposed project structure retains a single transactional core and does not invent microservices, internal HTTP calls, or additional databases.
- Confirm FR-16–FR-18 remain an amendment rather than being silently treated as part of the already validated PRD.
