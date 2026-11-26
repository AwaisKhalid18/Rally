"""M4's predicate and ranking - plan.md S5 AC2, AC3, AC4, AC7.

M4 owns no tables, so these tests build the world through the other modules' facades and
then assert on what the one query returns.
"""
import datetime as _dt

from django.test import TestCase

from rally.core import clock
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.profiles.api import facade as profiles
from rally.modules.safety.api import facade as safety
from rally.modules.search.api import facade as search

PASSWORD = "longenough"

# Three areas at known separations from F-7, so distance ordering is checkable.
AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
    {"code": "isb-f8", "name": "Islamabad F-8", "centroid_lat": "33.7006", "centroid_lon": "73.0387"},
    {"code": "rwp-gulraiz", "name": "Rawalpindi Gulraiz", "centroid_lat": "33.5520", "centroid_lon": "73.1170"},
]
F7 = (33.7211, 73.0551)


def at(day_offset: int, hour: int) -> _dt.datetime:
    base = clock.now().replace(minute=0, second=0, microsecond=0)
    return base + _dt.timedelta(days=day_offset, hours=hour - base.hour)


class MatchingCase(TestCase):
    def setUp(self):
        profiles.replace_areas(AREAS)
        self.searcher_id = self.make_player("searcher", "isb-f7", verified=True, slot=None)

    def make_player(self, name, area_code, verified=True, slot=(1, 18, 20), complete=True, level="intermediate"):
        account_id = identity.register(f"{name}@example.com", PASSWORD).account_id
        if complete:
            profiles.save_profile(account_id, name.title(), level, area_code)
        if verified:
            identity.verify_email(identity.get_verification_token(account_id))
        if slot:
            day, start, end = slot
            availability.add_slot(account_id, at(day, start), at(day, end))
        return account_id

    def run_search(self, day=1, start=18, end=20, area="isb-f7", searcher=None):
        return search.search(
            searcher_id=searcher or self.searcher_id,
            window_start=at(day, start),
            window_end=at(day, end),
            area_code=area,
            area_centroid=F7,
        )


class WhoAppearsTests(MatchingCase):
    """AC2."""

    def test_a_verified_complete_player_with_an_overlapping_slot_appears(self):
        other = self.make_player("other", "isb-f7")

        outcome = self.run_search()

        self.assertTrue(outcome.ok, outcome.errors)
        self.assertEqual([m.account_id for m in outcome.results], [other])

    def test_the_searcher_never_appears_in_their_own_results(self):
        availability.add_slot(self.searcher_id, at(1, 18), at(1, 20))
        self.make_player("other", "isb-f7")

        self.assertNotIn(self.searcher_id, [m.account_id for m in self.run_search().results])

    def test_an_unverified_player_does_not_appear(self):
        """ASR-06, folded into the view's `searchable` flag."""
        self.make_player("unverified", "isb-f7", verified=False)

        self.assertEqual(self.run_search().results, ())

    def test_a_player_without_a_profile_does_not_appear(self):
        self.make_player("naked", "isb-f7", complete=False)

        self.assertEqual(self.run_search().results, ())

    def test_a_player_with_no_overlapping_slot_does_not_appear(self):
        self.make_player("elsewhen", "isb-f7", slot=(2, 18, 20))

        self.assertEqual(self.run_search().results, ())

    def test_a_slot_merely_touching_the_window_does_not_overlap(self):
        """The overlap is strict: ending exactly when the window opens is not a match."""
        self.make_player("before", "isb-f7", slot=(1, 16, 18))
        self.make_player("after", "isb-f7", slot=(1, 20, 22))

        self.assertEqual(self.run_search().results, ())

    def test_a_partial_overlap_is_enough(self):
        self.make_player("partial", "isb-f7", slot=(1, 19, 21))

        self.assertEqual(len(self.run_search().results), 1)

    def test_a_player_appears_once_with_all_their_overlapping_slots(self):
        other = self.make_player("multi", "isb-f7", slot=(1, 17, 19))
        availability.add_slot(other, at(1, 19), at(1, 21))

        (match,) = self.run_search(start=17, end=21).results

        self.assertEqual(len(match.overlapping_slots), 2)


class BlockingTests(MatchingCase):
    """AC2 and ASR-10 - a block hides the pair from each other, both ways."""

    def test_a_player_the_searcher_blocked_does_not_appear(self):
        other = self.make_player("blocked", "isb-f7")
        safety.block_for_test(self.searcher_id, other)

        self.assertEqual(self.run_search().results, ())

    def test_a_player_who_blocked_the_searcher_does_not_appear(self):
        other = self.make_player("blocker", "isb-f7")
        safety.block_for_test(other, self.searcher_id)

        self.assertEqual(self.run_search().results, ())

    def test_a_block_between_two_other_players_changes_nothing(self):
        first = self.make_player("first", "isb-f7")
        second = self.make_player("second", "isb-f7")
        safety.block_for_test(first, second)

        self.assertEqual(len(self.run_search().results), 2)


class DistanceAndRankingTests(MatchingCase):
    """AC3 and AC4."""

    def test_results_are_ordered_by_distance_then_earliest_overlap(self):
        far = self.make_player("far", "rwp-gulraiz")
        near = self.make_player("near", "isb-f8")
        same = self.make_player("same", "isb-f7")

        order = [m.account_id for m in self.run_search().results]

        self.assertEqual(order, [same, near, far])

    def test_players_at_the_same_distance_are_ordered_by_earliest_overlap(self):
        later = self.make_player("later", "isb-f7", slot=(1, 19, 21))
        earlier = self.make_player("earlier", "isb-f7", slot=(1, 17, 20))

        order = [m.account_id for m in self.run_search(start=17, end=21).results]

        self.assertEqual(order, [earlier, later])

    def test_a_player_in_the_searchers_own_area_is_zero_kilometres_away(self):
        self.make_player("same", "isb-f7")

        (match,) = self.run_search().results

        self.assertIsNotNone(match.distance_km)
        self.assertLess(match.distance_km, 0.5)

    def test_distance_is_a_real_great_circle_figure(self):
        """F-7 to Gulraiz is roughly 19 km; the exact value is not the point, a
        plausible one is."""
        self.make_player("far", "rwp-gulraiz")

        (match,) = self.run_search().results

        self.assertGreater(match.distance_km, 15)
        self.assertLess(match.distance_km, 25)

    def test_the_match_carries_the_public_fields_and_only_those(self):
        self.make_player("other", "isb-f7", level="advanced")

        (match,) = self.run_search().results

        self.assertEqual(
            set(vars(match)),
            {
                "account_id",
                "display_name",
                "playing_level",
                "level_rank",
                "area_name",
                "distance_km",
                "overlapping_slots",
            },
        )
        self.assertEqual(match.display_name, "Other")
        self.assertEqual(match.playing_level, "advanced")
        self.assertEqual(match.area_name, "Islamabad F-7")

    def test_no_match_field_can_hold_a_contact_address(self):
        self.make_player("other", "isb-f7")

        (match,) = self.run_search().results
        blob = " ".join(str(value) for value in vars(match).values())

        self.assertNotIn("@", blob)


class CriteriaTests(MatchingCase):
    """AC1 - M4 decides what a valid search is (rule 14)."""

    def _errors(self, **kwargs):
        defaults = {
            "searcher_id": self.searcher_id,
            "window_start": at(1, 18),
            "window_end": at(1, 20),
            "area_code": "isb-f7",
            "area_centroid": F7,
        }
        defaults.update(kwargs)
        return search.search(**defaults).errors

    def test_a_missing_time_is_named(self):
        self.assertEqual(self._errors(window_start=None), {"start": search.START_REQUIRED})
        self.assertEqual(self._errors(window_end=None), {"end": search.END_REQUIRED})

    def test_an_end_before_the_start_is_rejected(self):
        self.assertEqual(self._errors(window_end=at(1, 17)), {"end": search.END_BEFORE_START})

    def test_a_window_already_past_is_rejected(self):
        self.assertEqual(
            self._errors(window_start=at(-2, 18), window_end=at(-2, 20)),
            {"date": search.WINDOW_IN_PAST},
        )

    def test_a_missing_location_is_rejected(self):
        self.assertEqual(self._errors(area_code=""), {"area_code": search.LOCATION_REQUIRED})

    def test_a_location_outside_the_fixed_list_is_rejected(self):
        self.assertEqual(
            self._errors(area_code="atlantis", area_centroid=None),
            {"area_code": search.LOCATION_INVALID},
        )

    def test_a_search_matching_nobody_is_not_an_error(self):
        outcome = self.run_search()

        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.results, ())


class OneQueryTests(MatchingCase):
    """AC7 - the whole predicate and ranking is a single statement (ASR-01)."""

    def test_the_search_runs_as_one_query_whatever_the_result_count(self):
        for i in range(5):
            self.make_player(f"player{i}", "isb-f7")

        with self.assertNumQueries(1):
            outcome = self.run_search()

        self.assertEqual(len(outcome.results), 5)

    def test_adding_players_does_not_add_queries(self):
        for i in range(20):
            self.make_player(f"player{i}", "isb-f8")

        with self.assertNumQueries(1):
            self.run_search()

    def test_results_are_capped(self):
        self.assertEqual(search.RESULT_LIMIT, 50)
