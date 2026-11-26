"""M2 profile rules - plan.md S3 AC1, AC2 (completeness) and AC4.

M2's own tests, so they may read M2's internals. M1 is reached only through its facade
where it is needed at all.
"""
from django.test import TestCase

from rally.modules.identity.api import facade as identity
from rally.modules.profiles.api import facade as profiles
from rally.modules.profiles.internal.models import Area, PlayingLevel, Profile

PASSWORD = "longenough"
AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
    {"code": "isb-g9", "name": "Islamabad G-9", "centroid_lat": "33.6900", "centroid_lon": "73.0300"},
]


class ProfileCase(TestCase):
    def setUp(self):
        profiles.replace_areas(AREAS)
        self.account_id = identity.register("owner@example.com", PASSWORD).account_id


class SaveProfileTests(ProfileCase):
    def test_an_owner_sets_name_level_and_area(self):
        """AC1."""
        result = profiles.save_profile(self.account_id, "Maaiz", "intermediate", "isb-f7")

        self.assertTrue(result.ok, result.errors)
        own = profiles.get_own_profile(self.account_id)
        self.assertEqual(own.display_name, "Maaiz")
        self.assertEqual(own.playing_level, "intermediate")
        self.assertEqual(own.area_code, "isb-f7")

    def test_saving_again_replaces_rather_than_duplicates(self):
        profiles.save_profile(self.account_id, "Maaiz", "beginner", "isb-f7")
        profiles.save_profile(self.account_id, "Maaiz A", "advanced", "isb-g9")

        self.assertEqual(Profile.objects.filter(account_id=self.account_id).count(), 1)
        own = profiles.get_own_profile(self.account_id)
        self.assertEqual((own.display_name, own.playing_level, own.area_code), ("Maaiz A", "advanced", "isb-g9"))

    def test_the_display_name_is_trimmed(self):
        profiles.save_profile(self.account_id, "  Maaiz  ", "beginner", "isb-f7")
        self.assertEqual(profiles.get_own_profile(self.account_id).display_name, "Maaiz")

    def test_one_profile_per_account(self):
        other = identity.register("other@example.com", PASSWORD).account_id
        profiles.save_profile(self.account_id, "One", "beginner", "isb-f7")
        profiles.save_profile(other, "Two", "advanced", "isb-g9")

        self.assertEqual(profiles.get_own_profile(self.account_id).display_name, "One")
        self.assertEqual(profiles.get_own_profile(other).display_name, "Two")

    def test_an_account_with_no_profile_reports_absence_not_blanks(self):
        own = profiles.get_own_profile(self.account_id)
        self.assertFalse(own.exists)
        self.assertIsNone(profiles.get_public_profile(self.account_id))


class RejectedInputTests(ProfileCase):
    """AC4 - every rejection names its field and changes nothing."""

    def _rejected(self, name, level, area):
        result = profiles.save_profile(self.account_id, name, level, area)
        self.assertFalse(result.ok)
        self.assertEqual(Profile.objects.count(), 0)
        return result.errors

    def test_a_level_outside_the_three_is_rejected(self):
        self.assertEqual(
            self._rejected("Maaiz", "professional", "isb-f7"), {"playing_level": profiles.LEVEL_INVALID}
        )

    def test_an_area_outside_the_fixed_list_is_rejected(self):
        self.assertEqual(
            self._rejected("Maaiz", "beginner", "atlantis"), {"area_code": profiles.AREA_INVALID}
        )

    def test_a_missing_field_is_named(self):
        errors = self._rejected("", "", "")
        self.assertEqual(
            errors,
            {
                "display_name": profiles.NAME_REQUIRED,
                "playing_level": profiles.LEVEL_REQUIRED,
                "area_code": profiles.AREA_REQUIRED,
            },
        )


class DisplayNameBoundaryTests(ProfileCase):
    """The rule is 2 to 40 characters (G-12), so 1 / 2 and 40 / 41 are what matter."""

    def _save(self, length):
        return profiles.save_profile(self.account_id, "n" * length, "beginner", "isb-f7")

    def test_one_character_is_rejected(self):
        self.assertEqual(self._save(1).errors, {"display_name": profiles.NAME_TOO_SHORT})

    def test_two_characters_is_accepted(self):
        self.assertTrue(self._save(2).ok)

    def test_forty_characters_is_accepted(self):
        self.assertTrue(self._save(40).ok)

    def test_forty_one_characters_is_rejected(self):
        self.assertEqual(self._save(41).errors, {"display_name": profiles.NAME_TOO_LONG})


class CompletenessTests(ProfileCase):
    """AC2 - complete means name + level + area + a verified email (PRD 12.1)."""

    def test_a_profile_without_a_verified_email_is_not_complete(self):
        profiles.save_profile(self.account_id, "Maaiz", "beginner", "isb-f7")
        self.assertFalse(profiles.is_complete(self.account_id))

    def test_a_verified_account_without_a_profile_is_not_complete(self):
        identity.verify_email(identity.get_verification_token(self.account_id))
        self.assertFalse(profiles.is_complete(self.account_id))

    def test_both_together_make_it_complete(self):
        profiles.save_profile(self.account_id, "Maaiz", "beginner", "isb-f7")
        identity.verify_email(identity.get_verification_token(self.account_id))

        self.assertTrue(profiles.is_complete(self.account_id))


class PublicProfileTests(ProfileCase):
    """AC3 - what another player may read."""

    def setUp(self):
        super().setUp()
        profiles.save_profile(self.account_id, "Maaiz", "advanced", "isb-g9")

    def test_it_carries_the_public_fields_and_only_those(self):
        public = profiles.get_public_profile(self.account_id)

        self.assertEqual(
            set(vars(public)),
            {
                "account_id",
                "display_name",
                "playing_level",
                "playing_level_label",
                "level_rank",
                "area_code",
                "area_name",
            },
        )
        self.assertEqual(public.display_name, "Maaiz")
        self.assertEqual(public.playing_level_label, "Advanced")
        self.assertEqual(public.area_name, "Islamabad G-9")

    def test_it_carries_no_contact_field(self):
        public = profiles.get_public_profile(self.account_id)
        blob = " ".join(str(value) for value in vars(public).values())
        self.assertNotIn("@", blob)

    def test_the_level_rank_orders_the_three_levels(self):
        self.assertEqual(profiles.get_public_profile(self.account_id).level_rank, 3)


class AreaTests(ProfileCase):
    def test_the_area_list_is_fixed_and_offered_whole(self):
        self.assertEqual({a.code for a in profiles.list_areas()}, {"isb-f7", "isb-g9"})

    def test_reloading_the_list_updates_rather_than_duplicates(self):
        profiles.replace_areas(AREAS)
        self.assertEqual(Area.objects.count(), 2)

    def test_an_area_holds_a_centroid_and_no_player_position(self):
        """Rule 7 - the schema has no exact-location field."""
        columns = {field.name for field in Area._meta.get_fields()}
        self.assertEqual(columns & {"centroid_lat", "centroid_lon"}, {"centroid_lat", "centroid_lon"})
        for forbidden in ("latitude", "longitude", "location", "address", "postcode"):
            self.assertNotIn(forbidden, {field.name for field in Profile._meta.get_fields()})

    def test_the_three_levels_are_the_prd_vocabulary(self):
        self.assertEqual(
            [level.name for level in profiles.playing_levels()],
            ["Beginner", "Intermediate", "Advanced"],
        )
        self.assertEqual(len(PlayingLevel.choices), 3)
