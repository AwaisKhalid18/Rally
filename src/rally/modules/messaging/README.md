# M9 — Messaging

In-app chat between two players who have a confirmed game.

| | |
| --- | --- |
| **Owns** | `conversation`, `message` |
| **Depends on** | M5 (is there a confirmed game?) · M6 (the block rule) |
| **Serves** | in-app chat |

> ## This module is ahead of the artefacts
>
> **PRD §12.5 records in-app chat as formally excluded from the MVP**, alongside court
> booking, payments, ratings and attendance tracking, and AGENTS.md §7 repeats it. That
> is a *client-validated* decision.
>
> M9 was built on an explicit instruction from the project lead to add it anyway. Until
> the team records that decision, the code and the artefacts disagree, and **the
> artefacts are what the client agreed to**. Three documents need updating before this
> is defensible in a review:
>
> 1. **PRD §12.5** — the answer to "is in-app chat excluded?" is no longer Yes.
> 2. **AGENTS.md §7** — remove chat from the out-of-scope list; §3 gains M9.
> 3. **A new ADR** — why a ninth module, why it depends on M5 and M6, and what it does
>    to ASR-04. `architecture.md` §16 is the precedent for how to record an amendment
>    that the client has not validated.
>
> Until then this README is the record that it was a deliberate, instructed exception
> and not an oversight.

## The three rules

Chat is where the privacy model is easiest to undo, so M9 enforces three things itself
rather than trusting the caller (rule 14).

**1. A conversation exists only where a confirmed game does.** Chat is for arranging a
game two players have already agreed to play — not a channel to anybody a search turned
up. M9 asks `M5.have_confirmed_game_between()`; it never reads M5's tables. A *pending*
invitation is not enough, and cancelling the game closes the thread. A game that has
already been played still allows messages: people need to talk afterwards too.

**2. A block closes it, both directions.** The same rule M4, M5 and M8 apply (ASR-10).
A blocked pair cannot open a thread, cannot post to one they already had, and do not see
it listed. The history is **kept** — unblocking restores it, the way unblocking restores
visibility everywhere else.

**3. A message may not carry contact data.** This is the one that matters. Rule 6 and
ASR-04 keep email and phone inside M1 behind two barriers: the data lives only there,
and every response is built from a public view model. A free-text box between two
players goes around both, by hand. So M9 refuses a message that looks like it carries an
address or a dialable number, before it is stored, and says why.

That check is **deliberately blunt and openly incomplete**. It catches
`me@example.com`, `03001234567`, `0300 123 4567`, `0300-123-4567`, `+92 300 1234567`
and `(0300) 1234567`. It will sometimes refuse an innocent message, and it cannot stop
somebody spelling a number out in words. It is a guard rail, not a proof — and the
honest way to describe it in the report is as a mitigation, not a control.

Tests pin both directions: every format above is refused, and `18:00 works`,
`Let's say 6pm`, `Court 3 at 7` and `I'll be 10 mins late` all go through, because a
guard that blocks the messages the feature exists for is worse than none.

## Published interface

| Operation | Notes |
| --- | --- |
| `open_conversation(a, b)` | Idempotent, so a "Message" button can call it every time. |
| `conversation_with(a, b)` | The existing open thread, or `None`. |
| `post_message(id, sender, body)` | Re-checks every rule — a block or a cancelled game since the thread opened still stops it. |
| `list_messages(id, account_id)` | Oldest first. `None` for a non-participant, which the caller turns into a not-found (ASR-05). |
| `list_conversations(account_id)` | Newest activity first, with unread counts. Blocked pairs omitted. |
| `mark_read(id, account_id)` · `unread_count(account_id)` | What the *other* player sent; never your own. |
| `carries_contact_data(body)` | Published so a page can warn first, and so the rule has one home. |

## What it stores, and what it does not

`conversation` holds the two account ids, ordered so a pair can only have one thread,
and `message` holds the words, who said them and when. There is **no contact column**,
no profile data and no location. Tests assert the exact column sets.

M9 holds no import of M1 at all — a test asserts it — so there is no path from a message
to an address.

## Why no email or outbox record

A new message writes no outbox record and sends no email. Two reasons: a per-message
email would put chat traffic on the path ASR-12 keeps clear for the things that matter,
and the free provider plan allows 300 a day (AGENTS.md §1). Unread messages show as a
count in the header instead.

That is a judgement, not a requirement — nothing specifies it, because nothing specifies
chat at all.

## Rules this module carries

- **Rule 1 / 2.** M9 reaches M5 and M6 through their facades and reads neither's tables.
- **Rule 3.** M9 does not import M7 and appends nothing.
- **Rule 6.** No contact data stored, published or logged — and messages that look like
  they carry some are refused.
- **Rule 14.** Platform collects the words and reports what M9 decided.
- **ASR-05.** A non-participant gets the same answer as for a thread that does not exist.
- **ASR-10.** Blocked pairs, both directions.
