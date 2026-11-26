"""M1 credential check — plan.md S1 AC3."""
from django.test import TestCase

from rally.modules.identity.api import facade as identity
from rally.modules.identity.internal.models import Account

PASSWORD = "correct-horse"


class AuthenticateTests(TestCase):
    def setUp(self):
        self.account_id = identity.register("player@example.com", PASSWORD).account_id

    def test_correct_credentials_identify_the_account(self):
        result = identity.authenticate("player@example.com", PASSWORD)

        self.assertTrue(result.ok)
        self.assertEqual(result.account_id, self.account_id)
        self.assertIsNone(result.reason)

    def test_email_case_does_not_matter(self):
        self.assertTrue(identity.authenticate("PLAYER@example.com", PASSWORD).ok)

    def test_wrong_password_and_unknown_email_give_the_same_generic_reason(self):
        """AC3 — wrong credentials give one generic error, whichever part is wrong."""
        wrong_password = identity.authenticate("player@example.com", "wrong-password")
        unknown_email = identity.authenticate("stranger@example.com", PASSWORD)

        self.assertFalse(wrong_password.ok)
        self.assertFalse(unknown_email.ok)
        self.assertEqual(wrong_password.reason, unknown_email.reason)
        self.assertEqual(wrong_password.reason, identity.SIGN_IN_FAILED)

    def test_an_inactive_account_cannot_sign_in(self):
        Account.objects.filter(pk=self.account_id).update(is_active=False)
        self.assertFalse(identity.authenticate("player@example.com", PASSWORD).ok)


class AccountSummaryTests(TestCase):
    def test_summary_carries_no_contact_data(self):
        account_id = identity.register("summary@example.com", PASSWORD).account_id

        summary = identity.account_summary(account_id)

        self.assertEqual(summary.account_id, account_id)
        self.assertFalse(summary.is_verified)
        self.assertEqual(
            set(vars(summary)), {"account_id", "is_verified"}, "AccountSummary must carry no contact field (rule 6)"
        )

    def test_summary_is_absent_for_an_unusable_account(self):
        self.assertIsNone(identity.account_summary(999_999))
