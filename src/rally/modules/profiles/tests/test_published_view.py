"""M2's published read view - the contract M4 and M8 will depend on (ADR-002, ADR-006)."""
from django.db import connection
from django.test import TestCase

from rally.modules.identity.api import facade as identity
from rally.modules.profiles.api import facade as profiles
from rally.modules.profiles.views import SEARCHABLE_PROFILE, SEARCHABLE_PROFILE_COLUMNS

PASSWORD = "longenough"
AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
]


def columns(view_name: str) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s ORDER BY ordinal_position",
            [view_name],
        )
        return [row[0] for row in cursor.fetchall()]


def rows():
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT account_id, display_name, playing_level, level_rank, area_name, searchable "
            f"FROM {SEARCHABLE_PROFILE} ORDER BY account_id"
        )
        return cursor.fetchall()


class SearchableProfileViewTests(TestCase):
    def setUp(self):
        profiles.replace_areas(AREAS)
        self.account_id = identity.register("viewed@example.com", PASSWORD).account_id
        profiles.save_profile(self.account_id, "Maaiz", "intermediate", "isb-f7")

    def test_the_view_exposes_exactly_its_declared_columns(self):
        self.assertEqual(tuple(columns(SEARCHABLE_PROFILE)), SEARCHABLE_PROFILE_COLUMNS)

    def test_the_view_carries_no_contact_field(self):
        present = set(columns(SEARCHABLE_PROFILE))
        self.assertFalse(present & {"email", "phone", "password", "verification_token"})

    def test_the_view_carries_an_area_centroid_and_no_player_position(self):
        """Rule 7 - the only coordinates are the area's centre."""
        present = set(columns(SEARCHABLE_PROFILE))
        self.assertEqual(present & {"centroid_lat", "centroid_lon"}, {"centroid_lat", "centroid_lon"})
        self.assertFalse(present & {"latitude", "longitude", "location", "address"})

    def test_an_unverified_player_is_not_searchable(self):
        """ASR-06 - the gate is folded into the view, so M4 cannot forget it."""
        (row,) = rows()
        self.assertEqual(row[0], self.account_id)
        self.assertFalse(row[5])

    def test_verifying_the_email_makes_the_profile_searchable(self):
        identity.verify_email(identity.get_verification_token(self.account_id))

        (row,) = rows()
        self.assertTrue(row[5])

    def test_the_row_carries_the_public_fields_and_the_level_rank(self):
        (row,) = rows()
        self.assertEqual(row[1], "Maaiz")
        self.assertEqual(row[2], "intermediate")
        self.assertEqual(row[3], 2)
        self.assertEqual(row[4], "Islamabad F-7")

    def test_an_account_without_a_profile_has_no_row(self):
        identity.register("nothing@example.com", PASSWORD)
        self.assertEqual(len(rows()), 1)
