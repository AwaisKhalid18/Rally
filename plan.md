# plan.md — Rally (living artefact)

**Version:** v01 · **Date:** 2026-11-20 (Fri) · **Deadline:** 2026-11-27 (Fri) · **Authors:** Awais, Fazeel, Ali
**Rule:** every meaningful change to this file is saved as `plan-vNN.md` (copy) *and* committed to git. Never overwrite history. A change-log row is added in §9 every time.

---

## 1. Product objective

Rally helps recreational badminton players find a suitable partner when their usual friends are unavailable: a player searches by date, time window and area, sees ranked players whose availability, approximate distance and playing level fit, sends an invitation (date, start, end, venue), and the recipient accepts or declines; acceptance creates a confirmed game that can never overlap another confirmed game for either player. Private contact data and exact location are never exposed.

**Promised scope (what must work in the demo):** FR-01 to FR-15, registration + email verification, blocking + reporting, confirmed-game cancellation (PRD §5, §12), and FR-16 to FR-18 (post-baseline amendment, architecture §16 — *not client-validated*; **P2, see §8 cut rule**).
**Explicitly not built:** court booking, payments, chat, ratings, attendance, rescheduling, recurring availability, privacy settings, post-acceptance contact sharing, geocoding, account deletion, admin screens, resend-verification, password reset (AGENTS §7).

**Context set (the "approved context"):** `docs/context/PRD.md`, `architecture.md`, `AGENTS.md` (v5 once signed), `docs/adr/ADR-001…008`.

## 2. Team, roles, ownership

| Member | Lead on slices | Module focus (for understanding, not exclusive) | Also owns |
| --- | --- | --- | --- |
| **Awais** | S1, S4, S5, S6, S12 | M1 Identity, M3 Availability, M4 Search, M6 Safety, Platform | architecture/AGENTS upkeep, plan.md versions, final integration |
| **Fazeel** | S3, S7, S8, S9, S11 | M2 Profile, M5 Invitation & Games | ADR upkeep (ADR-004 owner), concurrency tests, test-evidence log |
| **Ali** | S2, S10, S13, S14, S15, S16 | M7 Notification + worker, M8 Collections, frontend polish | repo/tooling, seed data, load test, Workflow Evidence Log, CCP + report |

**Review rule:** the *reviewer* in §4 makes the Accept / Revise / Reject call, never the lead alone. The lead may not review their own slice. Everyone must be able to explain every slice (any member can be questioned about the whole project) — so each member does the end-of-day walkthrough of one other member's slice (§7).

## 3. Assumptions and open issues (resolve in Stage 2 — Gate 1 for the affected slice)

| ID | Item | Proposed resolution | Needed by | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| A-00 | FR-16–FR-18 are not in the Validated PRD | Add a short "Amendment 1" section to PRD.md (text in `docs/context/`), flagged *not client-validated*. Keep as P2 | S13 | Awais | Open |
| G-10 | Availability vs confirmed games (does a game "consume" a slot?) | Slots never consumed; cancellation frees time via `cancelled_at`; search may list an already-booked player, accept rejects (AGENTS v5 §9) | S8 | Fazeel + Awais | Open |
| G-11 | Time zone | One display TZ, UTC storage, injectable `Clock` | S1 | Awais | Open |
| G-12 | Input bounds the PRD leaves open | end > start; start not in past; name 2–40; venue 2–100; own slots may not overlap; distance filter on unrounded km; results cap 50 | S3 | Fazeel | Open |
| G-13 | Report categories | Harassment / Fake profile / Inappropriate content / Other | S12 | Awais | Open |
| G-14 | Demo email | Console/file backend default; Brevo optional by config | S2 | Ali | Open |
| G-15 | ADR-007, ADR-008 and architecture §18 not yet reviewed against AGENTS | Review + sign-off by Awais and Fazeel; mark ADR-001…008 *Accepted* | before S1 merge | Awais, Fazeel | Open |
| G-16 | Stale architecture.md (M6→M5 edge, outbox writers, diagram without M8, G-08/G-09 "open") vs AGENTS v4 | Apply §18 / edits in `01-review-findings.md` | S1 | Awais | Open |
| G-17 | NFR verification is not possible as written in 7 days (30-day reliability, ≥10 usability participants) | Verify NFR-01 locally (10k seed, 100 users, gunicorn), NFR-03 by automated suite, NFR-02 by a small timed test (≥3 non-team players, stated as limited), NFR-04 reported as *not measurable in window* + logging evidence | S16 | Ali | Open |
| G-18 | Report review without admin screen | Accept limitation (review in DB) — optional: register `report` read-only in Django admin if time remains | — | Awais | Accepted limitation |
| G-08 | Email provider | Brevo behind adapter (AGENTS v4) — closed once ADR-007 signed | S2 | Ali | Closed in AGENTS |
| G-09 | Hosting | **Local run** via docker-compose (PostgreSQL) + `manage.py runserver`/gunicorn + worker command. No cloud | S16 | Ali | Proposed |

## 4. Slice backlog (priority order)

Legend — **Mode:** HITL = human approves the plan and reviews every step; AFK = delegated, human reviews the result. **Pri:** P1 must · P2 should (cut rule §8).

| ID | Vertical slice (user-visible capability) | Req. refs | Lead | Reviewer | Mode · reason | Depends on | Pri | Target | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | Register, sign in, sign out (+ minimal project skeleton) | FR-14, FR-01, §12.2, ASR-05 | Awais | Fazeel | HITL · sets auth + boundary rules for everything | — | P1 | Fri 20 – Sat 21 | Not started |
| S2 | Verify email via link; verification mail sent by worker/outbox | §12.2, ASR-06, ASR-11, ASR-12 | Ali | Awais | HITL · first outbox/worker, privacy-sensitive | S1 | P1 | Sat 21 | Not started |
| S3 | Create/edit my profile; view another player's public profile | FR-01, FR-06, FR-14, ASR-03 | Fazeel | Ali | AFK · routine CRUD, rules already fixed | S1 | P1 | Sat 21 | Not started |
| S4 | Manage my availability slots | FR-04, §12.1 | Awais | Fazeel | AFK · routine CRUD; views are reviewed | S1 | P1 | Sat 21 – Sun 22 | Not started |
| S5 | Search: date + time window + area → ranked results with availability and approx. distance | FR-02, FR-03, FR-04, FR-05, NFR-01, ASR-01/02 | Awais | Ali | HITL · SQL + read views + performance risk | S3, S4 | P1 | Sun 22 | Not started |
| S6 | Search refinement: level filter, max distance, ranking tie-breaks, no-results guidance | FR-06, FR-07, FR-13 | Awais | Fazeel | AFK · extends S5 under existing tests | S5 | P1 | Mon 23 | Not started |
| S7 | Send an invitation; see my sent/received invitations | FR-08, FR-10, §12.3 | Fazeel | Awais | HITL · eligibility + honest feedback | S2, S3, S4 (S6 optional) | P1 | Sun 22 – Mon 23 | Not started |
| S8 | Accept / decline an invitation → confirmed game (atomic, no double-booking) | FR-09, FR-15, ASR-07, ASR-08, ADR-004 | Fazeel | Awais | **HITL** · the critical transaction; concurrency | S7 | P1 | Mon 23 – Tue 24 | Not started |
| S9 | Cancel a pending invitation; invitations expire correctly | FR-11, ASR-09, ADR-005 | Fazeel | Ali | HITL · time semantics | S8 | P1 | Tue 24 | Not started |
| S10 | Notifications: in-app + email for accept / decline / cancel, retries, honest status | FR-12, ASR-11, ASR-12 | Ali | Fazeel | HITL · external failure + privacy | S8, S9, S2 | P1 | Tue 24 | Not started |
| S11 | My confirmed games; cancel a confirmed game | §12.4, FR-15 | Fazeel | Ali | AFK · builds on S8/S10 | S8, S10 | P1 | Wed 25 | Not started |
| S12 | Block / unblock and report a player (hidden in search, invites blocked, pending cancelled) | §12.5, ASR-10 | Awais | Ali | **HITL** · cascade through a port, cross-module | S5, S7, S10 | P1 | Tue 24 – Wed 25 | Not started |
| S13 | Favorites: add / list / remove | FR-16, ADR-006 | Ali | Awais | AFK · small, rules fixed | S5, S12 | **P2** | Wed 25 | Not started |
| S14 | Compare up to three players | FR-17 | Ali | Fazeel | AFK · stateless read | S5 | **P2** | Wed 25 | Not started |
| S15 | Saved searches: save / edit / reuse / delete | FR-18, ADR-006 | Ali | Awais | AFK · uses M4 via Platform | S6, S13 | **P2** | Wed 25 – Thu 26 | Not started |
| S16 | Final validation: seed 10k, load test, privacy suite, E2E run, README, report | Gate 5, NFR-01…04 | Ali (all) | Awais | HITL · evidence for the demo | all done | P1 | Thu 26 | Not started |

S1 is deliberately the first vertical slice: it builds only the parts of the skeleton (settings, Platform pipeline, `identity`, boundary checks) that registration/sign-in needs. Other modules are created by the slice that first needs them — no "scaffold everything first" step.

## 5. Slice details (acceptance criteria = Gate 1 input)

Format per slice: **Context to load** (only these go to the AI agent) · **Acceptance criteria** (AC) · **Key checks**. Detailed EP/BVA/negative cases are in `docs/evidence/test-plan.md`. Every slice also passes the standing checks in §6.

### S1 — Register, sign in, sign out
- **Context:** AGENTS §1–§5, §10, §11; PRD §12.2; architecture §5 (M1, P), §6.7, §12; ADR-003, ADR-007.
- **AC1** A visitor registers with email + password; an *unverified* account is created; password is stored hashed.
- **AC2** Invalid email, too-short password (<8), or an already-registered email is rejected with a clear message and the form keeps the valid inputs.
- **AC3** Valid credentials start a session; wrong credentials give one generic error; sign-out ends the session.
- **AC4** Every URL except register, sign in, verify-email (and static files) redirects to sign-in when there is no session — checked by a test that walks the URL conf.
- **AC5** POSTs require CSRF; authenticated pages send `Cache-Control: no-store`; no email appears in any log line.
- **AC6** `tools/check_module_graph.py` and `import-linter` pass in CI.

### S2 — Verify email; worker + outbox
- **Context:** AGENTS §1, §4 (rules 3, 5, 6), §5 (Sessions, Honest feedback), §11 (S-08); architecture §6.6, §7; ADR-005.
- **AC1** Registration appends an outbox event **in the same transaction**; the web request never contacts the email provider.
- **AC2** `manage.py run_worker` claims due outbox rows, reads the address from M1 at send time, sends through the adapter (console backend by default), records `queued → sent | failed`, retries a failure up to 3 times within 15 minutes, then logs and stops.
- **AC3** Verification link → page with a *Confirm* button → POST marks the account verified. Invalid, reused or malformed token → clear message, no state change.
- **AC4** With the email adapter forced to fail, registration still succeeds.
- **AC5** The address never appears in `outbox`, `notification` or logs (grep test).

### S3 — Profile
- **Context:** AGENTS §3 (M2), §4, §5 (Privacy), §11; PRD §12.1, §12.2 (fields); architecture §5 (M2), §8.2; ADR-002, ADR-003.
- **AC1** An account owner sets display name, playing level (Beginner / Intermediate / Advanced) and general area from the fixed list (`ops/seed/areas.csv`); phone is optional and private.
- **AC2** Only the owner can edit (direct request for another player's edit → rejected); a profile is *complete* only with name + level + area + verified email.
- **AC3** Another player's public profile page shows only display name, level, area (and slots after S4) — never email, phone or exact location; there is no field anywhere that accepts an exact location.
- **AC4** Invalid level / area not in list / name outside bounds → rejected with message.
- Creates `v_searchable_profile`.

### S4 — Availability
- **Context:** AGENTS §3 (M3), §5; PRD §12.1, §12.4; architecture §5 (M3); ADR-002.
- **AC1** The owner adds, edits and deletes slots (date, start, end); several slots allowed.
- **AC2** Slot with end ≤ start, or already ended, → rejected. Overlapping own slots → rejected (G-12).
- **AC3** `removeExpiredSlots()` removes slots whose end time has passed (worker command + query-time filter); a slot ending exactly "now" counts as passed.
- **AC4** Slots appear on the owner's public profile; only the owner can change them.
- Creates `v_active_availability` (future slots only).

### S5 — Search (core)
- **Context:** AGENTS §3 (M4), §4 (rules 1, 6, 7, 9, 13), §5 (Search), §11; PRD §12.1, FR-02…05; architecture §6.2, §8.3; ADR-002.
- **AC1** Date, time window and location are mandatory; a missing one shows a field error and the entered criteria are kept.
- **AC2** Results contain only other players who are verified, profile-complete, have ≥1 slot strictly overlapping the window; not the searcher.
- **AC3** Each card shows display name, level, area, the overlapping slot(s) and *approximate* distance (rounded km) from the chosen area centroid; distance is omitted **with a reason** when either location is missing.
- **AC4** Order: distance ascending, then earliest overlapping slot (level closeness is added in S6).
- **AC5** Cards offer an "Invite" entry point (wired in S7). Unauthenticated request → no data.
- **AC6** Responses contain no email / phone / exact location (privacy test on the rendered page and fragment).
- **AC7** (NFR-01 evidence) With the 10,000-profile seed, one search runs as one query set (no N+1) and local p95 < 2 s at 100 concurrent users (full run in S16; smoke run here).
- Creates M6's `block` table + `v_block_pairs` as an *empty stub* so M4 can depend on it from day one (UI comes in S12).

### S6 — Search refinement
- **Context:** AGENTS §5 (Search), §11; PRD §12.1, FR-06, FR-07, FR-13.
- **AC1** Optional level filter (omitted ⇒ all levels). Max distance 5/10/20/50 km, default 10; other values rejected; a player exactly at the limit is included, just over is excluded.
- **AC2** Filters combine with AND; ranking = distance → level closeness to the searcher's level → earliest overlap.
- **AC3** No match ⇒ no-results message suggesting a different date, time or location (and level / max distance if used); criteria are echoed unchanged; nothing is widened silently.

### S7 — Send invitation + invitations list
- **Context:** AGENTS §3 (M5), §4 (rules 4, 8), §5 (Invitations); PRD §12.3, §12.4, FR-08, FR-10; architecture §6.3, §6.4, §8.4; ADR-004 (send part).
- **AC1** Verified sender picks a recipient (from a result or profile), date, start, end, venue — all mandatory.
- **AC2** Rejected with a specific message when: unverified sender; recipient = self; either player blocks the other; end ≤ start; start in the past; recipient has no availability covering the time; a Pending invitation from the same sender to the same recipient already overlaps.
- **AC3** Created as Pending with `expires_at = min(created + 24 h, start)` (server UTC).
- **AC4** The success message appears only after commit; a forced failure shows an error, never success.
- **AC5** "My invitations" lists sent and received with status; a non-participant gets not-found; the other party is shown by display name only.
- **AC6** Writes an outbox record in the same transaction (consumed in S10).

### S8 — Accept / decline → confirmed game
- **Context:** AGENTS §3 (M5), §4 (rules 3–5, 8), §5 (Accept, First committed action wins); PRD §12.3, §12.4, FR-09, FR-15; architecture §6.4, §6.5, §8.4; ADR-004, ADR-007 (constraint).
- **AC1** Only the recipient may respond; declining needs no reason; a recorded response cannot be changed.
- **AC2** Accept runs as **one M5 transaction**: re-read `FOR UPDATE` → still Pending and not expired (UTC) → recipient still available → no overlapping confirmed game for either player → insert `confirmed_game` + two `game_participant` rows → status Accepted → append outbox → commit.
- **AC3** Back-to-back games (end = next start) are allowed; overlapping ones are rejected with *"you already have an overlapping game"*; any non-Pending invitation → *"no longer pending"*; never a raw database error.
- **AC4** Race 1: two simultaneous accepts of one invitation → exactly one succeeds. Race 2: two overlapping invitations to the same player accepted simultaneously → exactly one confirmed game. Zero overlapping confirmed games afterwards; no partial rows.
- **AC5** The invitation stays Accepted and the confirmed game is a separate record; the database exclusion constraint rejects a forced overlapping insert.

### S9 — Cancel invitation + expiry
- **Context:** AGENTS §5 (Expiry, First committed action wins); PRD §12.3, FR-11; architecture §6.4; ADR-005.
- **AC1** The sender cancels a Pending invitation → Cancelled; only the sender; a non-Pending one cannot be cancelled.
- **AC2** Accept after `expires_at` is rejected **even if the sweep never ran** (worker stopped; clock frozen in test). At `expires_at` exactly the invitation is expired; one second earlier it is acceptable.
- **AC3** `expires_at` is the earlier of creation+24 h and proposed start. `expirePending()` (worker) only refreshes stored status and sends nothing.
- **AC4** Cancel vs accept race → one winner, loser gets "no longer pending".

### S10 — Notifications
- **Context:** AGENTS §4 (rules 3, 5, 6), §5 (Honest feedback), §11; PRD §12.3 (notifications), FR-12; architecture §6.6; ADR-005.
- **AC1** Sender is notified (in-app + email) when the recipient accepts or declines; recipient is notified when the sender cancels a pending invitation.
- **AC2** The in-app notification always exists and lists in a notifications page (read/unread); the email goes through the worker only.
- **AC3** Email status is shown only as *queued / sent / failed*, never "delivered". Failed sends retry ≤3 times within 15 min, then are logged.
- **AC4** Provider down ⇒ accept/decline/cancel still succeed. No email address in outbox, notification or logs.

### S11 — Confirmed games
- **Context:** AGENTS §5 (Accept); PRD §12.4; architecture §8.4 (cancel game), §8.5.
- **AC1** A player sees their upcoming confirmed games (both participants see the same game).
- **AC2** Either participant can cancel before the start time after an explicit confirmation step, no reason needed; after the start time → rejected; non-participant → not-found.
- **AC3** Cancelling sets `cancelled_at` on both participants, so the time is free again for new games (G-10); the invitation status remains Accepted.
- **AC4** The other player gets an in-app notification + email (via S10 path).

### S12 — Block / unblock / report
- **Context:** AGENTS §3 (M6, port), §4 (rules 14, 15), §5; PRD §12.5, ASR-10; architecture §5 (M6), §6.3; ADR-007 (R-02).
- **AC1** A player blocks from a profile, result or invitation. The blocked pair is hidden from each other in search (both directions) and cannot send invitations.
- **AC2** Blocking cancels all Pending invitations between the two players **inside M6's transaction through the port**; confirmed games are untouched; outbox records are written.
- **AC3** Unblock from a blocked-players list restores visibility but not cancelled invitations.
- **AC4** Report from a profile or an invitation: category + optional text, stored; reporters cannot read reports.
- **AC5** Startup wiring test: the port is registered; `safety` does not import `invitations`. Accept-vs-block race leaves a consistent state.

### S13 — Favorites (P2)
- **Context:** AGENTS §3 (M8), §4 (rules 11, 13), §5 (Collections); architecture §16; ADR-006.
- **AC1** Add / list / remove favorites; owner-only; duplicates and self rejected; **cap 50** (the 51st is rejected with a message).
- **AC2** List shows name, level, area, future slots; no slots ⇒ "no availability" shown (not hidden); unavailable account ⇒ "no longer available" with remove; blocked pairs omitted both ways.
- **AC3** Only references are stored; the favorited player gets no notification and no outbox record.

### S14 — Compare (P2)
- **Context:** AGENTS §3 (M4), §5 (Compare); architecture §16.5.
- **AC1** Compare 1–3 selected players: level, area, available times, distance where possible; each missing value shows its reason (never blank/0).
- **AC2** A request with 4 players is rejected **by the server**; removing/replacing is a new request; nothing is stored.
- **AC3** A blocked or non-existent player is treated identically (not found).

### S15 — Saved searches (P2)
- **Context:** AGENTS §3 (M8), §5 (Collections), §4 (rules 11, 12); architecture §16.8; ADR-006.
- **AC1** Save a named search (time window, area, optional level / max distance, and `fixed_date` *or* `day_rule`); list, edit, delete; **cap 20**.
- **AC2** "Reuse" loads criteria from M8 and calls `M4.search()` from Platform (M8 never calls M4); a past `fixed_date` shows "needs a new date" and is not run.
- **AC3** Owner-only; no coordinates or copied profile data stored.

### S16 — Final validation and delivery
- **AC1** NFR-01: 10,000 seeded profiles, 100 concurrent users, local gunicorn, result (p95, error rate) recorded.
- **AC2** NFR-03: automated privacy suite (unauthenticated, other player, search, profile, invitation, notification, direct request) passes 100%.
- **AC3** NFR-02: small timed find-a-player test with ≥3 non-team players; stated honestly as limited. NFR-04: logging in place; reported as not measurable in the window.
- **AC4** Scripted end-to-end demo run on a fresh database and seed; Gate 5 checklist complete.
- **AC5** README run instructions verified on a teammate's machine; final report, CCP analysis, logs and plan history complete.

## 6. Standing checks for every slice (quality gates)

| Gate | Check before moving on | Evidence |
| --- | --- | --- |
| 1 Slice readiness | ACs above are clear; related assumptions (§3) resolved | Gate-1 line in the Workflow Evidence Log |
| 2 Functional | ACs + negative + relevant EP/BVA run; **real** output pasted | Test-evidence rows |
| 3 Architecture | Rules 1–15 + FE-1…FE-10; `check_module_graph.py` + `import-linter` green | CI output |
| 4 Regression | Full Tier-1 suite green before Accept; previous slices' flows still work | CI output + 1-line smoke note |
| 5 Final | S16 | S16 evidence |

## 7. Daily schedule (target; replan in §9 whenever it slips)

| Day | Awais | Fazeel | Ali |
| --- | --- | --- | --- |
| **Fri 20** (tonight) | Stage-2 review sign-off; plan-v01; start **S1** | Review ADR-007/008 + apply doc fixes; PRD Amendment text; create test-plan skeleton | Repo, docker-compose Postgres, CI (graph + import-linter), `areas.csv`, evidence folders, 10k seed script design |
| **Sat 21** | finish S1 → review S2 → **S4** | **S3**; review S1 | **S2** |
| **Sun 22** | **S5** (+ smoke perf with Ali's seed) | **S7** (starts when S2–S4 merge) | seed generator + load script; review S5 |
| **Mon 23** | **S6** | **S8** (HITL, with Awais) | support S8 tests (race harness); start S10 plumbing |
| **Tue 24** | start **S12**; review S8 | **S9** | **S10** · *evening: scope checkpoint (§8)* |
| **Wed 25** | finish S12 | **S11** | **S13, S14** (if go) |
| **Thu 26** | S15 review; final integration; freeze 18:00 | final regression + test evidence | **S15** (if go) → **S16** |
| **Fri 27** | Buffer, demo rehearsal, **submit early** — never rely on the last hour (late penalty starts at minute 1) | | |

Walkthrough rule: at the end of each day each member explains (5 min) one slice they did *not* lead; log it in the Contribution Log.

## 8. Scope-cut rule (Tuesday 24 Nov, evening)

If S1–S10 are not all *Accepted*, **S13–S15 are removed from promised scope**: update PRD Amendment, AGENTS §5/§7, architecture §16 status line and this plan (new version, reason recorded). Do not leave a half-built feature in the product — "whatever you promise must work in the demo." If S11–S12 are at risk on Wed, cut order is S15 → S14 → S13 → (never S11/S12: they are PRD §12 MVP).

## 9. Change log (plan versions)

| Version | Date | What changed | Why | Author |
| --- | --- | --- | --- | --- |
| v01 | 2026-11-20 | Initial plan: 16 slices, owners, ACs, schedule, assumptions | Stage 2 output after AI review of PRD/architecture/AGENTS/ADR-001…006 | Awais (with AI) |

*(Add a row — and a `plan-vNN.md` copy — after each slice decision, scope change, re-sequencing, or new assumption.)*
