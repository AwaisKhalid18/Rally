"""M1 email verification - plan.md S2 AC1 and AC3."""
from django.test import TestCase

from rally.modules.identity.api import facade as identity
from rally.modules.identity.internal.models import Account

EMAIL = "verify@example.com"
PASSWORD = "longenough"

# M1 must not import M7, not even in a test (rule 2). What lands in the outbox is
# asserted where the outbox lives: rally/modules/notification/tests/test_dispatch.py
# and rally/core/tests/test_verification_flow.py.


class RegistrationIssuesATokenTests(TestCase):
    """AC1, M1's half - registration issues a single-use token."""

    def test_registration_issues_a_token(self):
        account_id = identity.register(EMAIL, PASSWORD).account_id

        token = identity.get_verification_token(account_id)
        self.assertTrue(token)
        self.assertGreater(len(token), 20)
        self.assertFalse(identity.is_verified(account_id))

    def test_two_accounts_get_different_tokens(self):
        first = identity.register("one@example.com", PASSWORD).account_id
        second = identity.register("two@example.com", PASSWORD).account_id

        self.assertNotEqual(
            identity.get_verification_token(first), identity.get_verification_token(second)
        )


class VerifyTests(TestCase):
    """AC3 - the token verifies once; anything else changes nothing."""

    def setUp(self):
        self.account_id = identity.register(EMAIL, PASSWORD).account_id
        self.token = identity.get_verification_token(self.account_id)

    def test_a_valid_token_verifies_the_account(self):
        result = identity.verify_email(self.token)

        self.assertTrue(result.ok)
        self.assertEqual(result.account_id, self.account_id)
        self.assertTrue(identity.is_verified(self.account_id))
        account = Account.objects.get(pk=self.account_id)
        self.assertIsNotNone(account.verified_at)
        self.assertIsNone(account.verification_token)

    def test_the_token_is_single_use(self):
        identity.verify_email(self.token)

        second = identity.verify_email(self.token)

        self.assertFalse(second.ok)
        self.assertEqual(second.reason, identity.VERIFICATION_UNKNOWN_TOKEN)

    def test_an_unknown_token_changes_nothing(self):
        result = identity.verify_email("not-a-real-token")

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, identity.VERIFICATION_UNKNOWN_TOKEN)
        self.assertFalse(identity.is_verified(self.account_id))

    def test_an_empty_token_changes_nothing(self):
        self.assertFalse(identity.verify_email("").ok)
        self.assertFalse(identity.is_verified(self.account_id))

    def test_can_verify_reports_without_changing_anything(self):
        self.assertTrue(identity.can_verify(self.token))
        self.assertFalse(identity.is_verified(self.account_id))
        self.assertFalse(identity.can_verify("not-a-real-token"))

    def test_the_token_is_gone_once_the_account_is_verified(self):
        identity.verify_email(self.token)
        self.assertIsNone(identity.get_verification_token(self.account_id))

    def test_verifying_does_not_sign_the_player_in(self):
        """Verification is an M1 state change, not a session (ADR-003)."""
        identity.verify_email(self.token)
        self.assertTrue(identity.authenticate(EMAIL, PASSWORD).ok)
