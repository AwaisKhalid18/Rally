"""M4 compare() - plan.md S14 AC1, AC2, AC3."""
import datetime as _dt

from django.test import TestCase

from rally.core import clock
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.profiles.api import facade as profiles
from rally.modules.safety.api import facade as safety
from rally.modules.search.api import facade as search_api

PASSWORD = "longenough"
AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
    {"code": "isb-g9", "name": "Islamabad G-9", "centroid_lat": "33.6889", "centroid_lon": "73.0369"},
]
F7 = (33.7211, 73.0551)


def at(day_offset: int, hour: int) -> _dt.datetime:
    midnight = clock.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + _dt.timedelta(days=day_offset, hours=hour)


class CompareCase(TestCase):
    def setUp(self):
        profiles.replace_areas(AREAS)
        self.viewer = self.make_player("viewer")
        self.first = self.make_player("first")
        self.second = self.make_player("second", area="isb-g9", level="advanced")
        self.third = self.make_player("third")

    def make_player(self, name, slots=True, area="isb-f7", level="intermediate", verified=True):
        account_id = identity.register(f"{name}@example.com", PASSWORD).account_id
        assert profiles.save_profile(account_id, name.title(), level, area).ok
        if verified:
            identity.verify_email(identity.get_verification_token(account_id))
        if slots:
            assert availability.add_slot(account_id, at(1, 18), at(1, 20)).ok
        return account_id

    def compare(self, ids, reference=F7):
        return search_api.compare(self.viewer, ids, reference)


class WhatAComparisonShowsTests(CompareCase):
    """AC1."""

    def test_one_player_can_be_compared(self):
        outcome = self.compare([self.first])

        self.assertTrue(outcome.ok, outcome.errors)
        (player,) = outcome.players
        self.assertEqual(player.display_name, "First")
        self.assertEqual(player.playing_level, "intermediate")
        self.assertEqual(player.area_name, "Islamabad F-7")

    def test_three_players_can_be_compared(self):
        outcome = self.compare([self.first, self.second, self.third])

        self.assertTrue(outcome.ok, outcome.errors)
        self.assertEqual(len(outcome.players), 3)

    def test_the_columns_keep_the_order_they_were_asked_for(self):
        outcome = self.compare([self.third, self.first, self.second])

        self.assertEqual(
            [p.account_id for p in outcome.players], [self.third, self.first, self.second]
        )

    def test_available_times_are_listed(self):
        outcome = self.compare([self.first])

        (player,) = outcome.players
        self.assertEqual([(s.starts_at, s.ends_at) for s in player.slots], [(at(1, 18), at(1, 20))])
        self.assertIsNone(player.no_slots_reason)

    def test_distance_is_calculated_from_the_reference_point(self):
        outcome = self.compare([self.second])

        (player,) = outcome.players
        self.assertIsNotNone(player.distance_km)
        self.assertGreater(player.distance_km, 0)
        self.assertIsNone(player.no_distance_reason)

    def test_a_player_in_the_reference_area_is_about_zero_away(self):
        outcome = self.compare([self.first])

        (player,) = outcome.players
        self.assertAlmostEqual(player.distance_km, 0.0, places=3)


class MissingInformationTests(CompareCase):
    """AC1 - 'each missing value shows its reason (never blank/0)' (rule 13)."""

    def test_a_player_with_no_times_is_still_comparable(self):
        """AGENTS 5: comparable even with no future slots, times absent with a reason."""
        quiet = self.make_player("quiet", slots=False)

        outcome = self.compare([quiet])

        (player,) = outcome.players
        self.assertTrue(player.found)
        self.assertEqual(player.display_name, "Quiet")
        self.assertEqual(player.slots, ())
        self.assertEqual(player.no_slots_reason, search_api.NO_SLOTS_REASON)

    def test_a_past_slot_is_not_an_available_time(self):
        outcome_before = self.compare([self.first])
        self.assertTrue(outcome_before.players[0].slots, "precondition")

        previous = clock.set_clock(clock.FrozenClock(at(2, 12)))
        self.addCleanup(clock.set_clock, previous)

        (player,) = self.compare([self.first]).players
        self.assertEqual(player.slots, ())
        self.assertEqual(player.no_slots_reason, search_api.NO_SLOTS_REASON)

    def test_without_a_reference_point_the_distance_is_absent_with_a_reason(self):
        """M4 never invents a distance - not 0, not a placeholder (rule 13)."""
        outcome = search_api.compare(self.viewer, [self.first], None)

        (player,) = outcome.players
        self.assertTrue(player.found)
        self.assertIsNone(player.distance_km)
        self.assertEqual(player.no_distance_reason, search_api.NO_DISTANCE_REASON)

    def test_a_missing_distance_is_never_reported_as_zero(self):
        outcome = search_api.compare(self.viewer, [self.first], None)

        self.assertNotEqual(outcome.players[0].distance_km, 0)


class TheCapTests(CompareCase):
    """AC2 - 'a request with 4 players is rejected by the server'."""

    def test_four_players_are_refused(self):
        fourth = self.make_player("fourth")

        outcome = self.compare([self.first, self.second, self.third, fourth])

        self.assertEqual(outcome.errors, {"players": search_api.TOO_MANY})
        self.assertEqual(outcome.players, ())

    def test_the_message_names_the_limit(self):
        fourth = self.make_player("fourth")

        outcome = self.compare([self.first, self.second, self.third, fourth])

        self.assertIn(str(search_api.MAX_COMPARED), outcome.errors["players"])

    def test_three_is_the_boundary_and_is_allowed(self):
        """BVA: three in, four out."""
        self.assertTrue(self.compare([self.first, self.second, self.third]).ok)

    def test_an_empty_selection_is_refused(self):
        self.assertEqual(self.compare([]).errors, {"players": search_api.NONE_SELECTED})

    def test_the_same_player_twice_is_refused(self):
        outcome = self.compare([self.first, self.first])

        self.assertEqual(outcome.errors, {"players": search_api.DUPLICATE_SELECTED})

    def test_you_cannot_compare_yourself(self):
        outcome = self.compare([self.viewer, self.first])

        self.assertEqual(outcome.errors, {"players": search_api.CANNOT_COMPARE_YOURSELF})


class NothingIsStoredTests(CompareCase):
    """AC2 - 'removing/replacing is a new request; nothing is stored'."""

    def test_comparing_writes_nothing_anywhere(self):
        from django.db import connection

        def row_counts():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY relname
                    """
                )
                return cursor.fetchall()

        before = row_counts()
        self.compare([self.first, self.second])

        self.assertEqual(row_counts(), before)

    def test_removing_a_player_is_simply_a_different_call(self):
        both = self.compare([self.first, self.second])
        one = self.compare([self.first])

        self.assertEqual(len(both.players), 2)
        self.assertEqual(len(one.players), 1)
        self.assertEqual(one.players[0].account_id, self.first)

    def test_comparing_twice_gives_the_same_answer(self):
        first = self.compare([self.first, self.second])
        second = self.compare([self.first, self.second])

        self.assertEqual(
            [p.account_id for p in first.players], [p.account_id for p in second.players]
        )


class BlockedAndMissingLookIdenticalTests(CompareCase):
    """AC3 - 'a blocked or non-existent player is treated identically (not found)'."""

    def test_an_account_that_does_not_exist_is_not_found(self):
        outcome = self.compare([999_999])

        (player,) = outcome.players
        self.assertFalse(player.found)
        self.assertEqual(player.not_found_reason, search_api.NOT_FOUND_REASON)

    def test_a_player_the_viewer_blocked_is_not_found(self):
        safety.block(self.viewer, self.first)

        (player,) = self.compare([self.first]).players

        self.assertFalse(player.found)
        self.assertEqual(player.not_found_reason, search_api.NOT_FOUND_REASON)

    def test_a_player_who_blocked_the_viewer_is_not_found_either(self):
        """Both directions (ASR-10)."""
        safety.block(self.first, self.viewer)

        (player,) = self.compare([self.first]).players

        self.assertFalse(player.found)

    def test_the_two_are_indistinguishable(self):
        """The point of AC3: nothing in the answer tells them apart, so the absence of
        a result can never confirm that an account exists."""
        safety.block(self.viewer, self.first)

        (blocked,) = self.compare([self.first]).players
        (missing,) = self.compare([999_999]).players

        self.assertEqual(
            (blocked.found, blocked.display_name, blocked.playing_level, blocked.area_name,
             blocked.slots, blocked.distance_km, blocked.not_found_reason),
            (missing.found, missing.display_name, missing.playing_level, missing.area_name,
             missing.slots, missing.distance_km, missing.not_found_reason),
        )

    def test_an_unverified_player_is_not_comparable(self):
        """ASR-06: `searchable` folds in the verification gate."""
        unverified = self.make_player("unverified", verified=False)

        (player,) = self.compare([unverified]).players

        self.assertFalse(player.found)

    def test_the_others_are_still_compared_alongside_a_missing_one(self):
        outcome = self.compare([self.first, 999_999])

        self.assertTrue(outcome.ok, outcome.errors)
        found, missing = outcome.players
        self.assertTrue(found.found)
        self.assertFalse(missing.found)


class NothingPrivateIsReturnedTests(CompareCase):
    """Rule 6, rule 7, ASR-04."""

    def test_no_field_carries_an_address_or_a_coordinate_pair(self):
        outcome = self.compare([self.first, self.second])

        for player in outcome.players:
            for value in vars(player).values():
                self.assertNotIn("@", str(value))
            # The area's centroid never leaves M4: only a derived distance does.
            self.assertNotIn("33.7211", str(vars(player)))
            self.assertNotIn("73.0551", str(vars(player)))
