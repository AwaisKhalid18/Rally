"""M1 registration policy — plan.md S1 AC1 and AC2."""
from django.test import TestCase

from rally.modules.identity.api import facade as identity
from rally.modules.identity.internal import credentials
from rally.modules.identity.internal.models import Account

VALID_PASSWORD = "longenough"


class RegisterTests(TestCase):
    def test_creates_an_unverified_account(self):
        """AC1 — a visitor registers and an unverified account is created."""
        result = identity.register("Player@example.com", VALID_PASSWORD)

        self.assertTrue(result.ok)
        self.assertEqual(result.errors, {})
        account = Account.objects.get(pk=result.account_id)
        self.assertFalse(account.is_verified)
        self.assertIsNone(account.verified_at)
        self.assertFalse(identity.is_verified(result.account_id))

    def test_password_is_stored_hashed(self):
        """AC1 — the password is stored hashed, never in clear."""
        result = identity.register("hash@example.com", VALID_PASSWORD)
        account = Account.objects.get(pk=result.account_id)

        self.assertNotEqual(account.password, VALID_PASSWORD)
        self.assertNotIn(VALID_PASSWORD, account.password)
        self.assertIn("$", account.password)  # algorithm$iterations$salt$hash
        self.assertTrue(account.check_password(VALID_PASSWORD))

    def test_email_is_normalised(self):
        result = identity.register("  MiXeD@Example.COM ", VALID_PASSWORD)
        self.assertEqual(Account.objects.get(pk=result.account_id).email, "mixed@example.com")

    def test_rejects_an_invalid_email(self):
        """AC2 — invalid email is rejected with a clear message."""
        result = identity.register("not-an-email", VALID_PASSWORD)

        self.assertFalse(result.ok)
        self.assertEqual(result.errors, {"email": credentials.EMAIL_INVALID})
        self.assertEqual(Account.objects.count(), 0)

    def test_rejects_an_already_registered_email_ignoring_case(self):
        """AC2 — an already-registered email is rejected."""
        identity.register("taken@example.com", VALID_PASSWORD)

        result = identity.register("TAKEN@example.com", VALID_PASSWORD)

        self.assertFalse(result.ok)
        self.assertEqual(result.errors, {"email": credentials.EMAIL_TAKEN})
        self.assertEqual(Account.objects.count(), 1)

    def test_rejects_missing_fields(self):
        result = identity.register("", "")
        self.assertEqual(
            result.errors,
            {"email": credentials.EMAIL_REQUIRED, "password": credentials.PASSWORD_REQUIRED},
        )


class PasswordLengthBoundaryTests(TestCase):
    """AC2 boundary — the rule is 'at least 8', so 7 / 8 / 9 are the values that matter."""

    def test_seven_characters_is_rejected(self):
        result = identity.register("seven@example.com", "a" * 7)
        self.assertFalse(result.ok)
        self.assertEqual(result.errors, {"password": credentials.PASSWORD_TOO_SHORT})
        self.assertEqual(Account.objects.count(), 0)

    def test_eight_characters_is_accepted(self):
        result = identity.register("eight@example.com", "a" * 8)
        self.assertTrue(result.ok, result.errors)

    def test_nine_characters_is_accepted(self):
        result = identity.register("nine@example.com", "a" * 9)
        self.assertTrue(result.ok, result.errors)

    def test_the_minimum_is_eight(self):
        self.assertEqual(identity.PASSWORD_MIN_LENGTH, 8)
