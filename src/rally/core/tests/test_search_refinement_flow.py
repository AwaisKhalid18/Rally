"""The S6 vertical slice end to end - plan.md S6 AC1, AC2, AC3."""
import datetime as _dt

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rally.core import clock
from rally.core.localtime import DATE_FORMAT, parse_local
from rally.core.shapers.search import no_results_guidance
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.notification.api import facade as notification
from rally.modules.profiles.api import facade as profiles
from rally.modules.search.api import facade as search_api
from rally.modules.search.internal.query import KM_PER_DEGREE_LATITUDE

PASSWORD = "longenough"
SEARCHER = "searcher@example.com"
REF_LAT, REF_LON = 33.0, 73.0


def area_at_km(code: str, km: float) -> dict:
    return {
        "code": code,
        "name": f"Area {code}",
        "centroid_lat": f"{REF_LAT + km / KM_PER_DEGREE_LATITUDE:.4f}",
        "centroid_lon": f"{REF_LON:.4f}",
    }


AREAS = [
    {"code": "here", "name": "Area here", "centroid_lat": "33.0000", "centroid_lon": "73.0000"},
    area_at_km("km3", 3),
    area_at_km("km30", 30),
]


def local_date(day_offset: int) -> str:
    return (timezone.localtime(clock.now()) + _dt.timedelta(days=day_offset)).strftime(DATE_FORMAT)


class RefinementFlowCase(TestCase):
    def setUp(self):
        previous = notification.set_email_adapter(notification.RecordingEmailAdapter())
        self.addCleanup(notification.set_email_adapter, previous)
        profiles.replace_areas(AREAS)

        self.searcher_id = identity.register(SEARCHER, PASSWORD).account_id
        profiles.save_profile(self.searcher_id, "Searcher", "intermediate", "here")
        identity.verify_email(identity.get_verification_token(self.searcher_id))
        self.client.post(reverse("sign_in"), {"email": SEARCHER, "password": PASSWORD})

    def add_player(self, name, area="km3", level="advanced"):
        account_id = identity.register(f"{name}@example.com", PASSWORD).account_id
        saved = profiles.save_profile(account_id, name.title(), level, area)
        assert saved.ok, saved.errors
        identity.verify_email(identity.get_verification_token(account_id))
        availability.add_slot(
            account_id,
            parse_local(local_date(1), "18:00"),
            parse_local(local_date(1), "20:00"),
        )
        return account_id

    def search(self, **overrides):
        params = {
            "date": local_date(1),
            "start": "18:00",
            "end": "20:00",
            "area_code": "here",
        }
        params.update(overrides)
        return self.client.get(reverse("search"), params)


class FilterControlsTests(RefinementFlowCase):
    """AC1 - the two optional controls are on the form and are honoured."""

    def test_the_form_offers_any_level_and_the_four_distances(self):
        body = self.client.get(reverse("search")).content.decode()

        self.assertIn("Any level", body)
        for level in ("Beginner", "Intermediate", "Advanced"):
            self.assertIn(level, body)
        for km in (5, 10, 20, 50):
            self.assertIn(f"{km} km", body)

    def test_ten_kilometres_is_preselected(self):
        body = self.client.get(reverse("search")).content.decode()

        self.assertIn('<option value="10" selected>10 km</option>', body)

    def test_the_level_filter_narrows_the_results(self):
        self.add_player("adv", level="advanced")
        self.add_player("beg", level="beginner")

        body = self.search(playing_level="advanced").content.decode()

        self.assertIn("Adv", body)
        self.assertNotIn("Beg<", body)

    def test_the_distance_filter_narrows_the_results(self):
        self.add_player("far", area="km30")

        self.assertContains(self.search(max_distance_km="50"), "Far")
        self.assertContains(self.search(max_distance_km="20"), "No players match")

    def test_an_invalid_level_is_rejected_and_the_criteria_are_kept(self):
        response = self.search(playing_level="professional")

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, search_api.LEVEL_INVALID, status_code=400)
        self.assertContains(response, 'value="18:00"', status_code=400)

    def test_an_invalid_distance_is_rejected(self):
        response = self.search(max_distance_km="7")

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, search_api.DISTANCE_INVALID, status_code=400)

    def test_the_chosen_filters_are_echoed_back(self):
        body = self.search(playing_level="advanced", max_distance_km="20").content.decode()

        self.assertIn('<option value="advanced" selected>Advanced</option>', body)
        self.assertIn('<option value="20" selected>20 km</option>', body)


class NoResultsGuidanceTests(RefinementFlowCase):
    """AC3 - the message names the filters that were actually used, and nothing widens."""

    def test_the_base_message_suggests_date_time_and_area(self):
        body = self.search().content.decode()

        self.assertIn("No players match that search", body)
        self.assertIn("a different date", body)
        self.assertIn("a wider time window", body)
        self.assertIn("another area", body)
        self.assertNotIn("any playing level", body)
        self.assertNotIn("a larger maximum distance", body)

    def test_using_the_level_filter_adds_it_to_the_suggestions(self):
        body = self.search(playing_level="advanced").content.decode()

        self.assertIn("any playing level", body)
        self.assertNotIn("a larger maximum distance", body)

    def test_using_the_distance_filter_adds_it_to_the_suggestions(self):
        body = self.search(max_distance_km="5").content.decode()

        self.assertIn("a larger maximum distance", body)
        self.assertNotIn("any playing level", body)

    def test_using_both_mentions_both(self):
        body = self.search(playing_level="beginner", max_distance_km="5").content.decode()

        self.assertIn("any playing level", body)
        self.assertIn("a larger maximum distance", body)

    def test_nothing_is_widened_silently(self):
        """FE-7 - the criteria come back exactly as submitted."""
        self.add_player("far", area="km30")

        response = self.search(max_distance_km="5")

        self.assertContains(response, "No players match")
        self.assertContains(response, '<option value="5" selected>5 km</option>')
        self.assertNotContains(response, "Far")

    def test_the_guidance_reads_as_a_sentence(self):
        self.assertEqual(
            no_results_guidance(level_used=False, distance_used=False),
            "No players match that search. Try a different date, a wider time window "
            "or another area.",
        )
        self.assertEqual(
            no_results_guidance(level_used=True, distance_used=True),
            "No players match that search. Try a different date, a wider time window, "
            "another area, any playing level or a larger maximum distance.",
        )


class RankingOnThePageTests(RefinementFlowCase):
    """AC2 - the order the player sees."""

    def test_the_nearest_player_is_listed_first(self):
        self.add_player("near", area="km3")
        far_area = area_at_km("km8", 8)
        profiles.replace_areas([far_area])
        self.add_player("far", area="km8")

        body = self.search().content.decode()

        self.assertLess(body.index("Near"), body.index("Far"))

    def test_at_the_same_distance_the_closer_level_is_first(self):
        # Names deliberately unlike the level words: the form lists every level in its
        # <option>s, so matching on "Advanced" would find the filter, not the card.
        self.add_player("zulu", area="km3", level="advanced")
        self.add_player("yankee", area="km3", level="intermediate")

        body = self.search().content.decode()

        self.assertLess(body.index("Yankee"), body.index("Zulu"))
