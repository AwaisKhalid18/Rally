"""The chat screens, end to end.

In-app chat is **not** in the Final Validated PRD (§12.5 excludes it); it was added on
an explicit instruction. These tests cover it as a player meets it.
"""
import datetime as _dt

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rally.core import clock
from rally.core.localtime import DATE_FORMAT, parse_local
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.invitations.api import facade as invitations
from rally.modules.messaging.api import facade as messaging
from rally.modules.profiles.api import facade as profiles
from rally.modules.safety.api import facade as safety

PASSWORD = "longenough"
ME = "me@example.com"
THEM = "them@example.com"
STRANGER = "stranger@example.com"
VENUE = "Rally Courts, F-7"
AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
]


def local_date(day_offset: int) -> str:
    return (timezone.localtime(clock.now()) + _dt.timedelta(days=day_offset)).strftime(DATE_FORMAT)


class MessagePageCase(TestCase):
    def setUp(self):
        profiles.replace_areas(AREAS)
        self.me = self.make_player(ME, "My Name")
        self.them = self.make_player(THEM, "Their Name")
        self.stranger = self.make_player(STRANGER, "Stranger Name")

        sent = invitations.send(
            sender_account_id=self.them,
            recipient_account_id=self.me,
            starts_at=parse_local(local_date(1), "18:00"),
            ends_at=parse_local(local_date(1), "20:00"),
            venue=VENUE,
        )
        assert sent.ok, sent.errors
        accepted = invitations.accept(sent.invitation_id, self.me)
        assert accepted.ok, accepted.error
        self.game_id = accepted.game_id
        self.sign_in(ME)

    def make_player(self, email, name):
        account_id = identity.register(email, PASSWORD).account_id
        assert profiles.save_profile(account_id, name, "intermediate", "isb-f7").ok
        identity.verify_email(identity.get_verification_token(account_id))
        assert availability.add_slot(
            account_id,
            parse_local(local_date(1), "08:00"),
            parse_local(local_date(1), "23:00"),
        ).ok
        return account_id

    def sign_in(self, email):
        self.client.post(reverse("sign_out"))
        self.client.post(reverse("sign_in"), {"email": email, "password": PASSWORD})

    def open_url(self, account_id=None):
        return reverse("conversation_open", kwargs={"account_id": account_id or self.them})

    def thread(self):
        return messaging.open_conversation(self.me, self.them).conversation_id

    def thread_url(self, conversation_id=None):
        return reverse(
            "conversation", kwargs={"conversation_id": conversation_id or self.thread()}
        )


class StartingAConversationTests(MessagePageCase):
    def test_the_games_page_offers_a_message_button(self):
        response = self.client.get(reverse("games"))

        self.assertContains(response, self.open_url())
        self.assertContains(response, "Message Their Name")

    def test_pressing_it_opens_the_thread(self):
        response = self.client.post(self.open_url())

        self.assertEqual(response.status_code, 302)
        self.assertIn("/messages/", response["Location"])

    def test_it_is_not_reachable_by_get(self):
        """FE-9: it may create a conversation."""
        self.assertEqual(self.client.get(self.open_url()).status_code, 405)

    def test_messaging_a_player_with_no_game_is_refused_with_the_reason(self):
        response = self.client.post(
            self.open_url(self.stranger), {"next": reverse("games")}, follow=True
        )

        self.assertContains(response, messaging.NO_CONFIRMED_GAME)

    def test_messaging_yourself_is_a_not_found(self):
        self.assertEqual(self.client.post(self.open_url(self.me)).status_code, 404)

    def test_an_empty_list_explains_itself(self):
        """FE-6."""
        self.assertContains(self.client.get(reverse("conversations")), "no messages")


class TalkingTests(MessagePageCase):
    def test_a_message_is_sent_and_shown(self):
        url = self.thread_url()

        response = self.client.post(url, {"body": "See you at six"}, follow=True)

        self.assertContains(response, "See you at six")

    def test_both_players_see_it(self):
        url = self.thread_url()
        self.client.post(url, {"body": "See you at six"})

        self.sign_in(THEM)
        self.assertContains(self.client.get(url), "See you at six")

    def test_each_message_says_who_said_it(self):
        url = self.thread_url()
        self.client.post(url, {"body": "Mine"})

        self.assertContains(self.client.get(url), "You")

        self.sign_in(THEM)
        self.assertContains(self.client.get(url), "Them")

    def test_an_empty_message_is_refused_with_the_reason(self):
        response = self.client.post(self.thread_url(), {"body": "  "})

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, messaging.BODY_REQUIRED, status_code=400)

    def test_a_refused_message_keeps_what_was_typed(self):
        response = self.client.post(self.thread_url(), {"body": "ring me on 03001234567"})

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "ring me on 03001234567", status_code=400)

    def test_posting_without_a_csrf_token_is_refused(self):
        """FE-9."""
        from django.test import Client

        strict = Client(enforce_csrf_checks=True)
        strict.post(reverse("sign_in"), {"email": ME, "password": PASSWORD})

        response = strict.post(self.thread_url(), {"body": "Hello"})

        self.assertEqual(response.status_code, 403)

    def test_the_thread_appears_in_the_list_with_its_last_line(self):
        self.client.post(self.thread_url(), {"body": "Six o'clock"})

        response = self.client.get(reverse("conversations"))

        self.assertContains(response, "Their Name")
        self.assertContains(response, "Six o&#x27;clock")


class ContactDataIsRefusedTests(MessagePageCase):
    """The guard that keeps ASR-04 intact on this path, as a player meets it."""

    def test_an_email_address_is_refused_with_an_explanation(self):
        response = self.client.post(self.thread_url(), {"body": "write to me@example.com"})

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, messaging.LOOKS_LIKE_CONTACT_DATA, status_code=400)

    def test_a_phone_number_is_refused(self):
        response = self.client.post(self.thread_url(), {"body": "0300 123 4567"})

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, messaging.LOOKS_LIKE_CONTACT_DATA, status_code=400)

    def test_nothing_refused_is_ever_shown_to_the_other_player(self):
        url = self.thread_url()
        self.client.post(url, {"body": "write to me@example.com"})

        self.sign_in(THEM)
        response = self.client.get(url)

        self.assertNotContains(response, "me@example.com")

    def test_the_form_says_so_before_anybody_tries(self):
        self.assertContains(
            self.client.get(self.thread_url()),
            "does not pass on email addresses or phone numbers",
        )

    def test_an_ordinary_arrangement_goes_through(self):
        response = self.client.post(
            self.thread_url(), {"body": "I'll be at court 3 from 6"}, follow=True
        )

        self.assertContains(response, "court 3 from 6")


class OwnerOnlyTests(MessagePageCase):
    """ASR-05."""

    def test_a_stranger_gets_a_not_found(self):
        url = self.thread_url()
        self.sign_in(STRANGER)

        self.assertEqual(self.client.get(url).status_code, 404)

    def test_a_stranger_cannot_post_to_it(self):
        url = self.thread_url()
        self.client.post(url, {"body": "Ours"})
        self.sign_in(STRANGER)

        self.assertEqual(self.client.post(url, {"body": "Butting in"}).status_code, 404)

        self.sign_in(ME)
        self.assertNotContains(self.client.get(url), "Butting in")

    def test_a_thread_that_does_not_exist_gives_the_same_answer(self):
        self.assertEqual(
            self.client.get(reverse("conversation", kwargs={"conversation_id": 999999})).status_code,
            404,
        )

    def test_the_pages_need_a_session_and_are_not_cached(self):
        """FE-3, FE-9."""
        url = self.thread_url()
        self.assertIn("no-store", self.client.get(url)["Cache-Control"])

        self.client.post(reverse("sign_out"))

        for target in (reverse("conversations"), url):
            response = self.client.get(target)
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("sign_in"), response["Location"])

    def test_no_contact_address_appears_on_either_page(self):
        """FE-2."""
        url = self.thread_url()
        self.client.post(url, {"body": "See you there"})

        self.assertNotIn("@", self.client.get(url).content.decode())
        self.assertNotIn("@", self.client.get(reverse("conversations")).content.decode())


class BlockingClosesItTests(MessagePageCase):
    """ASR-10."""

    def test_a_blocked_thread_leaves_the_list(self):
        self.client.post(self.thread_url(), {"body": "Hello"})
        safety.block(self.me, self.them)

        self.assertNotContains(self.client.get(reverse("conversations")), "Their Name")

    def test_the_blocked_player_cannot_post(self):
        url = self.thread_url()
        safety.block(self.me, self.them)
        self.sign_in(THEM)

        response = self.client.post(url, {"body": "Let me in"})

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, messaging.BLOCKED, status_code=400)

    def test_the_games_page_no_longer_offers_it(self):
        safety.block(self.me, self.them)

        response = self.client.post(
            self.open_url(), {"next": reverse("games")}, follow=True
        )

        self.assertContains(response, messaging.BLOCKED)


class TheUnreadBadgeTests(MessagePageCase):
    def test_a_new_message_shows_in_the_header(self):
        url = self.thread_url()
        self.sign_in(THEM)
        self.client.post(url, {"body": "Are we still on?"})

        self.sign_in(ME)
        response = self.client.get(reverse("home"))

        self.assertContains(response, "Messages")
        self.assertContains(response, 'class="badge"')

    def test_reading_the_thread_clears_it(self):
        url = self.thread_url()
        self.sign_in(THEM)
        self.client.post(url, {"body": "Are we still on?"})

        self.sign_in(ME)
        self.client.get(url)

        self.assertEqual(messaging.unread_count(self.me), 0)

    def test_your_own_message_does_not_badge_you(self):
        self.client.post(self.thread_url(), {"body": "Mine"})

        self.assertEqual(messaging.unread_count(self.me), 0)
