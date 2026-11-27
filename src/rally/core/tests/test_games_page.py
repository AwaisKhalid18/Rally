"""The S11 vertical slice end to end - plan.md S11 AC1, AC2, AC3, AC4."""
import datetime as _dt

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rally.core import clock
from rally.core.localtime import DATE_FORMAT, parse_local
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.invitations.api import facade as invitations
from rally.modules.notification.api import facade as notification
from rally.modules.profiles.api import facade as profiles

PASSWORD = "longenough"
SENDER = "sender@example.com"
RECIPIENT = "recipient@example.com"
STRANGER = "stranger@example.com"
VENUE = "Rally Courts, F-7"
AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
]


def local_date(day_offset: int) -> str:
    return (timezone.localtime(clock.now()) + _dt.timedelta(days=day_offset)).strftime(DATE_FORMAT)


class GamePageCase(TestCase):
    def setUp(self):
        self.adapter = notification.RecordingEmailAdapter()
        previous = notification.set_email_adapter(self.adapter)
        self.addCleanup(notification.set_email_adapter, previous)
        profiles.replace_areas(AREAS)

        self.sender_id = self.make_player(SENDER, "Sender Name")
        self.recipient_id = self.make_player(RECIPIENT, "Recipient Name")
        self.stranger_id = self.make_player(STRANGER, "Stranger Name")
        self.invitation_id = invitations.send(
            sender_account_id=self.sender_id,
            recipient_account_id=self.recipient_id,
            starts_at=parse_local(local_date(1), "18:00"),
            ends_at=parse_local(local_date(1), "20:00"),
            venue=VENUE,
        ).invitation_id
        self.game_id = invitations.accept(self.invitation_id, self.recipient_id).game_id

        notification.mark_all_read(self.sender_id)
        notification.mark_all_read(self.recipient_id)
        self.adapter.sent.clear()
        self.sign_in(SENDER)

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

    def games_page(self):
        return self.client.get(reverse("games"))

    def cancel_url(self):
        return reverse("game_cancel", kwargs={"game_id": self.game_id})

    def freeze(self, when):
        previous = clock.set_clock(clock.FrozenClock(when))
        self.addCleanup(clock.set_clock, previous)


class BothPlayersSeeItTests(GamePageCase):
    """AC1."""

    def test_the_sender_sees_the_game_with_the_other_players_name(self):
        response = self.games_page()

        self.assertContains(response, "Recipient Name")
        self.assertContains(response, VENUE)
        self.assertContains(response, "Confirmed")

    def test_the_recipient_sees_the_same_game(self):
        self.sign_in(RECIPIENT)

        response = self.games_page()

        self.assertContains(response, "Sender Name")
        self.assertContains(response, VENUE)

    def test_a_player_in_no_game_is_told_so_rather_than_shown_a_blank(self):
        """FE-6."""
        self.sign_in(STRANGER)

        self.assertContains(self.games_page(), "no upcoming games")

    def test_no_contact_address_appears_on_the_page(self):
        """FE-2, rule 6: acceptance shares nothing private (PRD 12.2)."""
        self.assertNotIn("@", self.games_page().content.decode())

    def test_the_page_needs_a_session_and_is_not_cached(self):
        """FE-3, FE-9."""
        self.assertIn("no-store", self.games_page()["Cache-Control"])

        self.client.post(reverse("sign_out"))
        response = self.client.get(reverse("games"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("sign_in"), response["Location"])


class TheConfirmationStepTests(GamePageCase):
    """AC2 - 'an explicit confirmation step but no reason' (PRD 12.4)."""

    def test_the_games_page_offers_cancelling(self):
        self.assertContains(self.games_page(), self.cancel_url())

    def test_the_link_leads_to_a_question_not_to_a_cancellation(self):
        """FE-9 - a GET changes nothing."""
        response = self.client.get(self.cancel_url())

        self.assertContains(response, "Cancel this game?")
        self.assertContains(response, "Yes, cancel the game")
        self.assertContains(response, "No, keep it")
        detail = invitations.get_game_for_participant(self.game_id, self.sender_id)
        self.assertFalse(detail.is_cancelled, "the GET cancelled the game")

    def test_the_question_asks_for_no_reason(self):
        self.assertContains(self.client.get(self.cancel_url()), "do not\nhave to give a reason")

    def test_a_stranger_gets_a_not_found_for_the_question(self):
        """ASR-05."""
        self.sign_in(STRANGER)

        self.assertEqual(self.client.get(self.cancel_url()).status_code, 404)

    def test_a_stranger_posting_directly_gets_a_not_found_and_changes_nothing(self):
        self.sign_in(STRANGER)

        self.assertEqual(self.client.post(self.cancel_url()).status_code, 404)

        detail = invitations.get_game_for_participant(self.game_id, self.sender_id)
        self.assertFalse(detail.is_cancelled)


class CancellingThroughThePageTests(GamePageCase):
    """AC2 and AC3."""

    def test_confirming_cancels_it_and_says_so_after_the_commit(self):
        response = self.client.post(self.cancel_url(), follow=True)

        self.assertContains(response, "The game is cancelled")
        self.assertContains(response, "Cancelled")
        self.assertContains(response, "You cancelled this game.")

    def test_the_other_player_sees_who_cancelled_it(self):
        self.client.post(self.cancel_url())
        self.sign_in(RECIPIENT)

        self.assertContains(self.games_page(), "The other player cancelled this game.")

    def test_it_is_no_longer_offered_afterwards(self):
        self.client.post(self.cancel_url())

        self.assertNotContains(self.games_page(), self.cancel_url())

    def test_the_invitation_is_still_accepted(self):
        """AC3 - cancelling a game is not un-accepting an invitation."""
        self.client.post(self.cancel_url())

        detail_url = reverse("invitation_detail", kwargs={"invitation_id": self.invitation_id})
        response = self.client.get(detail_url)

        self.assertContains(response, "Accepted")
        self.assertContains(response, "This game was cancelled.")

    def test_the_freed_time_can_be_used_for_a_new_game(self):
        """AC3, G-10 - asserted by actually using the time."""
        self.client.post(self.cancel_url())
        self.sign_in(STRANGER)
        new_invitation = self.client.post(
            reverse("invitation_new", kwargs={"account_id": self.recipient_id}),
            {
                "date": local_date(1),
                "start": "19:00",
                "end": "21:00",
                "venue": VENUE,
            },
        )
        self.assertEqual(new_invitation.status_code, 302, "the invitation was refused")

        self.sign_in(RECIPIENT)
        _, received = invitations.list_for_player(self.recipient_id)
        pending = [row for row in received if row.status == "pending"]
        result = invitations.accept(pending[0].invitation_id, self.recipient_id)

        self.assertTrue(result.ok, result.error)

    def test_cancelling_after_the_start_is_refused_with_the_reason(self):
        """AC2 - and the page says which reason, not a generic failure."""
        self.freeze(parse_local(local_date(1), "18:00"))

        response = self.client.post(self.cancel_url(), follow=True)

        self.assertContains(response, invitations.ALREADY_STARTED)

    def test_a_started_game_is_not_offered_for_cancelling(self):
        self.freeze(parse_local(local_date(1), "19:00"))

        response = self.games_page()

        self.assertNotContains(response, self.cancel_url())

    def test_the_second_player_to_confirm_is_told_it_is_already_cancelled(self):
        self.client.post(self.cancel_url())
        self.sign_in(RECIPIENT)

        response = self.client.post(self.cancel_url(), follow=True)

        self.assertContains(response, invitations.ALREADY_CANCELLED)


class TheOtherPlayerIsNotifiedTests(GamePageCase):
    """AC4 - in-app and email, through the S10 path."""

    def test_the_other_player_has_it_in_their_inbox_at_once(self):
        self.client.post(self.cancel_url())

        self.assertEqual(self.adapter.sent, [], "the request reached the provider")
        items = notification.list_for_player(self.recipient_id)

        self.assertEqual(items[0].notification_type, "game.cancelled")
        self.assertEqual(items[0].game_id, self.game_id)

    def test_it_reads_as_a_cancelled_game_and_links_to_the_games_page(self):
        self.client.post(self.cancel_url())
        self.sign_in(RECIPIENT)

        response = self.client.get(reverse("notifications"))

        self.assertContains(response, "A confirmed game was cancelled by the other player")
        self.assertContains(response, "That time is free again")
        self.assertContains(response, reverse("games"))

    def test_the_player_who_cancelled_is_not_notified(self):
        self.client.post(self.cancel_url())

        types = [item.notification_type for item in notification.list_for_player(self.sender_id)]

        self.assertNotIn("game.cancelled", types)

    def test_the_email_goes_out_through_the_worker(self):
        self.client.post(self.cancel_url())

        self.assertEqual(self.adapter.sent, [], "the request itself reached the provider")
        # Everything queued earlier in the fixture is dispatched too, so the
        # cancellation's message is picked out rather than counted.
        notification.dispatch_due()

        matching = [m for m in self.adapter.sent if "game was cancelled" in m["subject"]]

        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["to"], RECIPIENT)
        self.assertNotIn(
            VENUE, matching[0]["body"], "the email is a nudge, not a copy (ASR-11)"
        )

    def test_cancelling_still_succeeds_with_the_provider_down(self):
        """AC4, ASR-12."""
        previous = notification.set_email_adapter(notification.AlwaysFailingEmailAdapter())
        self.addCleanup(notification.set_email_adapter, previous)

        response = self.client.post(self.cancel_url(), follow=True)

        self.assertContains(response, "The game is cancelled")
        detail = invitations.get_game_for_participant(self.game_id, self.sender_id)
        self.assertTrue(detail.is_cancelled)
        self.assertEqual(
            notification.list_for_player(self.recipient_id)[0].notification_type,
            "game.cancelled",
            "the in-app half survived the outage",
        )

    def test_no_contact_address_reaches_a_log_line(self):
        """Rule 6."""
        with self.assertLogs("rally.operation", level="INFO") as captured:
            self.client.post(self.cancel_url())
            notification.dispatch_due()

        written = "\n".join(captured.output)
        self.assertIn("operation=game.cancel outcome=cancelled", written)
        self.assertNotIn("@", written)

    def test_a_refused_cancellation_notifies_nobody(self):
        self.freeze(parse_local(local_date(1), "18:00"))

        self.client.post(self.cancel_url())

        types = [
            item.notification_type for item in notification.list_for_player(self.recipient_id)
        ]
        self.assertNotIn("game.cancelled", types)
