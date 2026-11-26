"""M1's published read view carries no contact data (rule 6, ADR-002)."""
from django.db import connection
from django.test import TestCase

from rally.modules.identity.api import facade as identity
from rally.modules.identity.views import VERIFIED_ACCOUNT, VERIFIED_ACCOUNT_COLUMNS


def _columns(view_name: str) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s ORDER BY ordinal_position",
            [view_name],
        )
        return [row[0] for row in cursor.fetchall()]


class VerifiedAccountViewTests(TestCase):
    def test_the_view_exposes_exactly_its_declared_columns(self):
        self.assertEqual(tuple(_columns(VERIFIED_ACCOUNT)), VERIFIED_ACCOUNT_COLUMNS)

    def test_the_view_carries_no_contact_field(self):
        columns = set(_columns(VERIFIED_ACCOUNT))
        self.assertNotIn("email", columns)
        self.assertNotIn("phone", columns)

    def test_a_registered_account_appears_with_its_verification_state(self):
        account_id = identity.register("viewed@example.com", "longenough").account_id

        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT account_id, is_verified FROM {VERIFIED_ACCOUNT} WHERE account_id = %s",
                [account_id],
            )
            row = cursor.fetchone()

        self.assertEqual(row, (account_id, False))
