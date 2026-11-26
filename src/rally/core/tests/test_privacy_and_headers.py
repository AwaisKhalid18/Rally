"""AC5 - CSRF, no-store, and no contact address in a log line or a rendered page.

Covers binding rule 6 and FE-2, FE-9.
"""
from django.test import Client, TestCase
from django.urls import reverse

from rally.modules.identity.api import facade as identity

EMAIL = "private@example.com"
PASSWORD = "longenough"


class CsrfTests(TestCase):
    """FE-9 - a state-changing request without a token is rejected."""

    def setUp(self):
        self.strict = Client(enforce_csrf_checks=True)

    def test_register_without_a_token_is_rejected(self):
        response = self.strict.post(reverse("register"), {"email": EMAIL, "password": PASSWORD})
        self.assertEqual(response.status_code, 403)

    def test_sign_in_without_a_token_is_rejected(self):
        identity.register(EMAIL, PASSWORD)
        response = self.strict.post(reverse("sign_in"), {"email": EMAIL, "password": PASSWORD})
        self.assertEqual(response.status_code, 403)

    def test_the_form_carries_a_token_so_the_flow_works_with_csrf_enforced(self):
        self.strict.get(reverse("register"))
        token = self.strict.cookies["csrftoken"].value
        response = self.strict.post(
            reverse("register"),
            {"email": EMAIL, "password": PASSWORD, "csrfmiddlewaretoken": token},
        )
        self.assertEqual(response.status_code, 302)


class CacheHeaderTests(TestCase):
    def setUp(self):
        identity.register(EMAIL, PASSWORD)

    def test_an_authenticated_page_is_never_stored(self):
        self.client.post(reverse("sign_in"), {"email": EMAIL, "password": PASSWORD})

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_a_public_page_does_not_claim_a_viewer(self):
        response = self.client.get(reverse("sign_in"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Cache-Control", response.headers)


class ContactDataNeverLeavesM1Tests(TestCase):
    """Rule 6 - email appears in no log line and on no rendered page."""

    def test_no_email_is_written_to_the_operation_log(self):
        with self.assertLogs("rally.operation", level="INFO") as captured:
            self.client.post(reverse("register"), {"email": EMAIL, "password": PASSWORD})
            self.client.post(reverse("sign_in"), {"email": EMAIL, "password": PASSWORD})
            self.client.post(reverse("sign_in"), {"email": EMAIL, "password": "wrong-one"})
            self.client.post(reverse("sign_out"))

        written = "\n".join(captured.output)
        self.assertNotIn(EMAIL, written)
        self.assertNotIn("@", written)
        self.assertIn("operation=identity.register outcome=created", written)

    def test_the_log_helper_refuses_anything_that_looks_like_an_address(self):
        from rally.core.logging import log_operation

        with self.assertLogs("rally.operation", level="INFO") as captured:
            log_operation("test", "ok", slipped=EMAIL)

        self.assertNotIn(EMAIL, captured.output[0])
        self.assertIn("<redacted>", captured.output[0])

    def test_the_signed_in_pages_show_no_contact_address(self):
        identity.register(EMAIL, PASSWORD)
        self.client.post(reverse("sign_in"), {"email": EMAIL, "password": PASSWORD})

        body = self.client.get(reverse("home")).content.decode()

        self.assertNotIn(EMAIL, body)
        self.assertNotIn("private@", body)

    def test_the_viewer_view_model_carries_only_public_facts(self):
        from rally.core.shapers.identity import viewer_view

        account_id = identity.register(EMAIL, PASSWORD).account_id
        view = viewer_view(identity.account_summary(account_id))

        self.assertEqual(set(vars(view)), {"account_id", "is_verified"})
        self.assertEqual(view.verification_notice, "Your email address is not verified yet.")


class ClockTests(TestCase):
    """Rule 8 - one server clock, always UTC."""

    def test_the_clock_is_timezone_aware_and_utc(self):
        from datetime import timezone

        from rally.core import clock

        self.assertEqual(clock.now().utcoffset(), timezone.utc.utcoffset(None))

    def test_the_clock_can_be_frozen_for_tests(self):
        from datetime import datetime, timezone

        from rally.core import clock

        instant = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
        previous = clock.set_clock(clock.FrozenClock(instant))
        try:
            self.assertEqual(clock.now(), instant)
        finally:
            clock.set_clock(previous)
