> **Formatting-repaired copy.** Wording is identical to `Final_Validated_PRD_Deliverable2.md`; only headings (11, 12.x, appendices), bold `Resolved:` labels and the flattened Appendix tables were restored. FR-16 to FR-18 are NOT in this PRD (see architecture.md §16 and plan.md assumption A-00).

# Rally — Validated Product Requirements Document (PRD)

## 1. Product Overview

Rally is a proposed digital platform intended to help recreational badminton players find suitable playing partners when their usual friends are unavailable.

The product concept focuses on discovering players whose availability, location, and playing level may make them suitable partners. The proposed core experience includes player profiles, search criteria and filters, search results, availability and distance information, and invitations to arrange a badminton game.

Rally is a proposed solution to a documented coordination problem. The available project information does not establish that a dedicated platform is superior to existing tools such as WhatsApp, nor does it establish the frequency or severity of the problem across recreational badminton players.

This PRD distinguishes four types of information:

- **Client-supported problem:** A need or difficulty documented in the available account of the client interview.
- **Recorded team decision:** A product behavior documented as a decision in the project materials.
- **Proposed requirement:** A candidate requirement or behavior that still needs team agreement or clarification.
- **Pending decision:** An issue for which the available evidence does not establish a final answer.

The Human Validation Log guides how the draft is revised. Its dispositions do not, by themselves, establish formal team or client approval of every requirement.

All questions that were previously listed as open or pending have been answered in Section 12, which now records the resolved decisions. The requirements below reference those decisions.

## 2. Problem Statement

The client, Maaiz Ameer, experiences difficulty arranging badminton games when friends are unavailable. Contacting friends individually takes time, while WhatsApp groups do not guarantee that someone will be available.

The underlying problem is therefore one of coordinating with suitable badminton partners, not simply finding people who play badminton. Potential partners need to be available at compatible times, be located within a reasonable distance, and have a suitable playing level.

The available project account supports the core coordination problem and the relevance of availability, location, and playing level. However, the original interview record was not available for direct verification during this revision. No additional direct quotations or unverified interview details are introduced here.

The following remain unverified in the source record; Section 12.7 records how each is handled:

- How frequently the client encounters the problem and how significantly it affects badminton participation.
- The relative importance of availability, location, and playing level.
- Whether finding players outside the client's existing social circle is a separate need.
- Whether Rally reduces coordination effort or offers a meaningful advantage over WhatsApp and other existing approaches.

Rally should therefore be evaluated as a proposed response to the documented problem, not as a proven superior solution.

## 3. Target Users and User Needs

### 3.1 Target users

The intended primary users are recreational badminton players who want to arrange games with suitable partners, particularly when their usual friends are unavailable.

The PRD does not establish additional user groups, such as professional players, clubs, court operators, or tournament organizers, as target users.

### 3.2 User needs

| ID    | User need                                                           | Basis and status                                                                                                  |
| ----- | ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| UN-01 | Find suitable recreational badminton partners.                      | Supported by the documented problem analysis.                                                                     |
| UN-02 | Identify players available at compatible times.                     | Availability is identified as a core matching factor; availability model resolved in 12.1.                        |
| UN-03 | Assess whether potential partners are within a reasonable distance. | Location is identified as a core matching factor; distance model resolved in 12.1.                                |
| UN-04 | Compare potential partners' playing levels.                         | Playing level is identified as a matching factor; scale resolved in 12.1.                                         |
| UN-05 | Review player information before choosing a potential partner.      | Profiles are part of the proposed solution; profile fields resolved in 12.2.                                      |
| UN-06 | Express interest in arranging a game with a potential partner.      | Invitations are part of the proposed solution; invitation details resolved in 12.3.                               |

These needs inform the requirements but do not imply that every proposed implementation detail has been approved.

## 4. Product Goals

Rally aims to:

1. **Support player discovery:** Help recreational players find potentially suitable badminton partners.
2. **Support availability comparison:** Make relevant availability information visible when evaluating potential partners.
3. **Support location assessment:** Display distance information without exposing exact location unnecessarily or presenting misleading values.
4. **Support playing-level comparison:** Display playing level consistently in player profiles and search results.
5. **Provide useful player information:** Present agreed profile information to help players evaluate potential partners.
6. **Enable invitations:** Allow players to express interest in arranging a badminton game.
7. **Provide understandable outcomes:** Communicate invitation status and give honest success or error feedback.
8. **Protect private information:** Keep exact location and personal contact information private by default, in line with the recorded team decision.

The project should also investigate whether the proposed experience addresses the client's coordination problem effectively. The success metrics used to do so are defined in Section 12.7.

## 5. Non-Goals and Scope Boundaries

### 5.1 Proposed initial scope

The proposed initial scope centers on:

- Player profiles.
- Search criteria and search filters.
- Search results.
- Availability and playing-level information.
- Distance display, using the reference point and calculation method defined in 12.1.
- Sending and responding to invitations.
- Invitation status and the documented 24-hour expiry direction.
- Privacy-by-default behavior and appropriate success/error feedback.

The relevant functional requirements are FR-01 to FR-14. FR-15, double-booking prevention, is included in the initial scope as resolved in 12.4. Registration and verification (12.2), blocking and reporting (12.5), and confirmed-game cancellation (12.4) are also included in the initial scope.

This scope is accepted as the MVP boundary as resolved in 12.8.

### 5.2 Proposed exclusions

The following are excluded from the initial version because the available information does not establish them as necessary for the core purpose:

- Court booking.
- Payment processing.
- In-app chat.
- Player ratings or reviews.
- Attendance tracking.

These exclusions are confirmed as part of the final MVP decision (12.5).

### 5.3 Scope decisions (previously pending, now resolved)

- Registration, authentication, and verification: included (12.2).
- Blocking and reporting players: included (12.5).
- Double-booking prevention: included (12.4).
- Cancellation of confirmed games: included (12.4).
- Post-acceptance contact-information sharing: not included; contact information stays private (12.2).
- Additional scheduling and coordination functionality: rescheduling and other additional functionality are not included in the MVP (12.4).

No deferred feature is included as an approved requirement solely because it appears in an AI critique or as a proposed behavior in the draft; the inclusions above are recorded team decisions in Section 12.

## 6. Ubiquitous Language

The following terms should be used consistently throughout the PRD and related project artifacts.

| Term                     | Working definition                                                                                                      | Status or qualification                                                                                                                                  |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Player**               | A person using Rally to find a suitable badminton partner.                                                              | Primary user term. A player must be registered and email-verified (12.2).                                                                                |
| **Player profile**       | Information about a player, including playing level, general area, and relevant availability.                           | Required and optional fields are defined in 12.2.                                                                                                        |
| **Availability**         | The times when a player is available to play badminton.                                                                 | Core matching factor; availability is recorded as individual date-and-time slots (12.1).                                                                 |
| **Search criteria**      | Information used to search for potential partners, including date, time, location, and playing level.                   | Date, time, and location are mandatory; playing level is optional (12.1).                                                                                |
| **Search filters**       | Controls that exclude results that do not meet selected criteria.                                                       | Distinct from ranking; filtering behavior is defined in 12.1.                                                                                            |
| **Search results**       | Players returned in response to a search, with available information such as availability, distance, and playing level. | Matching and ordering rules are defined in 12.1.                                                                                                         |
| **Distance**             | A displayed measure of separation between a player and an agreed reference point.                                       | Reference point, units, and calculation method are defined in 12.1.                                                                                      |
| **Playing level**        | A player's badminton ability, used to help evaluate partner suitability.                                                | Scale is Beginner, Intermediate, Advanced; self-selected and editable (12.1).                                                                            |
| **Invitation**           | A request sent to another player to arrange a badminton game.                                                           | Core workflow. Required invitation details are defined in 12.3.                                                                                          |
| **Pending invitation**   | An invitation awaiting the recipient's response.                                                                        | Lifecycle term.                                                                                                                                          |
| **Accepted invitation**  | An invitation whose recipient has accepted it.                                                                          | Acceptance creates a confirmed game immediately (12.3); the two terms remain distinct concepts.                                                          |
| **Declined invitation**  | An invitation whose recipient has declined it.                                                                          | The documented team decision is that a reason is not required.                                                                                           |
| **Expired invitation**   | An unanswered invitation that has reached its expiry limit.                                                             | Expires 24 hours after creation, or at the proposed start time if that is earlier (12.3).                                                                |
| **Cancelled invitation** | An invitation withdrawn before the workflow is completed.                                                               | Sender cancellation of a pending invitation is a recorded team decision; the resulting status is Cancelled and the recipient is notified (12.3).         |
| **Confirmed game**       | A badminton game arrangement that has reached an agreed confirmation state.                                             | A confirmed game is created at the moment an invitation is accepted (12.3). It can later be cancelled by either player (12.4).                            |
| **No-results message**   | A message displayed when a search returns no matching players, with suggestions to adjust search criteria.              | A recorded team decision; the original criteria must not be changed silently.                                                                            |
| **Private information**  | Exact location and personal contact information that are not visible to other players by default.                       | Privacy by default is a recorded team decision; no exceptions are made in the MVP, including after acceptance (12.2).                                    |

### 6.1 Invitation terminology rule

The following concepts must not be treated as interchangeable:

- **Accepted invitation:** The recipient has accepted the invitation.
- **Confirmed game:** The arrangement created when an invitation is accepted, as defined in 12.3.
- **Cancelled invitation:** The invitation has been withdrawn according to the applicable cancellation rules.
- **Expired invitation:** The unanswered invitation has reached its expiry limit.

The complete invitation status model and permitted transitions are defined in 12.3. Cancellation of a confirmed game is a separate action from cancellation of an invitation and is defined in 12.4.

## 7. Functional Requirements

### 7.1 Requirement status and priority conventions

The priority labels **Must Have** and **Should Have** are inherited recommendations from the original requirements derivation. They are accepted as the MVP priorities as resolved in 12.8.

The current decision labels describe the requirements' review status:

- **Accept recommendation:** Retain the requirement's core intent, subject to any outstanding details.
- **Modify recommendation:** Retain the useful intent but refine the wording or resolve ambiguities before finalization.
- **Pending:** Do not implement the unresolved behavior as a settled rule. No requirement remains pending; all earlier pending items are resolved in Section 12.
- **Rejected:** No functional requirement is marked rejected in the supplied requirements derivation. The Human Validation Log also contains no rejected review items.

An Accept recommendation does not mean that every implementation detail is final; implementation details are as resolved in Section 12.

### FR-01 — Player Profile

**Priority:** Must Have (proposed)  
**Decision:** Accept recommendation; profile details and registration resolved in 12.2.

**Requirement:** The system shall allow players to create and maintain a player profile containing their playing level, general area, and relevant availability.

**Basis:** Profiles are part of the proposed solution and support partner discovery. The available materials do not establish all mandatory profile fields.

**Resolved:** Required and optional fields, registration, authentication, verification, and profile-editing permissions are defined in 12.2. Only the account owner may edit a profile.

### FR-02 — Search Criteria

**Priority:** Must Have (proposed)  
**Decision:** Modify recommendation.

**Requirement:** The system shall allow players to specify search criteria from the supported criteria set, including preferred date, time, location, and playing level.

The requirement does not establish that every listed field is mandatory or that availability must use individual game slots rather than recurring schedules.

**Resolved:** Date, time, and location are mandatory; playing level is optional. Availability uses individual date-and-time slots. A search is for a specific date and time window, which is matched against players' availability slots (12.1).

### FR-03 — Search Results

**Priority:** Must Have (proposed)  
**Decision:** Accept recommendation; matching rules resolved in 12.1.

**Requirement:** The system shall display players returned by a search according to the matching rules established by the team.

Availability, location, and playing level are the principal matching factors. The matching rules are those in 12.1: filters exclude non-matching players, and remaining results are ranked by distance and then playing-level closeness.

**Resolved:** The system both excludes non-matching players and ranks the remaining results. Incomplete or inactive profiles are excluded (12.1).

### FR-04 — Availability Display

**Priority:** Must Have (proposed)  
**Decision:** Accept recommendation; update and validation rules resolved in 12.1 and 12.4.

**Requirement:** The system shall display relevant availability information for players in search results.

Unknown or stale availability must not be presented as confirmed availability. Availability slots are valid until their end time passes, and are rechecked when an invitation is sent and when it is accepted.

**Resolved:** Availability is individual slots; each slot is valid until its end time; slots that have passed are removed automatically; availability is revalidated at invitation send and at acceptance (12.1, 12.4).

### FR-05 — Distance Display

**Priority:** Must Have (proposed)  
**Decision:** Modify recommendation.

**Requirement:** The system shall display distance information between a player and an agreed reference point in search results, where the distance can be calculated reliably.

The system shall not display a misleading distance when the reference location or required location information is unavailable.

**Resolved:** The reference point is the searcher's chosen search location. Distance is measured to the other player's general-area centre, using straight-line distance in kilometres rounded to the nearest whole kilometre and labelled as approximate. A maximum-distance filter is provided (12.1).

### FR-06 — Playing Level Display

**Priority:** Must Have (proposed)  
**Decision:** Accept recommendation; level categories resolved in 12.1.

**Requirement:** The system shall display each player's playing level consistently in the player profile and search results when a level has been provided.

The system shall not assign a playing level automatically when none has been provided.

**Resolved:** Categories are Beginner, Intermediate, and Advanced. Players select and edit their own level. Verification is not required (12.1). A level is required for a profile to be complete, so it is always shown for players appearing in results.

### FR-07 — Search Filters

**Priority:** Must Have (proposed)  
**Decision:** Modify recommendation.

**Requirement:** The system shall provide controls for narrowing search results using the search filters agreed by the team.

Filters must be distinguished from ranking: filters exclude results that do not satisfy selected conditions, whereas ranking changes the order in which results are presented. The final matching and ranking approach is defined in 12.1.

**Resolved:** Available filters are date/time (mandatory), location (mandatory), maximum distance (optional, default 10 km), and playing level (optional). Combined filters apply together (logical AND). Results are ordered by distance ascending, then playing-level closeness (12.1).

### FR-08 — Send Invitation

**Priority:** Must Have (proposed)  
**Decision:** Accept recommendation.

**Requirement:** The system shall allow a player to send an invitation to another player to arrange a badminton game.

The system shall confirm successful submission only after the invitation has actually been created. If submission fails, the system shall communicate the failure without displaying a false success message.

**Resolved:** Required invitation fields, eligibility rules, duplicate-invitation policy, notification method, and handling of availability changes are defined in 12.3 and 12.4.

### FR-09 — Invitation Response

**Priority:** Must Have (proposed)  
**Decision:** Modify recommendation.

**Requirement:** The system shall allow the recipient of a valid pending invitation to accept or decline it.

Declining an invitation shall not require a reason, in accordance with the recorded team decision. A response shall not be accepted when the invitation is no longer pending.

Accepting an invitation creates a confirmed game immediately, as defined in 12.3, subject to the overlap check in 12.4.

**Resolved:** Confirmation semantics, response changes (not permitted), and handling of expired, cancelled, or conflicting invitations are defined in 12.3 and 12.4.

### FR-10 — Invitation Status

**Priority:** Should Have (proposed)  
**Decision:** Modify recommendation.

**Requirement:** The system shall make the current invitation status available to the sender and recipient.

The statuses are Pending, Accepted, Declined, Expired, and Cancelled. A confirmed game is a separate concept created when an invitation is accepted.

**Resolved:** The complete status set, definitions, permitted transitions, visibility, and handling of simultaneous actions are defined in 12.3.

### FR-11 — Invitation Expiration

**Priority:** Should Have (proposed)  
**Decision:** Accept recommendation; clarifications resolved in 12.3.

**Requirement:** An unanswered invitation shall expire after 24 hours, and the sender shall be able to cancel a pending invitation.

The 24-hour expiry direction and sender cancellation are recorded team decisions in the supplied project material. The 24-hour period begins when the invitation is created, and the invitation expires earlier if the proposed game start time is reached first.

The system must not accept a response to an invitation that has already expired or been cancelled.

**Resolved:** Expiry starts at creation time using server time (UTC), boundaries are evaluated against server time, the resulting status is Expired, the recipient is notified when a pending invitation is cancelled by the sender, and no reminders are sent in the MVP (12.3).

### FR-12 — Invitation Notifications

**Priority:** Should Have (proposed)  
**Decision:** Modify recommendation.

**Requirement:** The system should notify the invitation sender when the recipient accepts or declines an invitation.

Notifications are included in the MVP. The system must not claim that a notification was delivered unless delivery has been established according to the notification design in 12.3.

**Resolved:** Channels are in-app notification and email; delivery is attempted within 5 minutes; failed email delivery is retried up to 3 times within 15 minutes (12.3).

### FR-13 — No Search Results

**Priority:** Should Have (proposed)  
**Decision:** Accept recommendation.

**Requirement:** When no players match a search, the system shall display a clear no-results message and suggest adjusting the date, time, or location.

The system shall not silently modify the player's search criteria. The player must choose to change criteria before a subsequent search uses the revised values.

**Resolved:** The message also suggests adjusting playing level and maximum distance when those filters are applied (12.1).

### FR-14 — Profile Privacy

**Priority:** Must Have (proposed)  
**Decision:** Modify recommendation.

**Requirement:** The system shall keep a player's exact location and personal contact information private by default while displaying profile information permitted by the agreed visibility rules.

Search results and player profiles must not expose private information to players who are not authorized to access it.

**Resolved:** The public and private field sets, the absence of user-controlled visibility settings in the MVP, the authentication and access-control model, and the rule that no information becomes visible after invitation acceptance are defined in 12.2.

### FR-15 — Prevent Double-Booking

**Priority:** Should Have (proposed)  
**Decision:** Included in the MVP; conflict policy resolved in 12.4.

**Requirement:** The system shall prevent a player from having overlapping confirmed games.

A game's duration is the start-to-end time stated in the invitation; two games overlap when one starts before the other ends and ends after the other starts. Concurrent confirmations are resolved so that the first committed confirmation succeeds and the other is rejected (12.4).

## 11. Acceptance criteria validation rule

Before development or formal acceptance testing, the team should:

Resolve the decisions on which each criterion depends.

Replace conditional wording with explicit behavior where the team reaches a decision.

Define the test inputs, expected results, and relevant error cases.

Check that each criterion corresponds to its functional requirement.

Ensure that no criterion introduces behavior that the team has deferred or not approved.

## 12. Resolved Decisions (previously Open Questions and Pending Decisions)

Every question that was previously unresolved is answered below. The answers are recorded as team decisions for the MVP, grouped by topic.

### 12.1 Search and Matching

Related requirements: FR-02, FR-03, FR-04, FR-05, FR-06, FR-07.

Which search criteria must a player enter, and which are optional?
**Resolved:** Date, time window, and location are mandatory. Playing level is optional; if omitted, players of any level are returned. Maximum distance is optional and defaults to 10 km.

Is availability based on individual dates and times or a recurring schedule?
**Resolved:** Individual dates and times. Each availability entry is a slot with a date, start time, and end time. A player may have multiple slots. Recurring schedules are not supported in the MVP.

How long does an availability entry remain valid?
**Resolved:** A slot remains valid until its end time passes, after which it is removed automatically. Players may edit or delete a slot at any time.

Which matching criteria exclude a player from results, and which merely affect ranking?
**Resolved:** The following exclude a player: no availability slot overlapping the searched date and time window, general area outside the maximum distance, playing level not matching the selected level (when selected), the player being blocked by or blocking the searcher, and an incomplete or inactive profile. Distance and playing-level closeness affect ranking only.

Should Rally rank results, and if so, according to what agreed rules?
**Resolved:** Yes. Results are ordered by distance (nearest first), then by playing-level closeness to the searcher's own level (closest first), then by earliest overlapping availability.

How should incomplete or inactive profiles appear in search results?
**Resolved:** They do not appear. A profile is complete when it has a display name, playing level, general area, and verified email. A profile is inactive when it has no future availability slot.

What is the reference point for distance, which units are used, and how is distance calculated?
**Resolved:** The reference point is the location the searcher selects for the search, defaulting to the centre of the searcher's profile general area. Distance is measured to the centre of the other player's general area (never exact location), as straight-line (great-circle) distance in kilometres, rounded to the nearest whole kilometre and labelled as approximate. If either location is unavailable, no distance is shown.

Is a maximum-distance filter required?
**Resolved:** Yes. It is an optional filter with choices of 5, 10, 20, and 50 km, defaulting to 10 km.

Which playing-level categories will be used, and can players select or edit their own level?
**Resolved:** Beginner, Intermediate, and Advanced. Players select their own level at profile creation and may edit it at any time.

Is verification of playing level necessary?
**Resolved:** No. Playing level is self-reported and is not verified in the MVP.

### 12.2 Profiles, Registration, and Privacy

Related requirements: FR-01, FR-05, FR-06, FR-14, NFR-03.

Is registration required before using Rally?
**Resolved:** Yes. A registered account is required to create a profile, search, and send or respond to invitations.

Is email verification or another verification method required?
**Resolved:** Yes. Email verification is required before a profile can appear in search results or the player can send invitations. No other verification method is required.

Which profile fields are mandatory, and which are optional?
**Resolved:** Mandatory: display name, email address (private), password, playing level, general area, and at least one availability slot to be searchable. Optional: phone number (private).

Which profile fields are visible to other players?
**Resolved:** Display name, playing level, general area (named at district or neighbourhood level), availability slots, and approximate distance from the search reference point.

How are exact location and personal contact information protected?
**Resolved:** The system does not collect or store a player's exact location in the MVP, only a general area. Email address and phone number are stored privately and are never returned in search results, profiles, invitations, or notifications shown to other players. Access is enforced on the server side.

Are player-controlled privacy settings required?
**Resolved:** No. Visibility rules are fixed in the MVP.

Does accepting an invitation change what information becomes visible?
**Resolved:** No. Exact location and personal contact information remain private after acceptance. Players coordinate through the invitation details, which include the proposed venue.

What account and authorization mechanisms are required to enforce privacy rules?
**Resolved:** Email-and-password authentication with session-based access. Every request to view profiles, search, or access invitations requires an authenticated session. A player can read and edit only their own account data and can view only invitations they sent or received.

### 12.3 Invitations and Their Lifecycle

Related requirements: FR-08, FR-09, FR-10, FR-11, FR-12.

Which information must an invitation contain, including the proposed date, time, and location?
**Resolved:** Recipient, proposed date, start time, end time, and venue name (free text). All are mandatory.

How does a recipient access an invitation?
**Resolved:** Through an in-app invitations list showing received and sent invitations, and through an email notification linking to it.

What are the complete invitation statuses, including how cancellation is represented?
**Resolved:** Pending, Accepted, Declined, Expired, and Cancelled. Cancelled represents a pending invitation withdrawn by its sender.

What transitions are permitted between those statuses?
**Resolved:** Pending can become Accepted, Declined, Expired, or Cancelled. Accepted, Declined, Expired, and Cancelled are final. No other transitions are permitted.

Does acceptance immediately confirm a game, or is a further confirmation step required?
**Resolved:** Acceptance immediately creates a confirmed game. No further confirmation step is required. The invitation's status remains Accepted, and the confirmed game is a separate record.

When exactly does the 24-hour expiry period begin?
**Resolved:** When the invitation is created, using server time. If the proposed start time occurs before 24 hours have elapsed, the invitation expires at the proposed start time.

What happens if a response, cancellation, and expiry occur at almost the same time?
**Resolved:** The status is validated when each action is committed, and the first committed action wins. Later actions are rejected with a message stating the invitation is no longer pending.

Can a recipient change a previously recorded response?
**Resolved:** No. A response is final. A recipient who has accepted may cancel the confirmed game under 12.4.

Should duplicate invitations for the same proposed game be prevented?
**Resolved:** Yes. A sender cannot send a new invitation to the same recipient while a Pending invitation from that sender to that recipient has an overlapping time range.

Should the sender receive notifications for acceptance and decline?
**Resolved:** Yes, in the MVP.

Which notification channels and delivery expectations are required?
**Resolved:** In-app notification and email. Delivery is attempted within 5 minutes of the event.

What happens when a notification cannot be delivered?
**Resolved:** Email delivery is retried up to 3 times within 15 minutes. The in-app status always reflects the true invitation state, and the system never states that a notification was delivered unless delivery was confirmed. Failures are logged.

### 12.4 Scheduling, Availability, and Cancellation

Related requirements: FR-04, FR-08, FR-09, FR-11, FR-15.

When must availability be revalidated?
**Resolved:** When an invitation is sent and when it is accepted.

What happens when a player becomes unavailable after an invitation is sent or accepted?
**Resolved:** If the recipient no longer has availability covering the proposed time, or has an overlapping confirmed game, acceptance is rejected with an explanatory message. After acceptance, a player who can no longer attend cancels the confirmed game.

Who can cancel a confirmed game?
**Resolved:** Either of the two players, at any time before the game's start time.

Does cancellation require confirmation or a reason?
**Resolved:** It requires an explicit confirmation step but no reason.

How is the other player informed of a confirmed-game cancellation?
**Resolved:** By in-app notification and email, following the delivery rules in 12.3.

How should availability be updated after cancellation?
**Resolved:** The availability slot used by the game is restored for both players if its end time has not passed.

Should rescheduling be supported?
**Resolved:** No. A player cancels the confirmed game and sends a new invitation.

What constitutes an overlapping game?
**Resolved:** Two confirmed games for the same player overlap when one starts before the other ends and ends after the other starts. A game's duration is the start and end time stated in its invitation.

Should pending invitations reserve a time slot?
**Resolved:** No. Only confirmed games block time.

How should multiple invitations for the same time be handled?
**Resolved:** A recipient may hold several pending invitations for the same time. Accepting one creates a confirmed game; acceptance of any other overlapping invitation is then rejected with a message, and the recipient may decline it or let it expire.

Should double-booking prevention be included in the MVP?
**Resolved:** Yes. FR-15 is included.

How should simultaneous confirmation attempts be resolved?
**Resolved:** Confirmations are processed atomically. The first committed confirmation succeeds and the other is rejected with a conflict message.

### 12.5 Safety and Additional Features

Related requirements: FR-08, FR-14; MVP scope.

Should players be able to block other players?
**Resolved:** Yes. A blocked player cannot appear in the blocker's search results, cannot see the blocker in theirs, and cannot send invitations to the blocker.

Should players be able to report unwanted interactions?
**Resolved:** Yes. A player can report another player from that player's profile or from an invitation, choosing a category and optionally adding free-text details. Reports are stored for review by the project administrators.

If blocking is included, how should unblocking work and affect invitations?
**Resolved:** Players can unblock from a blocked-players list. Blocking cancels all Pending invitations between the two players. Existing confirmed games are unaffected until either player cancels. Unblocking restores visibility but does not restore cancelled invitations.

Are blocking and reporting necessary for the initial version?
**Resolved:** Yes, both are included in the initial version.

Are court booking, payments, in-app chat, player ratings, and attendance tracking formally excluded from the MVP?
**Resolved:** Yes. All five are formally excluded.

### 12.6 Quality Targets and Verification

Related requirements: NFR-01 to NFR-04.

Are the proposed performance, usability, privacy, and reliability thresholds feasible?
**Resolved:** Yes. All four NFR targets are accepted as stated in Appendix A.2.

What test environment and workload should be used for performance testing?
**Resolved:** A staging environment equivalent to production, loaded with a synthetic dataset of 10,000 player profiles, driven by a load-testing tool at 100 concurrent simulated users for 10 minutes issuing search requests.

How will representative usability-test participants and sample sizes be selected?
**Resolved:** At least 10 participants who play badminton recreationally and are not members of the project team. Each attempts the defined find-a-player task once, unassisted, and is timed.

What constitutes a successful operation for reliability measurement?
**Resolved:** A valid profile, search, or invitation request that returns the correct result without a server error or failed completion.

Which privacy test cases and authorization boundaries are required?
**Resolved:** Test cases cover unauthenticated access, authenticated access by another player, search results, profile pages, invitation views, notifications, and direct requests to the server interface for another player's exact location or contact information. The boundary is that only the account owner can see their own email address and phone number, and no player's exact location is stored.

Which exclusions and measurement definitions apply to the reliability target?
**Resolved:** Excluded are planned maintenance announced at least 24 hours ahead and outages of third-party email services. Invalid requests are not counted. Success is as defined above.

Are the proposed test periods and thresholds appropriate for the project's scope and timeline?
**Resolved:** Yes. Reliability is measured over a 30-day period beginning at pilot release; performance and usability tests are run once before release.

### 12.7 Evidence and Product Validation

Can the original interview notes and prototype feedback be made available to verify the evidence labels and details?
**Resolved:** The evidence labels in this PRD are accepted as written, and no further interview details are introduced. The original interview notes and prototype feedback are to be kept with the project record, and any later discrepancy found between them and this PRD is handled through the change process in 12.8.

How frequently does the client's coordination problem occur, and what impact does it have?
**Resolved:** Frequency and impact are not prerequisites for the MVP. They are measured after pilot release through the success metrics defined below.

Does Rally reduce the effort needed to arrange a game compared with existing alternatives?
**Resolved:** This is evaluated using two success metrics: the median time from starting a search to an accepted invitation, compared with the participant's stated time using their current method in the usability test; and the share of searches that result in a sent invitation.

Are there additional client needs or constraints not captured by the current requirements?
**Resolved:** None are recorded beyond those in this PRD. Any newly identified need enters through the change process in 12.8.

Which proposed requirements and priorities will the team formally accept, modify, reject, or defer?
**Resolved:** All Accept and Modify requirements are accepted with the details in this section, none is rejected, and no requirement is deferred.

### 12.8 Requirements and MVP Finalization

The team accepts the proposed priorities and MVP scope as the product baseline.

In particular:

Must Have and Should Have labels are accepted as the MVP priorities.

The initial MVP boundary is accepted as described in Section 5.

FR-15 is included.

Registration, verification, blocking, reporting, and confirmed-game cancellation are included.

The numerical NFR targets are accepted.

Requirements marked Accept or Modify are accepted with the details recorded in this section.

Decisions are recorded with their outcome and rationale in this section. Where evidence could not be verified, the PRD does not present the decision as a client requirement. Changes after this baseline are made by recording a new decision with its outcome, rationale, and supporting evidence where available.

## Appendix A — Requirements Status Summary

### A.1 Functional requirement dispositions

The following counts preserve the original requirements derivation. They describe the recommended dispositions, which are accepted as resolved in 12.8.

| Disposition | Requirement IDs | Count |
| --- | --- | --- |
| Accept recommendation | FR-01, FR-03, FR-04, FR-06, FR-08, FR-11, FR-13 | 7 |
| Modify recommendation | FR-02, FR-05, FR-07, FR-09, FR-10, FR-12, FR-14, FR-15 | 8 |
| Rejected in original derivation | None | 0 |

FR-15 is classified as Modify in the original derivation; it is now included in the MVP with the conflict rules in 12.4. FR-11 retains the recorded 24-hour expiry direction and pending-invitation cancellation behavior, and its lifecycle details are resolved in 12.3.

### A.2 Non-functional requirement dispositions

| ID | Proposed target | Current status |
| --- | --- | --- |
| NFR-01 | Search results within 2 seconds for at least 95% of requests at 100 concurrent users. | Accepted; verified using the test setup in 12.6. |
| NFR-02 | At least 90% of representative test users complete the defined find-a-player task within 2 minutes without assistance. | Accepted; verified using the test setup in 12.6. |
| NFR-03 | 100% of defined privacy tests prevent unauthorized access to exact location and personal contact information. | Accepted; verified using the test cases in 12.6. |
| NFR-04 | At least 99.5% successful completion of valid profile, search, and invitation operations over a defined 30-day monitoring period, excluding planned maintenance. | Accepted; verified using the definitions in 12.6. |

### A.3 Evidence limitations

The available project account documents the client's difficulty arranging games when friends are unavailable, the time cost of messaging friends individually, and the limitations of relying on WhatsApp groups. It also identifies availability, location, and playing level as relevant factors.

The original interview and prototype records were not available for direct verification during this revision. Consequently, the PRD does not claim that every proposed feature or quality target has been verified with the client. AI-generated critique and recommendations have been used only to guide revision in accordance with the Human Validation Log, not as independent client evidence.

## Appendix B — Human Validation Log Change Summary

The following summary identifies how the validation dispositions were applied in this revision.

| Outcome | Validation IDs | Applied changes |
| --- | --- | --- |
| Accept | HV-01, HV-02, HV-03, HV-04 | Retained the core product purpose and target users, avoided invented client statements, and standardized terminology. |
| Accept | HV-12, HV-14, HV-15, HV-19 | Retained stale-availability safeguards, the no-results guidance, honest invitation-submission feedback, and sender cancellation of pending invitations. |
| Accept | HV-28, HV-30, HV-31, HV-35 | Preserved relevant edge cases, honest error handling, original FR IDs, cross-references, and explicit evidence limitations. |
| Modify | HV-05, HV-08, HV-10, HV-13 | Kept the three main matching factors; clarified distance limitations, profile-field uncertainty, and the distinction between filtering and ranking. The ranking rules and fields are now defined in 12.1 and 12.2. |
| Modify | HV-16, HV-17, HV-18, HV-21, HV-25 | Separated invitation acceptance from game confirmation; clarified lifecycle ambiguity, retained the 24-hour expiry direction, qualified notifications, and retained privacy by default. Timing and status rules are now defined in 12.3. |
| Modify | HV-29, HV-32, HV-33 | Addressed simultaneous actions through status validation, identified acceptance criteria that depend on decisions, and retained all four NFRs as targets, now accepted in 12.6. |
| Defer | HV-06, HV-07, HV-09, HV-11 | Mandatory search fields, availability format, playing-level categories, registration, and verification were left open in the earlier draft and are now resolved in 12.1 and 12.2. |
| Defer | HV-20, HV-22, HV-23, HV-24 | Confirmed-game cancellation, duplicate invitations, double-booking prevention, and conflicts involving pending invitations were left open in the earlier draft and are now resolved in 12.3 and 12.4. |
| Defer | HV-26, HV-27, HV-34 | Post-acceptance privacy changes, blocking and reporting, and final MVP boundaries were left open in the earlier draft and are now resolved in 12.2, 12.5, and 12.8. |

Rejected items: None. The Human Validation Log explicitly states that no items were marked Reject because the complete original critique was not available for a reliable item-by-item comparison. No critique suggestion has been treated as a team decision merely because it appeared in the AI review.

## Conclusion

This Validated PRD preserves Rally's core purpose and original requirement IDs while aligning the requirements, user flows, edge cases, and acceptance criteria with the Human Validation Log. All previously open questions are resolved in Section 12.
