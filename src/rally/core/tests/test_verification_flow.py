"""The S2 vertical slice end to end - plan.md S2 AC1, AC3, AC4, AC5.

Platform may read M7's api (it hosts the worker) but never its internals, so the outbox
is inspected through a dispatch run and through M7's own tests.
"""
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from rally.core.pipeline.session import ACCOUNT_ID_KEY
from rally.core.wiring import registry
from rally.modules.identity.api import facade as identity
from rally.modules.notification.api import facade as notification


EMAIL = "newplayer@example.com"
PASSWORD = "longenough"


class WiringTests(TestCase):
    def test_the_outbox_port_is_registered_at_startup(self):
        self.assertIn("OutboxAppender", registry.registered())

    def test_an_unregistered_port_says_where_to_wire_it(self):
        with self.assertRaises(LookupError) as raised:
            registry.resolve("NotAPort")
        self.assertIn("wire it in", str(raised.exception))


class RegistrationDoesNotTouchTheProviderTests(TestCase):
    """AC1 - the web request never contacts the email provider."""

    def setUp(self):
        self.adapter = notification.RecordingEmailAdapter()
        previous = notification.set_email_adapter(self.adapter)
        self.addCleanup(notification.set_email_adapter, previous)

    def test_registering_sends_nothing_and_queues_everything(self):
        response = self.client.post(reverse("register"), {"email": EMAIL, "password": PASSWORD})

        self.assertRedirects(response, reverse("sign_in"))
        self.assertEqual(self.adapter.sent, [], "the request reached the provider")
        self.assertEqual(mail.outbox, [])

        # The event is there, waiting for the worker.
        self.assertEqual(notification.dispatch_due().sent, 1)
        self.assertEqual(len(self.adapter.sent), 1)

    def test_the_message_says_queued_and_never_sent_or_delivered(self):
        response = self.client.post(
            reverse("register"), {"email": EMAIL, "password": PASSWORD}, follow=True
        )

        body = response.content.decode()
        self.assertIn("queued", body)
        self.assertNotIn("delivered", body)


class ProviderDownTests(TestCase):
    """AC4 - with the adapter forced to fail, registration still succeeds."""

    def setUp(self):
        previous = notification.set_email_adapter(notification.AlwaysFailingEmailAdapter())
        self.addCleanup(notification.set_email_adapter, previous)

    def test_registration_succeeds_while_the_provider_is_down(self):
        response = self.client.post(reverse("register"), {"email": EMAIL, "password": PASSWORD})

        self.assertRedirects(response, reverse("sign_in"))
        self.assertTrue(identity.authenticate(EMAIL, PASSWORD).ok)

    def test_the_worker_records_the_failure_without_raising(self):
        self.client.post(reverse("register"), {"email": EMAIL, "password": PASSWORD})

        run = notification.dispatch_due()

        self.assertEqual((run.sent, run.retrying), (0, 1))
        self.assertTrue(identity.authenticate(EMAIL, PASSWORD).ok)

    def test_signing_in_still_works_while_email_is_failing(self):
        self.client.post(reverse("register"), {"email": EMAIL, "password": PASSWORD})
        notification.dispatch_due()

        response = self.client.post(reverse("sign_in"), {"email": EMAIL, "password": PASSWORD})

        self.assertRedirects(response, reverse("home"))


class VerifyEmailPageTests(TestCase):
    """AC3 - the link shows a page, the POST does the work (FE-9)."""

    def setUp(self):
        previous = notification.set_email_adapter(notification.RecordingEmailAdapter())
        self.addCleanup(notification.set_email_adapter, previous)
        self.account_id = identity.register(EMAIL, PASSWORD).account_id
        self.token = identity.get_verification_token(self.account_id)
        self.url = reverse("verify_email", kwargs={"token": self.token})

    def test_the_link_is_reachable_without_a_session(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirm")
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_the_get_changes_nothing(self):
        self.client.get(self.url)
        self.assertFalse(identity.is_verified(self.account_id))

    def test_the_post_verifies_the_account(self):
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "verified")
        self.assertTrue(identity.is_verified(self.account_id))

    def test_verifying_does_not_start_a_session(self):
        self.client.post(self.url)
        self.assertNotIn(ACCOUNT_ID_KEY, self.client.session)

    def test_a_malformed_token_gives_a_clear_message_and_changes_nothing(self):
        response = self.client.get(reverse("verify_email", kwargs={"token": "rubbish"}))

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, identity.VERIFICATION_UNKNOWN_TOKEN, status_code=404)
        self.assertFalse(identity.is_verified(self.account_id))

    def test_a_reused_link_gives_a_clear_message_and_changes_nothing(self):
        self.client.post(self.url)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, identity.VERIFICATION_UNKNOWN_TOKEN, status_code=400)
        self.assertTrue(identity.is_verified(self.account_id))

    def test_the_verification_pages_show_no_contact_address(self):
        for page in (self.client.get(self.url), self.client.post(self.url)):
            self.assertNotIn(EMAIL, page.content.decode())

    def test_no_address_reaches_a_log_line_during_the_whole_flow(self):
        """AC5."""
        with self.assertLogs("rally.operation", level="INFO") as captured:
            self.client.get(self.url)
            self.client.post(self.url)
            notification.dispatch_due()

        written = "\n".join(captured.output)
        self.assertIn("operation=identity.verify_email outcome=verified", written)
        self.assertNotIn(EMAIL, written)
        self.assertNotIn("@", written)
