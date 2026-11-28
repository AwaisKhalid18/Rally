"""M9 Messaging — the three rules that bound a conversation.

In-app chat is **not** in the Final Validated PRD (PRD §12.5 excludes it); it was added
on an explicit instruction. These tests pin the rules that keep it from undoing the
privacy model: a confirmed game is required, a block closes it, and a message may not
carry contact data.
"""
import datetime as _dt

from django.test import TestCase

from rally.core import clock
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.invitations.api import facade as invitations
from rally.modules.messaging.api import facade as messaging
from rally.modules.messaging.internal.models import Conversation, Message
from rally.modules.profiles.api import facade as profiles
from rally.modules.safety.api import facade as safety

PASSWORD = "longenough"
AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
]
VENUE = "Rally Courts, F-7"


def at(day_offset: int, hour: int) -> _dt.datetime:
    midnight = clock.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + _dt.timedelta(days=day_offset, hours=hour)


class MessagingCase(TestCase):
    def setUp(self):
        profiles.replace_areas(AREAS)
        self.me = self.make_player("me")
        self.them = self.make_player("them")
        self.stranger = self.make_player("stranger")
        self.game_id = self.play_together(self.me, self.them, 18, 20)

    def make_player(self, name):
        account_id = identity.register(f"{name}@example.com", PASSWORD).account_id
        assert profiles.save_profile(account_id, name.title(), "intermediate", "isb-f7").ok
        identity.verify_email(identity.get_verification_token(account_id))
        assert availability.add_slot(account_id, at(1, 8), at(1, 23)).ok
        return account_id

    def play_together(self, sender, recipient, start, end):
        sent = invitations.send(
            sender_account_id=sender,
            recipient_account_id=recipient,
            starts_at=at(1, start),
            ends_at=at(1, end),
            venue=VENUE,
        )
        assert sent.ok, sent.errors
        accepted = invitations.accept(sent.invitation_id, recipient)
        assert accepted.ok, accepted.error
        return accepted.game_id

    def thread(self):
        return messaging.open_conversation(self.me, self.them).conversation_id


class AConfirmedGameIsRequiredTests(MessagingCase):
    """Rule 1 — chat is for arranging a game, not a channel to anyone."""

    def test_two_players_with_a_game_can_open_a_conversation(self):
        result = messaging.open_conversation(self.me, self.them)

        self.assertTrue(result.ok, result.error)
        self.assertIsNotNone(result.conversation_id)

    def test_a_player_with_no_game_cannot(self):
        result = messaging.open_conversation(self.me, self.stranger)

        self.assertEqual(result.error, messaging.NO_CONFIRMED_GAME)
        self.assertEqual(Conversation.objects.count(), 0)

    def test_a_pending_invitation_is_not_enough(self):
        """Only a *confirmed* game: agreeing to play is the threshold."""
        sent = invitations.send(
            sender_account_id=self.me,
            recipient_account_id=self.stranger,
            starts_at=at(1, 20),
            ends_at=at(1, 22),
            venue=VENUE,
        )
        self.assertTrue(sent.ok, sent.errors)

        self.assertEqual(
            messaging.open_conversation(self.me, self.stranger).error,
            messaging.NO_CONFIRMED_GAME,
        )

    def test_you_cannot_message_yourself(self):
        self.assertEqual(
            messaging.open_conversation(self.me, self.me).error,
            messaging.CANNOT_MESSAGE_YOURSELF,
        )

    def test_opening_it_twice_returns_the_same_conversation(self):
        """A 'Message' button presses more than once."""
        first = messaging.open_conversation(self.me, self.them).conversation_id
        second = messaging.open_conversation(self.them, self.me).conversation_id

        self.assertEqual(first, second)
        self.assertEqual(Conversation.objects.count(), 1)

    def test_the_pair_is_stored_once_whichever_way_round(self):
        messaging.open_conversation(self.them, self.me)

        row = Conversation.objects.get()
        self.assertLess(row.lower_account_id, row.higher_account_id)

    def test_cancelling_the_game_closes_the_conversation(self):
        thread = self.thread()
        self.assertTrue(messaging.post_message(thread, self.me, "See you there").ok)

        invitations.cancel_game(self.game_id, self.me)

        result = messaging.post_message(thread, self.me, "Still on?")
        self.assertEqual(result.error, messaging.NO_CONFIRMED_GAME)

    def test_a_game_that_has_been_played_still_allows_messages(self):
        """People need to talk after playing, not only before."""
        thread = self.thread()
        previous = clock.set_clock(clock.FrozenClock(at(2, 12)))
        self.addCleanup(clock.set_clock, previous)

        self.assertTrue(messaging.post_message(thread, self.me, "Good game").ok)


class BlockingClosesItTests(MessagingCase):
    """Rule 2 — ASR-10, the same rule search, invitations and favorites apply."""

    def test_a_blocked_pair_cannot_open_a_conversation(self):
        safety.block(self.me, self.them)

        self.assertEqual(
            messaging.open_conversation(self.me, self.them).error, messaging.BLOCKED
        )

    def test_it_is_blocked_in_the_other_direction_too(self):
        safety.block(self.them, self.me)

        self.assertEqual(
            messaging.open_conversation(self.me, self.them).error, messaging.BLOCKED
        )

    def test_neither_can_post_to_one_they_already_had(self):
        thread = self.thread()
        safety.block(self.me, self.them)

        self.assertEqual(
            messaging.post_message(thread, self.me, "Hello").error, messaging.BLOCKED
        )
        self.assertEqual(
            messaging.post_message(thread, self.them, "Hello").error, messaging.BLOCKED
        )

    def test_it_disappears_from_both_listings(self):
        self.thread()
        safety.block(self.me, self.them)

        self.assertEqual(messaging.list_conversations(self.me), [])
        self.assertEqual(messaging.list_conversations(self.them), [])

    def test_the_history_is_kept_and_unblocking_restores_it(self):
        """Blocking hides; it does not destroy what was said."""
        thread = self.thread()
        messaging.post_message(thread, self.me, "Six o'clock then")
        safety.block(self.me, self.them)

        safety.unblock(self.me, self.them)

        (conversation,) = messaging.list_conversations(self.me)
        self.assertEqual(conversation.last_message_body, "Six o'clock then")

    def test_a_blocked_pair_is_not_offered_an_existing_thread(self):
        thread = self.thread()
        safety.block(self.me, self.them)

        self.assertIsNone(messaging.conversation_with(self.me, self.them))
        self.assertEqual(thread, Conversation.objects.get().pk, "the row still exists")


class NoContactDataTests(MessagingCase):
    """Rule 3 — the guard that keeps ASR-04 intact on this path.

    A free-text box between two players goes around both barriers that keep contact
    data inside M1. This refuses the obvious cases; it is a guard rail, not a proof.
    """

    def setUp(self):
        super().setUp()
        self.thread_id = self.thread()

    def refused(self, body):
        result = messaging.post_message(self.thread_id, self.me, body)
        self.assertEqual(result.error, messaging.LOOKS_LIKE_CONTACT_DATA, body)
        return result

    def test_an_email_address_is_refused(self):
        self.refused("mail me at me@example.com")

    def test_an_address_on_its_own_is_refused(self):
        self.refused("me@example.com")

    def test_a_phone_number_is_refused(self):
        self.refused("my number is 03001234567")

    def test_a_spaced_phone_number_is_refused(self):
        self.refused("0300 123 4567")

    def test_a_dashed_phone_number_is_refused(self):
        self.refused("0300-123-4567")

    def test_an_international_number_is_refused(self):
        self.refused("+92 300 1234567")

    def test_a_bracketed_number_is_refused(self):
        self.refused("(0300) 1234567")

    def test_nothing_is_stored_when_it_is_refused(self):
        """The address must not reach the database either."""
        self.refused("me@example.com")

        self.assertEqual(Message.objects.count(), 0)

    def test_an_ordinary_message_goes_through(self):
        result = messaging.post_message(self.thread_id, self.me, "See you at six by the courts")

        self.assertTrue(result.ok, result.error)

    def test_a_time_is_not_mistaken_for_a_number(self):
        """The guard must not refuse the messages the feature exists for."""
        for body in ("18:00 works", "Let's say 6pm", "Court 3 at 7", "I'll be 10 mins late"):
            with self.subTest(body=body):
                result = messaging.post_message(self.thread_id, self.me, body)
                self.assertTrue(result.ok, f"{body!r} was refused: {result.error}")

    def test_the_rule_is_published_so_a_page_can_warn_first(self):
        self.assertTrue(messaging.carries_contact_data("me@example.com"))
        self.assertFalse(messaging.carries_contact_data("see you at 6"))


class PostingAndReadingTests(MessagingCase):
    def setUp(self):
        super().setUp()
        self.thread_id = self.thread()

    def test_a_message_is_stored_and_read_back_in_order(self):
        messaging.post_message(self.thread_id, self.me, "First")
        messaging.post_message(self.thread_id, self.them, "Second")

        bodies = [m.body for m in messaging.list_messages(self.thread_id, self.me)]

        self.assertEqual(bodies, ["First", "Second"])

    def test_both_players_see_the_same_thread(self):
        messaging.post_message(self.thread_id, self.me, "Hello")

        mine = messaging.list_messages(self.thread_id, self.me)
        theirs = messaging.list_messages(self.thread_id, self.them)

        self.assertEqual([m.body for m in mine], [m.body for m in theirs])

    def test_each_knows_which_messages_are_their_own(self):
        messaging.post_message(self.thread_id, self.me, "Mine")

        (message,) = messaging.list_messages(self.thread_id, self.me)

        self.assertTrue(message.was_sent_by(self.me))
        self.assertFalse(message.was_sent_by(self.them))

    def test_an_empty_message_is_refused(self):
        self.assertEqual(
            messaging.post_message(self.thread_id, self.me, "   ").error,
            messaging.BODY_REQUIRED,
        )

    def test_a_message_at_the_limit_is_accepted(self):
        """BVA on a real bound."""
        body = "x" * messaging.MESSAGE_MAX_LENGTH

        self.assertTrue(messaging.post_message(self.thread_id, self.me, body).ok)

    def test_a_message_one_character_over_is_refused(self):
        body = "x" * (messaging.MESSAGE_MAX_LENGTH + 1)

        self.assertEqual(
            messaging.post_message(self.thread_id, self.me, body).error,
            messaging.BODY_TOO_LONG,
        )

    def test_the_text_is_trimmed(self):
        messaging.post_message(self.thread_id, self.me, "  spaced  ")

        self.assertEqual(messaging.list_messages(self.thread_id, self.me)[0].body, "spaced")


class OwnerOnlyTests(MessagingCase):
    """ASR-05 — you reach only your own conversations."""

    def setUp(self):
        super().setUp()
        self.thread_id = self.thread()
        messaging.post_message(self.thread_id, self.me, "Private")

    def test_a_stranger_cannot_read_it(self):
        self.assertIsNone(messaging.list_messages(self.thread_id, self.stranger))

    def test_a_stranger_cannot_post_to_it(self):
        result = messaging.post_message(self.thread_id, self.stranger, "Butting in")

        self.assertEqual(result.error, messaging.NOT_FOUND)
        self.assertEqual(Message.objects.count(), 1)

    def test_a_conversation_that_does_not_exist_gives_the_same_answer(self):
        """Nothing tells a stranger's thread apart from one that is not there."""
        self.assertIsNone(messaging.list_messages(999_999, self.me))
        self.assertEqual(
            messaging.post_message(999_999, self.me, "Hello").error, messaging.NOT_FOUND
        )

    def test_a_stranger_sees_none_of_it_in_their_list(self):
        self.assertEqual(messaging.list_conversations(self.stranger), [])

    def test_a_stranger_cannot_mark_it_read(self):
        self.assertEqual(messaging.mark_read(self.thread_id, self.stranger), 0)


class UnreadTests(MessagingCase):
    def setUp(self):
        super().setUp()
        self.thread_id = self.thread()

    def test_what_the_other_player_sent_is_unread(self):
        messaging.post_message(self.thread_id, self.them, "Hello")

        self.assertEqual(messaging.unread_count(self.me), 1)

    def test_your_own_messages_are_never_unread_for_you(self):
        messaging.post_message(self.thread_id, self.me, "Hello")

        self.assertEqual(messaging.unread_count(self.me), 0)
        self.assertEqual(messaging.unread_count(self.them), 1)

    def test_reading_the_thread_clears_it(self):
        messaging.post_message(self.thread_id, self.them, "Hello")

        marked = messaging.mark_read(self.thread_id, self.me)

        self.assertEqual(marked, 1)
        self.assertEqual(messaging.unread_count(self.me), 0)

    def test_reading_does_not_mark_your_own_as_read(self):
        messaging.post_message(self.thread_id, self.me, "Mine")

        messaging.mark_read(self.thread_id, self.me)

        self.assertEqual(messaging.unread_count(self.them), 1)

    def test_the_listing_carries_the_count_and_the_last_line(self):
        messaging.post_message(self.thread_id, self.them, "First")
        messaging.post_message(self.thread_id, self.them, "Second")

        (conversation,) = messaging.list_conversations(self.me)

        self.assertEqual(conversation.unread_count, 2)
        self.assertEqual(conversation.last_message_body, "Second")
        self.assertEqual(conversation.other_party_account_id, self.them)

    def test_a_conversation_with_nothing_said_yet_reads_as_empty(self):
        (conversation,) = messaging.list_conversations(self.me)

        self.assertEqual(conversation.unread_count, 0)
        self.assertEqual(conversation.last_message_body, "")


class NothingPrivateIsStoredTests(MessagingCase):
    """Rule 6 — M9 holds no contact data of its own."""

    def test_the_tables_hold_no_contact_column(self):
        conversation_columns = {f.attname for f in Conversation._meta.fields}
        message_columns = {f.attname for f in Message._meta.fields}

        self.assertEqual(
            conversation_columns,
            {"id", "lower_account_id", "higher_account_id", "created_at", "last_message_at"},
        )
        self.assertEqual(
            message_columns,
            {"id", "conversation_id", "sender_account_id", "body", "sent_at", "read_at"},
        )

    def test_no_published_record_carries_an_address(self):
        thread = self.thread()
        messaging.post_message(thread, self.me, "See you at six")

        for record in messaging.list_conversations(self.me):
            for value in vars(record).values():
                self.assertNotIn("@", str(value))
        for record in messaging.list_messages(thread, self.me):
            for value in vars(record).values():
                self.assertNotIn("@", str(value))

    def test_m9_holds_no_import_of_m1(self):
        """Contact data lives in M1 and must not be reachable from a message path."""
        from rally.modules.messaging.api import facade
        from rally.modules.messaging.internal import conversations, models

        for module in (facade, conversations, models):
            leaked = [
                name
                for name, value in vars(module).items()
                if getattr(value, "__module__", "").startswith("rally.modules.identity")
                or getattr(value, "__name__", "").startswith("rally.modules.identity")
            ]
            self.assertEqual(leaked, [], f"{module.__name__} imports M1: {leaked}")
