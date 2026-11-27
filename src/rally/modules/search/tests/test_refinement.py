"""M4's optional filters and the full ranking - plan.md S6 AC1 and AC2."""
import datetime as _dt
import math

from django.test import TestCase

from rally.core import clock
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.profiles.api import facade as profiles
from rally.modules.search.api import facade as search
from rally.modules.search.internal.query import KM_PER_DEGREE_LATITUDE, bounding_box

PASSWORD = "longenough"
REF_LAT, REF_LON = 33.0000, 73.0000
F7 = (REF_LAT, REF_LON)


def area_at_km(code: str, km: float) -> dict:
    """An area exactly `km` north of the reference point.

    Along a meridian the great-circle distance is R times the latitude difference, so
    the separation is exact by construction rather than approximated.
    """
    return {
        "code": code,
        "name": f"Area {code}",
        "centroid_lat": f"{REF_LAT + km / KM_PER_DEGREE_LATITUDE:.4f}",
        "centroid_lon": f"{REF_LON:.4f}",
    }


# 4 decimal places of latitude is ~11 m, so the codes below are accurate to about that.
AREAS = [
    {"code": "here", "name": "Area here", "centroid_lat": f"{REF_LAT:.4f}", "centroid_lon": f"{REF_LON:.4f}"},
    area_at_km("km3", 3),
    area_at_km("km8", 8),
    area_at_km("km10", 10),
    area_at_km("km12", 12),
    area_at_km("km30", 30),
]


def at(day_offset: int, hour: int) -> _dt.datetime:
    # Anchored on midnight, not on "now": re-reading the clock per call made the
    # fixture and the search window disagree whenever the hour rolled over mid-test.
    midnight = clock.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + _dt.timedelta(days=day_offset, hours=hour)


class RefinementCase(TestCase):
    def setUp(self):
        profiles.replace_areas(AREAS)
        self.searcher_id = self.make_player("searcher", "here", level="intermediate", slot=None)

    def make_player(self, name, area_code, level="intermediate", slot=(1, 18, 20)):
        account_id = identity.register(f"{name}@example.com", PASSWORD).account_id
        saved = profiles.save_profile(account_id, name.title(), level, area_code)
        # Fail loudly here rather than silently producing a player with no profile,
        # which would then be invisible to search for the right reason and make the
        # real assertion lie. (Display names must be at least 2 characters.)
        assert saved.ok, saved.errors
        identity.verify_email(identity.get_verification_token(account_id))
        if slot:
            day, start, end = slot
            availability.add_slot(account_id, at(day, start), at(day, end))
        return account_id

    def run_search(self, **filters):
        return search.search(
            searcher_id=self.searcher_id,
            window_start=at(1, 18),
            window_end=at(1, 20),
            area_code="here",
            area_centroid=F7,
            **filters,
        )


class LevelFilterTests(RefinementCase):
    """AC1 - the level filter is optional; omitted means every level."""

    def setUp(self):
        super().setUp()
        self.beginner = self.make_player("bravo", "here", level="beginner")
        self.intermediate = self.make_player("india", "here", level="intermediate")
        self.advanced = self.make_player("alfa", "here", level="advanced")

    def test_omitting_the_level_returns_every_level(self):
        found = {m.account_id for m in self.run_search().results}

        self.assertEqual(found, {self.beginner, self.intermediate, self.advanced})

    def test_an_empty_level_is_the_same_as_omitting_it(self):
        self.assertEqual(len(self.run_search(playing_level="").results), 3)

    def test_choosing_a_level_returns_only_that_level(self):
        found = [m.account_id for m in self.run_search(playing_level="advanced").results]

        self.assertEqual(found, [self.advanced])

    def test_a_level_outside_the_three_is_rejected(self):
        outcome = self.run_search(playing_level="professional")

        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.errors, {"playing_level": search.LEVEL_INVALID})

    def test_the_level_choices_are_the_prd_vocabulary(self):
        self.assertEqual(search.PLAYING_LEVELS, ("beginner", "intermediate", "advanced"))


class MaxDistanceTests(RefinementCase):
    """AC1 - 5/10/20/50 km, default 10, at the limit in and just over out."""

    def test_the_default_is_ten_kilometres(self):
        self.assertEqual(search.DEFAULT_MAX_DISTANCE_KM, 10)
        self.assertEqual(search.DISTANCE_CHOICES_KM, (5, 10, 20, 50))

    def test_a_player_beyond_the_default_is_excluded(self):
        self.make_player("far", "km12")

        self.assertEqual(self.run_search().results, ())

    def test_a_player_inside_the_default_is_included(self):
        near = self.make_player("near", "km8")

        self.assertEqual([m.account_id for m in self.run_search().results], [near])

    def test_a_wider_choice_reaches_further(self):
        far = self.make_player("far", "km30")

        self.assertEqual(self.run_search(max_distance_km=20).results, ())
        self.assertEqual([m.account_id for m in self.run_search(max_distance_km=50).results], [far])

    def test_a_narrower_choice_reaches_less_far(self):
        self.make_player("mid", "km8")

        self.assertEqual(self.run_search(max_distance_km=5).results, ())

    def test_the_limit_is_inclusive(self):
        """AC1 - 'a player exactly at the limit is included'.

        The area is built to sit exactly 10 km out, but a float comparison at the
        boundary is only as exact as the stored centroid, so the test asserts the
        *semantics*: the player is returned if and only if the distance the query
        itself computed is within the limit.
        """
        at_limit = self.make_player("limit", "km10")

        measured = self.run_search(max_distance_km=50).results[0].distance_km
        included = [m.account_id for m in self.run_search(max_distance_km=10).results]

        self.assertAlmostEqual(measured, 10.0, places=1)
        self.assertEqual(included == [at_limit], measured <= 10)

    def test_a_player_just_over_the_limit_is_excluded(self):
        self.make_player("over", "km12")

        self.assertEqual(self.run_search(max_distance_km=10).results, ())

    def test_a_distance_outside_the_four_choices_is_rejected(self):
        for bad in (7, 0, -5, 100, "ten"):
            with self.subTest(value=bad):
                outcome = self.run_search(max_distance_km=bad)
                self.assertFalse(outcome.ok)
                self.assertEqual(outcome.errors, {"max_distance_km": search.DISTANCE_INVALID})


class FiltersCombineTests(RefinementCase):
    """AC2 - the filters apply together (logical AND)."""

    def test_level_and_distance_must_both_pass(self):
        near_right = self.make_player("nearright", "km3", level="advanced")
        self.make_player("nearwrong", "km3", level="beginner")
        self.make_player("farright", "km30", level="advanced")

        found = [
            m.account_id
            for m in self.run_search(playing_level="advanced", max_distance_km=10).results
        ]

        self.assertEqual(found, [near_right])

    def test_a_blocked_player_is_excluded_whatever_the_filters_allow(self):
        from rally.modules.safety.api import facade as safety

        other = self.make_player("blocked", "km3", level="advanced")
        safety.block_for_test(self.searcher_id, other)

        self.assertEqual(self.run_search(playing_level="advanced").results, ())

    def test_the_time_window_still_applies(self):
        self.make_player("elsewhen", "km3", level="advanced", slot=(2, 18, 20))

        self.assertEqual(self.run_search(playing_level="advanced").results, ())


class RankingTests(RefinementCase):
    """AC2 - distance, then level closeness, then earliest overlap."""

    def test_distance_comes_first(self):
        far = self.make_player("far", "km8", level="intermediate")
        near = self.make_player("near", "km3", level="advanced")

        order = [m.account_id for m in self.run_search().results]

        self.assertEqual(order, [near, far])

    def test_level_closeness_breaks_a_distance_tie(self):
        """The searcher is Intermediate, so Intermediate beats Beginner and Advanced."""
        advanced = self.make_player("alfa", "km3", level="advanced")
        same = self.make_player("india", "km3", level="intermediate")

        order = [m.account_id for m in self.run_search().results]

        self.assertEqual(order, [same, advanced])

    def test_a_beginner_searcher_ranks_beginners_first(self):
        beginner_searcher = self.make_player("beginnersearcher", "here", level="beginner", slot=None)
        advanced = self.make_player("alfa", "km3", level="advanced")
        beginner = self.make_player("bravo", "km3", level="beginner")

        outcome = search.search(
            searcher_id=beginner_searcher,
            window_start=at(1, 18),
            window_end=at(1, 20),
            area_code="here",
            area_centroid=F7,
        )

        self.assertEqual([m.account_id for m in outcome.results][:2], [beginner, advanced])

    def test_earliest_overlap_breaks_a_distance_and_level_tie(self):
        later = self.make_player("later", "km3", slot=(1, 19, 21))
        earlier = self.make_player("earlier", "km3", slot=(1, 17, 20))

        outcome = search.search(
            searcher_id=self.searcher_id,
            window_start=at(1, 17),
            window_end=at(1, 21),
            area_code="here",
            area_centroid=F7,
        )

        self.assertEqual([m.account_id for m in outcome.results], [earlier, later])

    def test_a_searcher_without_a_profile_still_gets_distance_ordering(self):
        """The closeness term collapses to zero rather than failing."""
        no_profile = identity.register("bare@example.com", PASSWORD).account_id
        far = self.make_player("far", "km8")
        near = self.make_player("near", "km3")

        outcome = search.search(
            searcher_id=no_profile,
            window_start=at(1, 18),
            window_end=at(1, 20),
            area_code="here",
            area_centroid=F7,
        )

        self.assertEqual([m.account_id for m in outcome.results], [near, far])


class BoundingBoxTests(TestCase):
    """ASR-01 - a cheap box narrows the scan before the great-circle arithmetic."""

    def test_the_box_contains_everything_within_the_radius(self):
        box = bounding_box(REF_LAT, REF_LON, 10)

        self.assertLess(box["lat_min"], REF_LAT)
        self.assertGreater(box["lat_max"], REF_LAT)
        # A point exactly 10 km north must still be inside the box.
        self.assertGreaterEqual(box["lat_max"], REF_LAT + 10 / KM_PER_DEGREE_LATITUDE)

    def test_the_longitude_span_widens_away_from_the_equator(self):
        near_equator = bounding_box(0.0, 0.0, 10)
        far_north = bounding_box(60.0, 0.0, 10)

        self.assertGreater(
            far_north["lon_max"] - far_north["lon_min"],
            near_equator["lon_max"] - near_equator["lon_min"],
        )

    def test_the_longitude_bound_is_dropped_at_the_pole(self):
        self.assertTrue(bounding_box(89.999, 0.0, 50)["lon_wraps"])

    def test_the_longitude_bound_is_dropped_across_the_antimeridian(self):
        self.assertTrue(bounding_box(0.0, 179.99, 50)["lon_wraps"])

    def test_the_box_is_never_smaller_than_the_radius_it_must_cover(self):
        for radius in (5, 10, 20, 50):
            with self.subTest(radius=radius):
                box = bounding_box(33.0, 73.0, radius)
                span_km = (box["lat_max"] - box["lat_min"]) / 2 * KM_PER_DEGREE_LATITUDE
                self.assertGreaterEqual(round(span_km, 6), radius)


class StillOneQueryTests(RefinementCase):
    """ASR-01 - the filters and the searcher's own level rank stay in one statement."""

    def test_a_filtered_search_is_still_one_query(self):
        for i in range(5):
            self.make_player(f"p{i}", "km3", level="advanced")

        with self.assertNumQueries(1):
            outcome = self.run_search(playing_level="advanced", max_distance_km=20)

        self.assertEqual(len(outcome.results), 5)


class MathCheck(TestCase):
    def test_a_degree_of_latitude_matches_the_earth_radius_used_in_sql(self):
        self.assertAlmostEqual(KM_PER_DEGREE_LATITUDE, math.pi * 6371.0 / 180.0, places=9)
