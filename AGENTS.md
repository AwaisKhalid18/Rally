# AGENTS.md — Rally

Instructions for AI coding agents working in this repository. Read this file first, every session.
Authors: Awais (architecture), Fazeel (ADRs), Ali Tahir (agent context). Status: **draft v5 PROPOSED, 2026-11-20** (v4 = 2026-11-16). Decisions R-01 to R-15 come from **ADR-007**, adopted for implementation by Ali Tahir and **pending sign-off** by Awais and Fazeel. Decisions S-01 to S-08 (frontend and worker, §11) come from **ADR-008**, adopted for implementation by Ali Tahir, with the same sign-off as ADR-007; v4 only *adds* §11 and the lines that point to it — nothing decided in v3 is changed.

**v5 changes (proposed by Awais, all marked `[v5]` below; nothing decided in v4 is reversed):**
1. §3.1 Python package naming — three module folder names collide with the Python standard library and would break the project.
2. §5 verification link must not change state on GET (resolves a conflict between §5 Sessions and FE-9).
3. §5 one display time zone, stored UTC (the PRD says "server UTC" but players type local times).
4. §9 new open items G-10…G-14 (proposed resolutions, **not decided** — treat as open until the team signs them).
5. §10 "one module per change" replaced by "one vertical slice per change" (D4 requires vertical slices); test tiers added.
6. §12 new: slice workflow and evidence duties for the agent.

---

## 1. What Rally is

A web app that helps recreational badminton players find a playing partner when their usual friends are unavailable. A player searches by date, time window, location and (optionally) playing level; Rally returns ranked players; the player sends an invitation (date, start, end, venue); the recipient accepts or declines; **acceptance creates a confirmed game**.

Rally is a *proposed* solution, not a proven one. Keep it small and cheap to change.

**Architecture:** modular monolith. One deployable web app + one background worker (same codebase), one PostgreSQL database, one external service (an email provider). Nothing else.

**Stack (ADR-007 R-01):** Python 3 + Django, PostgreSQL, `import-linter` for boundary tests. Do not add another framework, database or service. If the team changes the language, only this paragraph and the constraint syntax under "Accept" in §5 change.

**Full stack (ADR-007 R-01 + ADR-008 S-01…S-08, §11):**

| Layer | Choice | Status |
|---|---|---|
| Backend | Python 3 + Django (modular monolith) | ADR-007 R-01 |
| Database | PostgreSQL (relational) | ADR-007 R-01 |
| Frontend | Django templates, server-rendered, plus HTMX (vendored) | ADR-008 S-01, S-02 |
| Styling | One hand-written CSS file, system fonts | ADR-008 S-03 |
| Background worker | Django management command polling the outbox | ADR-008 S-08 |
| Email | **Brevo** (SMTP relay, free plan) behind M7's adapter | chosen |
| Boundary tests | `import-linter` + `tools/check_module_graph.py` | ADR-007 |
| Hosting / WSGI server | not decided | open (§9) |

The frontend is part of the same deployable web app. It adds no service, no database and no second runtime.

**Email provider: Brevo.** It is the one external service. Only the worker calls it, through the adapter interface M7 owns, using Django's built-in SMTP email backend (no new library). Host `smtp-relay.brevo.com`, port 587, TLS. The SMTP login and key are injected as secrets, never committed. The free plan allows 300 emails a day (about 9,000 a month), which is enough for the pilot. Staging and load tests use a fake adapter and send no real email. Because the provider sits behind the adapter, replacing it changes only that adapter. The email address is read from M1 at send time and never stored or logged (rule 6).

---

## 2. Read before you write

Authority order (higher wins; if two disagree, stop and report — do not pick):

1. `docs/context/PRD.md` — Final Validated PRD. §12 holds the resolved decisions.
2. `docs/context/architecture.md` — **§1–15 baseline, §16 Amendment 1 (adds M8, `compare()`), §18 Amendment 3 (ADR-007 resolutions).** Where a later section changes an earlier one, the later one wins.
3. `docs/adr/` — ADR-001…006 (status *Proposed*, the team's recorded direction), **ADR-007**, which amends them, and **ADR-008** (frontend and worker; it amends none of ADR-001…007).
4. `docs/context/architecture-decisions.md`, `ASR-analysis.md`, `architecture-alternatives.md` — *why*.
5. This file — the operational summary.

FR-16, FR-17, FR-18 arrived after the PRD was validated: real requirements, **not client-validated**.
Every module README lists the FR/ASR IDs it serves (CON-06).

---

## 3. Modules

| Module | Folder | Owns tables | Publishes | Never |
|---|---|---|---|---|
| M1 Identity | `identity` | `account`, `session` | authenticate, isVerified, getDeliveryAddress, `v_verified_account`; the three public endpoints (§5) | hold profile data; know search/invitations |
| M2 Profile | `profile` | `profile`, `area` | getPublicProfile, isComplete, `v_searchable_profile` | store contact data, credentials, availability, **any exact location** |
| M3 Availability | `availability` | `availability_slot` | hasAvailability, listSlots, removeExpiredSlots, `v_active_availability` | decide whether a game may be confirmed |
| M4 Search & Matching | `search` | **none (read-only)** | `search()`, `compare()` | write data; send invitations; be called by another module |
| M5 Invitation & Games | `invitations` | `invitation`, `confirmed_game`, `game_participant` | send, accept, decline, cancelInvitation, cancelGame, listForPlayer, **expirePending**, **cancelPendingBetween** (implements M6's port) | own availability or block data; import M7; let another module change invitation status |
| M6 Safety | `safety` | `block`, `report` | block, unblock, isBlockedBetween, report, `v_block_pairs`, **port `PendingInvitationCanceller`** | apply blocks to search/invites itself; import M5 |
| M7 Notification | `notification` | `outbox`, `notification` | nothing; implements Platform's `OutboxAppender`; driven by the outbox | make business decisions; persist or log a contact address |
| M8 Player Collections | `collections` | `favorite`, `saved_search` | add/removeFavorite, listFavorites, save/update/deleteSearch, listSearches, getSearch | execute a search; call M4 or be read by M4; copy profile/availability/contact data; store coordinates |
| P Platform | `platform` | none | pipeline, auth enforcement, response shapers, UTC clock, unit-of-work mechanism, **`OutboxAppender` port**, startup wiring, read-only composition, worker host, logging | contain any business rule |

### 3.1 Package naming `[v5]`

The folder names above are **logical module names**. Three of them equal Python standard-library modules (`profile`, `collections`, `platform`); a top-level package with such a name shadows the library and breaks Django and most tools. Rules:

- Everything lives under one top-level package `rally/`: `rally/modules/<folder>/` and `rally/core/` (the Platform layer).
- Physical folder / Django app label for the clashing modules: `profile` → **`profiles`**, `collections` → **`player_collections`**, Platform → **`rally/core`**. All other folders keep their names. `import-linter` and `tools/check_module_graph.py` use the physical names.
- Never create a top-level package named `profile`, `collections`, `platform`, `search`-like generic names outside `rally/`.
- Cross-module references to another module's rows are plain `account_id` fields (integer/UUID), **not** Django `ForeignKey`/relations to another app's model. Reason: a relation needs an import of the other module's model, which breaks rule 2.
- Account model: custom `AUTH_USER_MODEL` owned by `identity`, set before the first migration. Django's built-in session table is treated as M1's `session` (infrastructure, not hand-written).

### Permitted dependencies (anything not listed is forbidden)

- `search` → `profile`, `availability`, `safety` — **published read views only**
- `collections` → `profile`, `availability`, `safety` — **published read views only**
- `invitations` → `availability`, `safety`, `profile` (it also implements `safety`'s port)
- `profile` → `identity` (reads `v_verified_account` only)
- `notification` → `identity` (delivery address at send time, never stored)
- everything → `platform`
- `identity` → nothing · **`safety` → nothing** · nothing → `notification` · nothing → `search` · nothing → `collections`

Verify any change with `python3 tools/check_module_graph.py` (must pass).

### How the block cascade works (ADR-007 R-02)

`safety` declares the port `PendingInvitationCanceller`. `invitations` implements it. Platform's startup wiring registers the implementation. `M6.block()` opens **its own transaction**, calls the port inside it, and appends outbox records. The source dependency runs one way (`invitations` → `safety`); the call crosses back at run time only through the port. Never import `invitations` from `safety`.

---

## 4. Binding rules — never break these

1. No module reads or writes another module's tables. The published read views (§8.3) are the only exception. Consumers: `search` and `collections` (all views in ADR-002/006); `profile` reads `v_verified_account`.
2. No module imports another module's internal packages — only its facade (and ports declared in a facade).
3. **No business module imports M7.** To notify, call Platform's `OutboxAppender.append(eventType, entityRefs)` inside your own transaction. M7 is the only writer of `outbox`.
4. A module interface invoked inside a transaction must not open or commit its own. The module that owns an invariant starts the transaction that protects it.
5. No transaction encloses an external call (email, HTTP, anything outside the database).
6. Email and phone appear in no view, payload, notification, outbox record or log outside M1.
7. No exact-location field in any schema. Store an area reference; derive distance per request from centroids.
8. State transitions use server time (UTC). Never a client-supplied timestamp.
9. Search is read-only. No module calls it; only Platform does.
10. No new framework, database, external service or cross-module dependency without an approved ADR.
11. M8 stores references, never copies. No profile field, availability value, contact detail or coordinate pair goes into `favorite` or `saved_search`.
12. M8 does not call M4 and M4 does not read M8. Reusing a saved search is composed in Platform: fetch criteria from M8, then call `M4.search()`.
13. A field that cannot be resolved is returned as **absent with a reason** — never `""`, `0` or a placeholder distance.
14. Platform may wire, mechanise transactions and orchestrate read-only facade calls. It never starts a transaction for a business module and never branches on business data.
15. A call that would invert a dependency goes through a port declared by the *called-from* module (or Platform) and registered at startup. Never add a reverse import.

Rules 1–13 keep the numbering of architecture §9.2 and §16.10; 14 and 15 are new (ADR-007). Part 3 of the process evidence numbers its list differently; this file wins.

---

## 5. Behaviour agents get wrong

**Invitations (M5 only).** Pending → Accepted | Declined | Expired | Cancelled; the last four are terminal. *Accepted invitation* ≠ *confirmed game*: acceptance inserts a separate `confirmed_game` and the invitation stays Accepted. Cancelling an invitation ≠ cancelling a confirmed game.

**Accept = one transaction, owned by M5.** Re-read invitation `FOR UPDATE` → still Pending and not expired by server UTC → recipient still available (M3 joins) → no overlapping confirmed game for either player → insert `confirmed_game` and **two `game_participant` rows** → set Accepted → append outbox → commit. Double-booking is enforced twice: an application check (readable message) and a PostgreSQL exclusion constraint on `game_participant` (`account` with `=`, time range `[start,end)` with `&&`, where `cancelled_at IS NULL`). Back-to-back games do not conflict. `cancelGame()` sets `cancelled_at` on both rows. A rejected accept returns the domain reason, never a raw constraint error.

**Expiry.** `expires_at = min(created + 24h, proposed start)`, evaluated **at commit time**. `M5.expirePending()` (called by the worker, with `M3.removeExpiredSlots()`, through facades) only refreshes stored status and sends no notification.

**First committed action wins.** Accept, decline, cancel, expire and block-cascade race on one invitation; losers get "no longer pending".

**Only confirmed games block time.** Pending invitations reserve nothing. Duplicate = same sender, same recipient, overlapping time, still Pending.

**Privacy.** Never serialise a domain entity; every response is built by a Platform response shaper from an explicit public view model. Public: display name, level, general area name, availability slots, approximate distance (nearest km, labelled approximate, omitted when unavailable). Private: email, phone — M1 only. Nothing becomes visible after acceptance.

**Sessions.** Every request needs a session **except exactly three**: register, sign in, verify email (token link). They call M1 only and return no player data. `[v5]` The emailed verification link (a GET) only *shows* a confirmation page; the state change happens on a POST with CSRF from that page (FE-9). Resend-verification stays out of scope. Add no other anonymous route. Resend-verification and password reset are not in the PRD.

**Time zone.** `[v5]` One configured display time zone for the pilot (Django `TIME_ZONE`, set once in settings); every timestamp is stored as UTC (`timestamptz`). Players type local date/time; Platform converts to UTC at the edge. Expiry, overlap and "in the past" are always evaluated in UTC with an injectable `Clock` so tests can freeze time.

**Honest feedback.** Success only after commit. Email status is `queued`, `sent` (provider accepted) or `failed`; the product says "email sent", never "delivered". Search criteria are echoed back unchanged; no-results shows guidance and never widens silently.

**Search.** Exclude: no overlapping slot, outside max distance, level mismatch (if chosen), blocked either way, incomplete or inactive profile. Rank: distance → level closeness → earliest overlapping slot. Date, time and location mandatory; level and max distance (5/10/20/50 km, default 10) optional. Areas come from a fixed list (`ops/seed/areas.csv`); no geocoding.

**Compare.** `compare()` applies the block rule both ways and treats a blocked player exactly like a non-existent account. Verified accounts with complete profiles are comparable even with no future slots (times shown absent with a reason). Server-side cap of three.

**Collections (M8).** At most 50 favorites and 20 saved searches per player (config values, enforced server-side). A saved search stores `fixed_date` **or** `day_rule` (`today`, `tomorrow`, weekday = next occurrence); a past `fixed_date` is returned as "needs a new date" and is not run. Blocked pairs are hidden from favorites; incomplete/inactive profiles are **not** (shown with no times). A favorite whose account is unavailable shows "no longer available" and can be removed. Favoriting sends no notification and writes no outbox record. There is no account deletion in the MVP.

**Reports.** M6 stores them. Review happens directly in the database; there is no admin screen (accepted limitation).

---

## 6. Vocabulary — use PRD terms

Player · Player profile · Availability (individual date/time slots, no recurrence) · Search criteria · Search filters · Search results · Distance · Playing level (Beginner/Intermediate/Advanced, self-reported) · Invitation · Pending/Accepted/Declined/Expired/Cancelled invitation · Confirmed game · No-results message · Private information. Do not invent synonyms ("match", "booking", "request", "friend").

---

## 7. Out of scope — do not add

Court booking, payments, in-app chat, ratings/reviews, attendance tracking, rescheduling, recurring availability, player-controlled privacy settings, post-acceptance contact sharing, geocoding or any second external service, account deletion, admin screens, resend-verification, password reset.

---

## 8. Stop and ask

Stop, write down the question, and wait for a human when:

- the PRD and architecture disagree, or two architecture sections disagree;
- you need a library, framework or tool outside §1;
- a change needs a dependency edge, a new view, a new table owner, a new port, or touches a published view;
- you would store, log or return anything private or location-like;
- a route would be reachable without a session;
- you are tempted to "just add a helper" in `platform` or a shared `utils` — shared code with business meaning belongs to a module;
- the frontend would need a JS framework, a Node/bundler build step, a CDN or third-party script or font, or any client-side store of player data (§11).

Never resolve ambiguity by inventing structure.

---

## 9. Open items

Decisions R-01…R-15 in ADR-007 close every earlier open item (G-01…G-07, AV-01…AV-11, stack). Remaining:

- **Sign-off.** Awais and Fazeel must approve ADR-007 before ADR-002…006 are marked Accepted. If they change a decision, this file changes with it.
- **Client or TA confirmation:** R-11 (pilot city's area list — data to supply in `ops/seed/areas.csv`), R-13 (no account deletion), R-14 (FR-18 date handling).
- **Config values:** the caps 50 and 20 (R-15) are adjustable without an architecture change.
- **Missing content:** `ops/seed/areas.csv` rows.
- **ADR-008:** signed off together with ADR-007. Static assets (CSS, vendored HTMX) are served without a session, carry no player data and are not counted as routes under the three-public-routes rule. Hosting and the WSGI server are not decided.

`[v5]` **New open items (proposed resolution — confirm before the affected slice):**

- **G-10 — Availability vs confirmed games.** PRD 12.4 says a game's slot is "restored" on cancellation, but nothing says accepting *consumes* a slot, and search (12.1) does not exclude players who already have a confirmed game. *Proposed:* slots are **never consumed or split**; a confirmed game blocks time only through the overlap rule at accept time; cancelling sets `cancelled_at`, which frees the time automatically, so "restoration" needs no slot write. Search may still list a player who is already booked — acceptance will then be rejected (accepted limitation; PRD 12.4 'only confirmed games block time').
- **G-11 — Time zone.** Proposed in §5.
- **G-12 — Input bounds** the PRD leaves open: end after start; start not in the past; display name 2–40 chars; venue 2–100 chars; own availability slots must not overlap each other; max-distance filter uses the unrounded distance (display is rounded); search results capped at 50.
- **G-13 — Report categories:** Harassment, Fake profile, Inappropriate content, Other (PRD says 'choose a category' without a list).
- **G-14 — Demo email.** The default email backend is the console/file backend; Brevo is enabled only by configuration. The demo must not depend on a live provider.

All modules may now be scaffolded and built, following ADR-007. The frontend follows ADR-008 (§11).

---

## 10. Working agreement

- `[v5]` Propose structure before writing code; **one vertical slice per change** (see §12). A slice may touch several modules, but only through their facades, and each module's part is a separate commit. Small commits.
- Put code under `src/modules/<folder>/` (`api/` facade and ports · `internal/` · `views/` · `migrations/` · `tests/`). Nothing outside a module's `api/` may be imported. Platform lives in `src/platform/` (`ports/`, `wiring/`, …). Frontend files live in Platform only: `src/platform/web/templates/` and `src/platform/web/static/` (§11.4). Note: a module's `views/` folder holds published **database** read views, not Django views or templates.
- Each module README lists its FR/ASR IDs and its published interface.
- Tests you must keep green: module-graph check and `import-linter` contracts · privacy cases (§12.6: unauthenticated, other player, search, profile, invitation, notification, direct server request; the three public endpoints are the only anonymous routes; no email in any log, outbox or notification) · concurrency (accept/accept on one invitation, accept/cancel, accept/expire, accept racing a block cascade, overlapping accepts of two invitations sharing a player, expiry at the exact earlier deadline, rejection from terminal states, no partial invitation/game/outbox records) · resilience (email provider down: invitation operations still succeed; worker stopped: an expired invitation still cannot be accepted; three retries within fifteen minutes) · wiring (both ports registered at startup).
- `[v5]` Test tiers (D4 says testing is lightweight): **Tier 1 — must exist and pass in CI:** module-graph + import-linter, privacy cases, accept/accept and overlapping-accept races, expiry-at-commit, wiring. **Tier 2 — one test or one documented manual run each:** email-provider-down, worker-stopped, three-retry policy, CSRF, no-store header. Do not generate large suites; EP/BVA only where a real boundary exists.
- Definition of done: rules 1–15 hold · frontend rules FE-1…FE-10 hold (§11) · no private field in any new view/payload/log · no client timestamp in a transition · graph check passes · FR/ASR IDs recorded.
- Secrets are injected, never committed. Staging reproducible with 10,000 seeded profiles (CON-03).

---

## 11. Frontend and worker (ADR-008 S-01…S-08)

This section only adds. It changes no module, table, view, port, dependency edge or rule 1–15.

### 11.1 Decisions

| ID | Decision |
|---|---|
| S-01 | **Server-rendered Django templates.** No single-page app, no separate frontend project, no second deployable. |
| S-02 | **HTMX** for partial page updates (search results, accept/decline, favorites). One vendored, version-pinned file committed in `static/`. No other JS framework. A little plain JS is allowed for presentation only. |
| S-03 | **One hand-written stylesheet** with design tokens (colours, spacing, type scale), mobile-first, system font stack. No CSS framework, no web fonts, no build step. |
| S-04 | Templates are fed **only public view models** from Platform's response shapers. |
| S-05 | **Session cookie + Django CSRF** (HttpOnly, Secure, SameSite=Lax). No tokens or player data in JS-reachable storage. |
| S-06 | **No optimistic UI.** The page shows success only after the server confirms the commit. |
| S-07 | **Same-origin only.** Every script, style and font is served by the app. No CDN, analytics or third-party embed (keeps CON-01: exactly one external service). |
| S-08 | **Worker = a Django management command** that polls the outbox and runs the expiry sweep. No Celery, Redis or broker. It remains the only caller of the email provider. |

### 11.2 Frontend rules (FE-1…FE-10 — numbered separately so rules 1–15 stay stable)

1. **FE-1.** A template renders a public view model. Never a model instance, queryset or domain entity (rule: §5 Privacy).
2. **FE-2.** No email, phone, exact location or internal-only field in HTML, `data-` attributes, hidden inputs, URLs, inline JS or logs (rules 6, 7).
3. **FE-3.** Every page needs a session except the pages of the three public flows (register, sign in, verify email). No other anonymous page. Static assets carry no player data and are not routes under this rule.
4. **FE-4.** No business logic in templates or JS: no eligibility, overlap, expiry, ranking or block decisions. Display what the view model says.
5. **FE-5.** Success messages only after commit. Email status wording is `queued`, `sent` or `failed`; never "delivered" (§5 Honest feedback).
6. **FE-6.** An absent field shows its reason text. Never blank, `0` or a placeholder distance (rule 13). Distance is labelled approximate.
7. **FE-7.** Echo search criteria back unchanged. No-results shows guidance and never widens silently.
8. **FE-8.** Dates and times typed by the player are search criteria or an invitation proposal only. The server stamps every state transition in UTC (rule 8).
9. **FE-9.** State-changing requests are POST with CSRF, including HTMX requests. Never change state on GET. Authenticated responses send `Cache-Control: no-store`.
10. **FE-10.** Same-origin assets only; HTMX is vendored and pinned (S-07).

Usability (ASR-13): a search result card shows availability, approximate distance and playing level together, and the invite action is reachable from it, with no per-result follow-up calls.

### 11.3 Screens

Register · sign in · verify-email result (the three public pages) · profile · availability · search (form, results, no-results guidance) · compare (max three) · send invitation · my invitations · confirmed games · favorites and saved searches · block and report. Each screen's FR/ASR IDs go in its module README (CON-06). Use PRD vocabulary (§6) in all UI text.

### 11.4 Where the files go

`src/platform/web/templates/` and `src/platform/web/static/` (CSS, vendored HTMX). Templates contain presentation only, so they do not breach "Platform contains no business rule". A template never calls a module facade; Platform views call facades, build view models through the shapers, and pass those to templates.

### 11.5 Tests to add (same rules as §10)

Privacy: no contact data or exact location in any rendered page or fragment, for every screen. Anonymous access: only the three public pages and static assets respond without a session. CSRF: state-changing requests without a token are rejected. No-store header on authenticated pages. Rendering: an absent field shows its reason.

---

## 12. Slice workflow and evidence duties `[v5]`

The course grades the *process* as much as the product. Follow this for every task you are given.

1. **One slice at a time.** The human names the slice ID from `plan.md`. Do not start another, and do not build ahead.
2. **Load only what the slice's "Context to load" line lists** (plan.md). Say which files you used.
3. **Restate the slice's acceptance criteria** and propose the checks (functional, negative, EP/BVA only where a real boundary exists) **before** coding. Wait for a human OK on HITL slices.
4. **Implement vertically**: UI → Platform view → module facade → data → check. No technical-layer-only work.
5. **Run the checks and report the real output.** Never write "tests pass" without having run them. Paste failures too.
6. **Do not mark a slice done.** A human decides Accept / Revise / Reject.
7. **If your change needs a rule, view, table, port or dependency edge that is not in §3–§4, stop (§8).** Propose the artefact change (PRD / architecture / ADR / this file) first.
8. **At the end of every slice, output:** (a) files changed, (b) rules 1–15 and FE-1…FE-10 you checked, (c) checks run + results, (d) anything you were unsure about, (e) the suggested edit to `plan.md` (status line + any new assumption).
9. Do not edit `plan.md`, `docs/evidence/*` or ADRs yourself; propose the text and the human commits it (keeps the history honest).
