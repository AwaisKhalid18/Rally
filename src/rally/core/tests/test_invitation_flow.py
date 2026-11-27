"""The S7 vertical slice end to end - plan.md S7 AC1, AC4, AC5, AC6."""
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


class InvitationFlowCase(TestCase):
    def setUp(self):
        self.adapter = notification.RecordingEmailAdapter()
        previous = notification.set_email_adapter(self.adapter)
        self.addCleanup(notification.set_email_adapter, previous)
        profiles.replace_areas(AREAS)

        self.sender_id = self.make_player(SENDER, "Sender")
        self.recipient_id = self.make_player(RECIPIENT, "Recipient", slot=("17:00", "21:00"))
        # Registering queued a verification email for each player. Drain the outbox so a
        # later assertion counts only what the invitation itself produced.
        notification.dispatch_due()
        self.adapter.sent.clear()
        self.sign_in(SENDER)

    def make_player(self, email, name, verified=True, slot=None):
        account_id = identity.register(email, PASSWORD).account_id
        saved = profiles.save_profile(account_id, name, "intermediate", "isb-f7")
        assert saved.ok, saved.errors
        if verified:
            identity.verify_email(identity.get_verification_token(account_id))
        if slot:
            start, end = slot
            assert availability.add_slot(
                account_id, parse_local(local_date(1), start), parse_local(local_date(1), end)
            ).ok
        return account_id

    def sign_in(self, email):
        self.client.post(reverse("sign_out"))
        self.client.post(reverse("sign_in"), {"email": email, "password": PASSWORD})

    def invite(self, **overrides):
        payload = {
            "date": local_date(1),
            "start": "18:00",
            "end": "20:00",
            "venue": VENUE,
        }
        payload.update(overrides)
        return self.client.post(
            reverse("invitation_new", kwargs={"account_id": self.recipient_id}), payload
        )


class InviteFormTests(InvitationFlowCase):
    """AC1."""

    def test_the_form_needs_a_session(self):
        self.client.post(reverse("sign_out"))

        response = self.client.get(
            reverse("invitation_new", kwargs={"account_id": self.recipient_id})
        )

        self.assertEqual(response.status_code, 302)

    def test_the_form_names_the_player_being_invited(self):
        response = self.client.get(
            reverse("invitation_new", kwargs={"account_id": self.recipient_id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recipient")
        self.assertContains(response, "Venue")

    def test_inviting_yourself_is_not_a_page(self):
        response = self.client.get(
            reverse("invitation_new", kwargs={"account_id": self.sender_id})
        )
        self.assertEqual(response.status_code, 404)

    def test_inviting_a_player_who_does_not_exist_is_not_a_page(self):
        response = self.client.get(reverse("invitation_new", kwargs={"account_id": 999999}))
        self.assertEqual(response.status_code, 404)

    def test_a_search_result_links_to_the_invite_form(self):
        response = self.client.get(
            reverse("search"),
            {"date": local_date(1), "start": "18:00", "end": "20:00", "area_code": "isb-f7"},
        )

        self.assertContains(
            response, reverse("invitation_new", kwargs={"account_id": self.recipient_id})
        )

    def test_every_field_is_required(self):
        response = self.invite(venue="")

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, invitations.VENUE_REQUIRED, status_code=400)

    def test_a_rejected_invitation_keeps_what_was_typed(self):
        response = self.invite(start="20:00", end="18:00")

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, invitations.END_BEFORE_START, status_code=400)
        self.assertContains(response, VENUE, status_code=400)


class SuccessIsReportedOnlyAfterCommitTests(InvitationFlowCase):
    """AC4."""

    def test_a_sent_invitation_redirects_with_a_success_message(self):
        response = self.invite()

        self.assertRedirects(response, reverse("invitations"))
        sent, _ = invitations.list_for_player(self.sender_id)
        self.assertEqual(len(sent), 1)

    def test_the_success_message_appears_only_once_the_invitation_exists(self):
        response = self.client.post(
            reverse("invitation_new", kwargs={"account_id": self.recipient_id}),
            {"date": local_date(1), "start": "18:00", "end": "20:00", "venue": VENUE},
            follow=True,
        )

        self.assertContains(response, "Your invitation is sent")
        self.assertEqual(len(invitations.list_for_player(self.sender_id)[0]), 1)

    def test_a_refused_invitation_never_claims_success(self):
        response = self.invite(venue="")

        body = response.content.decode()
        self.assertNotIn("Your invitation is sent", body)
        self.assertEqual(invitations.list_for_player(self.sender_id)[0], [])


class OutboxTests(InvitationFlowCase):
    """AC6 - the event is committed with the invitation and the request sends nothing.

    Platform hosts the worker, so this is where what reaches the outbox is asserted;
    M5 must not import M7 (rule 3).
    """

    def test_sending_queues_one_notification_and_contacts_nobody(self):
        self.invite()

        self.assertEqual(self.adapter.sent, [], "the web request reached the provider")

        run = notification.dispatch_due()

        self.assertEqual((run.claimed, run.sent), (1, 1))
        self.assertEqual(self.adapter.sent[-1]["to"], RECIPIENT)

    def test_a_refused_invitation_queues_nothing(self):
        self.invite(venue="")

        self.assertEqual(notification.dispatch_due().claimed, 0)

    def test_the_email_points_at_the_in_app_record_and_copies_no_detail(self):
        """ASR-11 - the in-app invitation is the source of truth, not the email."""
        self.invite()
        notification.dispatch_due()

        message = self.adapter.sent[-1]
        self.assertIn(reverse("invitations"), message["body"])
        self.assertNotIn(VENUE, message["body"])
        self.assertNotIn("18:00", message["body"])

    def test_no_contact_address_reaches_a_log_line(self):
        with self.assertLogs("rally.operation", level="INFO") as captured:
            self.invite()
            notification.dispatch_due()

        written = "\n".join(captured.output)
        self.assertIn("operation=invitation.send outcome=sent", written)
        self.assertNotIn("@", written)


class InvitationListTests(InvitationFlowCase):
    """AC5."""

    def setUp(self):
        super().setUp()
        self.invite()
        self.invitation_id = invitations.list_for_player(self.sender_id)[0][0].invitation_id

    def test_the_sender_sees_it_under_sent(self):
        response = self.client.get(reverse("invitations"))

        self.assertContains(response, "Recipient")
        self.assertContains(response, "Pending")
        self.assertContains(response, VENUE)

    def test_the_recipient_sees_it_under_received(self):
        self.sign_in(RECIPIENT)

        response = self.client.get(reverse("invitations"))

        self.assertContains(response, "Sender")
        self.assertContains(response, "Pending")

    def test_an_empty_list_says_why(self):
        stranger = self.make_player("stranger@example.com", "Stranger")
        self.sign_in("stranger@example.com")

        response = self.client.get(reverse("invitations"))

        self.assertContains(response, "No one has invited you yet")
        self.assertContains(response, "You have not sent an invitation yet")

    def test_the_other_party_is_shown_by_display_name_only(self):
        identity.set_phone(self.recipient_id, "03001234567")

        body = self.client.get(reverse("invitations")).content.decode()

        self.assertIn("Recipient", body)
        self.assertNotIn(RECIPIENT, body)
        self.assertNotIn("@", body)
        self.assertNotIn("03001234567", body)

    def test_a_participant_can_open_the_detail(self):
        response = self.client.get(
            reverse("invitation_detail", kwargs={"invitation_id": self.invitation_id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, VENUE)
        self.assertContains(response, "Pending")

    def test_a_non_participant_gets_not_found(self):
        self.make_player("stranger@example.com", "Stranger")
        self.sign_in("stranger@example.com")

        response = self.client.get(
            reverse("invitation_detail", kwargs={"invitation_id": self.invitation_id})
        )

        self.assertEqual(response.status_code, 404)

    def test_the_detail_needs_a_session(self):
        self.client.post(reverse("sign_out"))

        response = self.client.get(
            reverse("invitation_detail", kwargs={"invitation_id": self.invitation_id})
        )

        self.assertEqual(response.status_code, 302)

    def test_the_detail_shows_when_the_invitation_expires(self):
        response = self.client.get(
            reverse("invitation_detail", kwargs={"invitation_id": self.invitation_id})
        )

        self.assertContains(response, "Expires")
