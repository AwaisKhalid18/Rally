"""The S9 vertical slice end to end - plan.md S9 AC1, AC2, AC3."""
import datetime as _dt
from io import StringIO

from django.core.management import call_command
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


class LifecycleFlowCase(TestCase):
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

    def detail_url(self):
        return reverse("invitation_detail", kwargs={"invitation_id": self.invitation_id})

    def cancel(self):
        return self.client.post(
            reverse("invitation_cancel", kwargs={"invitation_id": self.invitation_id})
        )

    def status(self):
        return invitations.get_for_participant(self.invitation_id, self.sender_id).status


class CancelButtonTests(LifecycleFlowCase):
    """AC1 - only the sender is offered it."""

    def test_the_sender_sees_a_cancel_button_and_the_deadline(self):
        response = self.client.get(self.detail_url())

        self.assertContains(response, "Cancel this invitation")
        self.assertContains(response, "It expires on")

    def test_the_recipient_is_not_offered_it(self):
        self.sign_in(RECIPIENT)

        response = self.client.get(self.detail_url())

        self.assertNotContains(
            response, reverse("invitation_cancel", kwargs={"invitation_id": self.invitation_id})
        )

    def test_cancelling_is_not_reachable_by_get(self):
        """FE-9."""
        response = self.client.get(
            reverse("invitation_cancel", kwargs={"invitation_id": self.invitation_id})
        )

        self.assertEqual(response.status_code, 405)
        self.assertEqual(self.status(), "pending")

    def test_the_recipient_cannot_cancel_by_posting_directly(self):
        self.sign_in(RECIPIENT)

        self.client.post(
            reverse("invitation_cancel", kwargs={"invitation_id": self.invitation_id})
        )

        self.assertEqual(self.status(), "pending")


class CancelFlowTests(LifecycleFlowCase):
    def test_cancelling_records_it_and_says_so(self):
        response = self.cancel()

        self.assertRedirects(response, self.detail_url())
        page = self.client.get(self.detail_url())
        self.assertContains(page, "Cancelled")
        self.assertNotContains(page, "Cancel this invitation")

    def test_the_recipient_can_no_longer_accept_it(self):
        self.cancel()
        self.sign_in(RECIPIENT)

        response = self.client.post(
            reverse("invitation_accept", kwargs={"invitation_id": self.invitation_id}),
            follow=True,
        )

        self.assertContains(response, invitations.NO_LONGER_PENDING)

    def test_a_refused_cancel_shows_the_domain_reason(self):
        self.sign_in(RECIPIENT)
        self.client.post(reverse("invitation_decline", kwargs={"invitation_id": self.invitation_id}))
        self.sign_in(SENDER)

        response = self.cancel()

        self.assertRedirects(response, self.detail_url())
        self.assertContains(self.client.get(self.detail_url()), "Declined")

    def test_the_recipient_is_notified(self):
        """PRD 12.3."""
        self.cancel()

        self.assertEqual(self.adapter.sent, [], "the request reached the provider")
        run = notification.dispatch_due()

        self.assertEqual((run.claimed, run.sent), (1, 1))
        message = self.adapter.sent[-1]
        self.assertEqual(message["to"], RECIPIENT)
        self.assertIn("cancelled", message["subject"])
        self.assertNotIn(VENUE, message["body"])

    def test_no_contact_address_reaches_a_log_line(self):
        with self.assertLogs("rally.operation", level="INFO") as captured:
            self.cancel()
            notification.dispatch_due()

        written = "\n".join(captured.output)
        self.assertIn("operation=invitation.cancel outcome=cancelled", written)
        self.assertNotIn("@", written)


class ExpiryOnThePageTests(LifecycleFlowCase):
    """AC2 and AC3 as a player experiences them."""

    def _expire(self):
        from rally.modules.invitations.internal.models import Invitation

        Invitation.objects.filter(pk=self.invitation_id).update(
            expires_at=clock.now() - _dt.timedelta(minutes=1)
        )

    def test_the_recipient_cannot_accept_an_expired_invitation(self):
        self._expire()
        self.sign_in(RECIPIENT)

        response = self.client.post(
            reverse("invitation_accept", kwargs={"invitation_id": self.invitation_id}),
            follow=True,
        )

        self.assertContains(response, invitations.HAS_EXPIRED)

    def test_that_holds_even_though_the_worker_never_ran(self):
        """AC2 - the stored status is still Pending and it still cannot be accepted."""
        self._expire()

        self.assertEqual(self.status(), "pending")

        self.sign_in(RECIPIENT)
        self.client.post(reverse("invitation_accept", kwargs={"invitation_id": self.invitation_id}))

        self.sign_in(SENDER)
        self.assertEqual(self.status(), "pending")

    def test_the_worker_then_refreshes_what_is_displayed(self):
        """AC3 - and tells nobody."""
        self._expire()

        out = StringIO()
        call_command("run_worker", "--once", stdout=out)

        self.assertIn("invitations_expired=1", out.getvalue())
        self.assertEqual(self.status(), "expired")
        self.assertContains(self.client.get(self.detail_url()), "Expired")

    def test_expiry_notifies_nobody(self):
        """PRD 12.3 sends no reminders and no expiry notice."""
        self._expire()
        call_command("run_worker", "--once", stdout=StringIO())

        self.assertEqual(self.adapter.sent, [])
        self.assertEqual(notification.dispatch_due().claimed, 0)

    def test_the_worker_leaves_a_live_invitation_alone(self):
        out = StringIO()
        call_command("run_worker", "--once", stdout=out)

        self.assertNotIn("invitations_expired=1", out.getvalue())
        self.assertEqual(self.status(), "pending")
