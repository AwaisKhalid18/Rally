"""AC1, AC2, AC3 end to end: UI -> Platform view -> M1 facade -> data.

These are Platform tests, so they reach M1 only through its facade (rule 2). Whether an
account was really created is asked of the facade, not of M1's table.
"""
from django.test import TestCase
from django.urls import reverse

from rally.core.pipeline.session import ACCOUNT_ID_KEY
from rally.modules.identity.api import facade as identity

EMAIL = "player@example.com"
PASSWORD = "longenough"


def account_exists(email: str, password: str) -> bool:
    return identity.authenticate(email, password).ok


class RegisterPageTests(TestCase):
    def test_the_page_is_reachable_without_a_session(self):
        response = self.client.get(reverse("register"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create your account")

    def test_registering_creates_an_unverified_account_and_sends_the_player_to_sign_in(self):
        response = self.client.post(reverse("register"), {"email": EMAIL, "password": PASSWORD})

        self.assertRedirects(response, reverse("sign_in"))
        result = identity.authenticate(EMAIL, PASSWORD)
        self.assertTrue(result.ok)
        self.assertFalse(identity.is_verified(result.account_id))

    def test_a_rejected_registration_keeps_the_email_the_player_typed(self):
        """AC2 - clear message, and the form keeps the valid inputs."""
        response = self.client.post(reverse("register"), {"email": EMAIL, "password": "short"})

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, identity.PASSWORD_TOO_SHORT, status_code=400)
        self.assertContains(response, EMAIL, status_code=400)
        self.assertFalse(account_exists(EMAIL, "short"))

    def test_an_invalid_email_is_rejected_and_nothing_is_created(self):
        response = self.client.post(
            reverse("register"), {"email": "not-an-email", "password": PASSWORD}
        )

        self.assertContains(response, identity.EMAIL_INVALID, status_code=400)
        self.assertFalse(account_exists("not-an-email", PASSWORD))

    def test_a_duplicate_email_is_reported_on_the_email_field(self):
        identity.register(EMAIL, PASSWORD)

        response = self.client.post(reverse("register"), {"email": EMAIL, "password": PASSWORD})

        self.assertContains(response, identity.EMAIL_TAKEN, status_code=400)

    def test_the_password_is_never_echoed_back(self):
        response = self.client.post(reverse("register"), {"email": "bad", "password": PASSWORD})
        self.assertNotContains(response, PASSWORD, status_code=400)


class SignInTests(TestCase):
    def setUp(self):
        self.account_id = identity.register(EMAIL, PASSWORD).account_id

    def test_valid_credentials_start_a_session(self):
        response = self.client.post(reverse("sign_in"), {"email": EMAIL, "password": PASSWORD})

        self.assertRedirects(response, reverse("home"))
        self.assertEqual(self.client.session[ACCOUNT_ID_KEY], self.account_id)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_wrong_credentials_give_one_generic_error_and_no_session(self):
        response = self.client.post(reverse("sign_in"), {"email": EMAIL, "password": "not-it"})

        self.assertContains(response, identity.SIGN_IN_FAILED, status_code=400)
        self.assertNotIn(ACCOUNT_ID_KEY, self.client.session)

    def test_an_unknown_email_gives_the_same_error(self):
        response = self.client.post(
            reverse("sign_in"), {"email": "nobody@example.com", "password": PASSWORD}
        )
        self.assertContains(response, identity.SIGN_IN_FAILED, status_code=400)

    def test_signing_in_returns_the_player_to_the_page_they_asked_for(self):
        response = self.client.post(
            reverse("sign_in"),
            {"email": EMAIL, "password": PASSWORD, "next": reverse("home")},
        )
        self.assertRedirects(response, reverse("home"))

    def test_an_off_site_next_is_ignored(self):
        response = self.client.post(
            reverse("sign_in"),
            {"email": EMAIL, "password": PASSWORD, "next": "https://example.net/steal"},
        )
        self.assertRedirects(response, reverse("home"))

    def test_a_signed_in_player_is_sent_home_from_the_public_pages(self):
        self.client.post(reverse("sign_in"), {"email": EMAIL, "password": PASSWORD})
        self.assertRedirects(self.client.get(reverse("sign_in")), reverse("home"))
        self.assertRedirects(self.client.get(reverse("register")), reverse("home"))


class SignOutTests(TestCase):
    def setUp(self):
        identity.register(EMAIL, PASSWORD)
        self.client.post(reverse("sign_in"), {"email": EMAIL, "password": PASSWORD})

    def test_signing_out_ends_the_session(self):
        response = self.client.post(reverse("sign_out"))

        self.assertRedirects(response, reverse("sign_in"))
        self.assertNotIn(ACCOUNT_ID_KEY, self.client.session)
        self.assertEqual(self.client.get(reverse("home")).status_code, 302)

    def test_sign_out_is_not_reachable_by_get(self):
        """FE-9 - state never changes on GET."""
        self.assertEqual(self.client.get(reverse("sign_out")).status_code, 405)
        self.assertIn(ACCOUNT_ID_KEY, self.client.session)
