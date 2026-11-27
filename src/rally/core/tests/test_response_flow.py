"""The S8 vertical slice end to end - plan.md S8 AC1, AC3, and the notification path."""
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
VENUE = "Rally Courts, F-7"
AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
]


def local_date(day_offset: int) -> str:
    return (timezone.localtime(clock.now()) + _dt.timedelta(days=day_offset)).strftime(DATE_FORMAT)


class ResponseFlowCase(TestCase):
    def setUp(self):
        self.adapter = notification.RecordingEmailAdapter()
        previous = notification.set_email_adapter(self.adapter)
        self.addCleanup(notification.set_email_adapter, previous)
        profiles.replace_areas(AREAS)

        self.sender_id = self.make_player(SENDER, "Sender")
        self.recipient_id = self.make_player(RECIPIENT, "Recipient")
        self.invitation_id = invitations.send(
            sender_account_id=self.sender_id,
            recipient_account_id=self.recipient_id,
            starts_at=parse_local(local_date(1), "18:00"),
            ends_at=parse_local(local_date(1), "20:00"),
            venue=VENUE,
        ).invitation_id
        notification.dispatch_due()
        self.adapter.sent.clear()
        self.sign_in(RECIPIENT)

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

    def detail_url(self):
        return reverse("invitation_detail", kwargs={"invitation_id": self.invitation_id})

    def accept(self):
        return self.client.post(
            reverse("invitation_accept", kwargs={"invitation_id": self.invitation_id})
        )

    def decline(self):
        return self.client.post(
            reverse("invitation_decline", kwargs={"invitation_id": self.invitation_id})
        )


class ResponseButtonsTests(ResponseFlowCase):
    """AC1 - only the recipient is offered the choice."""

    def test_the_recipient_sees_accept_and_decline(self):
        response = self.client.get(self.detail_url())

        self.assertContains(response, "Accept")
        self.assertContains(response, "Decline")

    def test_the_sender_is_told_to_wait_instead(self):
        self.sign_in(SENDER)

        response = self.client.get(self.detail_url())

        self.assertContains(response, "Waiting for Recipient")
        self.assertNotContains(response, reverse("invitation_accept", kwargs={"invitation_id": self.invitation_id}))

    def test_accepting_is_not_reachable_by_get(self):
        """FE-9 - state never changes on GET."""
        response = self.client.get(
            reverse("invitation_accept", kwargs={"invitation_id": self.invitation_id})
        )

        self.assertEqual(response.status_code, 405)
        self.assertEqual(
            invitations.get_for_participant(self.invitation_id, self.recipient_id).status,
            "pending",
        )

    def test_declining_is_not_reachable_by_get(self):
        response = self.client.get(
            reverse("invitation_decline", kwargs={"invitation_id": self.invitation_id})
        )
        self.assertEqual(response.status_code, 405)

    def test_the_sender_cannot_accept_their_own_invitation(self):
        self.sign_in(SENDER)

        self.accept()

        self.assertEqual(
            invitations.get_for_participant(self.invitation_id, self.sender_id).status,
            "pending",
        )

    def test_a_non_participant_gets_not_found(self):
        self.make_player("stranger@example.com", "Stranger")
        self.sign_in("stranger@example.com")

        self.assertEqual(self.client.get(self.detail_url()).status_code, 404)


class AcceptFlowTests(ResponseFlowCase):
    def test_accepting_confirms_the_game_and_says_so(self):
        response = self.accept()

        self.assertRedirects(response, self.detail_url())
        page = self.client.get(self.detail_url())
        self.assertContains(page, "Accepted")
        self.assertContains(page, "The game is confirmed")

    def test_the_buttons_are_gone_once_answered(self):
        self.accept()

        page = self.client.get(self.detail_url())

        self.assertNotContains(page, ">Accept<")
        self.assertNotContains(page, ">Decline<")

    def test_declining_records_the_answer_and_creates_no_game(self):
        self.decline()

        page = self.client.get(self.detail_url())
        self.assertContains(page, "Declined")
        self.assertNotContains(page, "The game is confirmed")

    def test_a_refused_accept_shows_the_domain_reason_not_a_database_error(self):
        """AC3."""
        self.decline()

        response = self.client.post(
            reverse("invitation_accept", kwargs={"invitation_id": self.invitation_id}),
            follow=True,
        )

        self.assertContains(response, invitations.NO_LONGER_PENDING)
        self.assertNotContains(response, "IntegrityError")
        self.assertNotContains(response, "constraint")

    def test_an_overlapping_second_game_is_refused_in_the_page(self):
        self.accept()
        other_sender = self.make_player("other@example.com", "Other")
        second = invitations.send(
            sender_account_id=other_sender,
            recipient_account_id=self.recipient_id,
            starts_at=parse_local(local_date(1), "19:00"),
            ends_at=parse_local(local_date(1), "21:00"),
            venue=VENUE,
        ).invitation_id

        response = self.client.post(
            reverse("invitation_accept", kwargs={"invitation_id": second}), follow=True
        )

        self.assertContains(response, invitations.OVERLAPPING_GAME)


class ResponseNotifiesTheSenderTests(ResponseFlowCase):
    """PRD 12.3 - the sender is told when their invitation is answered."""

    def test_accepting_queues_one_notification_for_the_sender(self):
        self.accept()

        self.assertEqual(self.adapter.sent, [], "the request reached the provider")

        run = notification.dispatch_due()

        self.assertEqual((run.claimed, run.sent), (1, 1))
        message = self.adapter.sent[-1]
        self.assertEqual(message["to"], SENDER)
        self.assertIn("accepted", message["subject"])

    def test_declining_queues_one_notification_for_the_sender(self):
        self.decline()
        notification.dispatch_due()

        message = self.adapter.sent[-1]
        self.assertEqual(message["to"], SENDER)
        self.assertIn("declined", message["subject"])

    def test_the_email_copies_no_detail_of_the_game(self):
        self.accept()
        notification.dispatch_due()

        body = self.adapter.sent[-1]["body"]
        self.assertIn(reverse("invitations"), body)
        self.assertNotIn(VENUE, body)
        self.assertNotIn("18:00", body)

    def test_a_refused_response_queues_nothing(self):
        self.decline()
        notification.dispatch_due()
        self.adapter.sent.clear()

        self.accept()  # refused: no longer pending

        self.assertEqual(notification.dispatch_due().claimed, 0)

    def test_no_contact_address_reaches_a_log_line(self):
        with self.assertLogs("rally.operation", level="INFO") as captured:
            self.accept()
            notification.dispatch_due()

        written = "\n".join(captured.output)
        self.assertIn("operation=invitation.accept outcome=accepted", written)
        self.assertNotIn("@", written)
