"""The S10 vertical slice end to end - plan.md S10 AC1, AC2, AC3, AC4."""
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


class NotificationPageCase(TestCase):
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
        # Everything registration and sending produced is already read: each test is
        # about the notification its own action creates.
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

    def page(self):
        return self.client.get(reverse("notifications"))

    def answer(self, action):
        self.sign_in(RECIPIENT)
        self.client.post(reverse(action, kwargs={"invitation_id": self.invitation_id}))
        self.sign_in(SENDER)


class TheSenderIsToldTests(NotificationPageCase):
    """AC1 and AC2 - the sender learns the recipient's answer, in app."""

    def test_an_acceptance_appears_on_the_senders_page(self):
        self.answer("invitation_accept")

        response = self.page()

        self.assertContains(response, "was accepted")
        self.assertContains(response, "Unread")

    def test_a_decline_appears_on_the_senders_page(self):
        self.answer("invitation_decline")

        self.assertContains(self.page(), "was declined")

    def test_the_recipient_is_told_when_the_sender_cancels(self):
        self.client.post(reverse("invitation_cancel", kwargs={"invitation_id": self.invitation_id}))
        self.sign_in(RECIPIENT)

        self.assertContains(self.page(), "was cancelled by the player who sent it")

    def test_the_notification_links_to_the_invitation_it_is_about(self):
        self.answer("invitation_accept")

        self.assertContains(
            self.page(),
            reverse("invitation_detail", kwargs={"invitation_id": self.invitation_id}),
        )

    def test_the_recipient_does_not_see_the_senders_notification(self):
        """ASR-04 - one player's page never shows another's."""
        self.answer("invitation_accept")
        self.sign_in(RECIPIENT)

        self.assertNotContains(self.page(), "was accepted")

    def test_an_empty_inbox_says_so_rather_than_showing_nothing(self):
        """FE-6 - a reason, not a blank page.

        Rendered directly: every real player has at least a verification notification,
        so the empty branch cannot be reached through a request.
        """
        from django.template.loader import render_to_string

        page = render_to_string("notifications.html", {"notifications": [], "unread_count": 0})

        self.assertIn("no notifications yet", page)


class ItIsThereWithoutTheWorkerTests(NotificationPageCase):
    """AC2 - 'the email goes through the worker only'; the page does not wait for it."""

    def test_the_page_is_complete_before_anything_is_dispatched(self):
        self.answer("invitation_accept")

        self.assertEqual(self.adapter.sent, [], "precondition: the worker has not run")
        self.assertContains(self.page(), "was accepted")

    def test_the_header_counts_the_unread_one(self):
        self.answer("invitation_accept")

        self.assertContains(self.client.get(reverse("home")), 'class="badge"')


class EmailStatusOnThePageTests(NotificationPageCase):
    """AC3 - queued, sent or failed; never 'delivered'."""

    def test_it_reads_queued_before_the_worker_runs(self):
        self.answer("invitation_accept")

        response = self.page()

        self.assertContains(response, "Email queued")
        self.assertNotContains(response, "delivered")

    def test_it_reads_sent_once_the_provider_has_accepted_it(self):
        self.answer("invitation_accept")

        notification.dispatch_due()

        response = self.page()
        self.assertContains(response, "Email sent")
        self.assertNotContains(response, "delivered")

    def test_it_reads_failed_once_the_retries_run_out(self):
        """The retries are driven by moving the clock, not by touching M7's tables
        (rule 2): attempts fall 5 minutes apart and the window closes at 15."""
        self.answer("invitation_accept")
        previous_adapter = notification.set_email_adapter(notification.AlwaysFailingEmailAdapter())
        self.addCleanup(notification.set_email_adapter, previous_adapter)
        start = clock.now()

        for attempt in range(notification.MAX_ATTEMPTS):
            previous_clock = clock.set_clock(
                clock.FrozenClock(start + attempt * notification.RETRY_INTERVAL + _dt.timedelta(minutes=1))
            )
            self.addCleanup(clock.set_clock, previous_clock)
            notification.dispatch_due()

        response = self.page()
        self.assertContains(response, "could not be sent")
        self.assertContains(response, "was accepted", msg_prefix="the in-app half survived")


class MarkingReadTests(NotificationPageCase):
    """AC2 - read/unread, through the page."""

    def test_marking_one_read_removes_the_unread_flag(self):
        self.answer("invitation_accept")
        # Newest first: the acceptance. The sender also still has their own
        # verification notification, which is why this is not the only row.
        item = notification.list_for_player(self.sender_id)[0]

        response = self.client.post(
            reverse("notification_read", kwargs={"notification_id": item.notification_id})
        )

        self.assertRedirects(response, reverse("notifications"))
        self.assertNotContains(self.page(), "Unread")

    def test_marking_all_read_says_how_many(self):
        self.answer("invitation_accept")

        response = self.client.post(reverse("notifications_read_all"), follow=True)

        self.assertContains(response, "Marked 1 notification(s) as read")
        self.assertEqual(notification.unread_count(self.sender_id), 0)

    def test_marking_read_is_not_reachable_by_get(self):
        """FE-9 - state changes are POST with CSRF."""
        self.answer("invitation_accept")
        # Newest first: the acceptance. The sender also still has their own
        # verification notification, which is why this is not the only row.
        item = notification.list_for_player(self.sender_id)[0]

        response = self.client.get(
            reverse("notification_read", kwargs={"notification_id": item.notification_id})
        )

        self.assertEqual(response.status_code, 405)
        self.assertEqual(notification.unread_count(self.sender_id), 1)

    def test_another_player_cannot_mark_it_read_by_posting_directly(self):
        self.answer("invitation_accept")
        # Newest first: the acceptance. The sender also still has their own
        # verification notification, which is why this is not the only row.
        item = notification.list_for_player(self.sender_id)[0]
        self.sign_in(RECIPIENT)

        self.client.post(
            reverse("notification_read", kwargs={"notification_id": item.notification_id})
        )

        self.assertEqual(notification.unread_count(self.sender_id), 1)


class PrivacyAndResilienceTests(NotificationPageCase):
    """AC4 - a dead provider costs nothing, and no address is anywhere."""

    def test_accepting_still_succeeds_with_the_provider_down(self):
        failing = notification.AlwaysFailingEmailAdapter()
        previous = notification.set_email_adapter(failing)
        self.addCleanup(notification.set_email_adapter, previous)

        self.answer("invitation_accept")

        record = invitations.get_for_participant(self.invitation_id, self.sender_id)
        self.assertEqual(record.status, "accepted")
        self.assertContains(self.page(), "was accepted")

    def test_cancelling_still_succeeds_with_the_provider_down(self):
        previous = notification.set_email_adapter(notification.AlwaysFailingEmailAdapter())
        self.addCleanup(notification.set_email_adapter, previous)

        self.client.post(reverse("invitation_cancel", kwargs={"invitation_id": self.invitation_id}))

        record = invitations.get_for_participant(self.invitation_id, self.sender_id)
        self.assertEqual(record.status, "cancelled")

    def test_no_contact_address_is_rendered_on_the_page(self):
        """FE-2."""
        self.answer("invitation_accept")
        notification.dispatch_due()

        body = self.page().content.decode()

        self.assertNotIn("@", body)

    def test_no_contact_address_reaches_a_log_line(self):
        with self.assertLogs("rally.operation", level="INFO") as captured:
            self.answer("invitation_accept")
            notification.dispatch_due()
            self.page()

        written = "\n".join(captured.output)
        self.assertIn("operation=notification.email outcome=sent", written)
        self.assertNotIn("@", written)

    def test_the_page_needs_a_session(self):
        """FE-3 - it is not one of the three public routes."""
        self.client.post(reverse("sign_out"))

        response = self.client.get(reverse("notifications"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("sign_in"), response["Location"])

    def test_the_page_is_never_cached(self):
        """FE-9."""
        self.assertIn("no-store", self.page()["Cache-Control"])
