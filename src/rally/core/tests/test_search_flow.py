"""The S5 vertical slice end to end - plan.md S5 AC1, AC3, AC5, AC6."""
import datetime as _dt

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rally.core import clock
from rally.core.localtime import DATE_FORMAT, parse_local
from rally.core.shapers.search import DISTANCE_UNAVAILABLE, result_view
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.notification.api import facade as notification
from rally.modules.profiles.api import facade as profiles
from rally.modules.search.api.facade import Match, MatchedSlot

PASSWORD = "longenough"
SEARCHER = "searcher@example.com"
PARTNER = "partner@example.com"
AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
    {"code": "isb-f8", "name": "Islamabad F-8", "centroid_lat": "33.7006", "centroid_lon": "73.0387"},
]


def at(day_offset: int, hour: int) -> _dt.datetime:
    base = clock.now().replace(minute=0, second=0, microsecond=0)
    return base + _dt.timedelta(days=day_offset, hours=hour - base.hour)


def local_date(day_offset: int) -> str:
    return (timezone.localtime(clock.now()) + _dt.timedelta(days=day_offset)).strftime(DATE_FORMAT)


class SearchFlowCase(TestCase):
    def setUp(self):
        previous = notification.set_email_adapter(notification.RecordingEmailAdapter())
        self.addCleanup(notification.set_email_adapter, previous)
        profiles.replace_areas(AREAS)

        self.searcher_id = identity.register(SEARCHER, PASSWORD).account_id
        profiles.save_profile(self.searcher_id, "Searcher", "intermediate", "isb-f7")
        identity.verify_email(identity.get_verification_token(self.searcher_id))
        self.client.post(reverse("sign_in"), {"email": SEARCHER, "password": PASSWORD})

    def add_partner(self, email=PARTNER, name="Partner", area="isb-f8", level="advanced"):
        account_id = identity.register(email, PASSWORD).account_id
        profiles.save_profile(account_id, name, level, area)
        identity.verify_email(identity.get_verification_token(account_id))
        # The slot has to be built the way the player would type it, through the same
        # local-to-UTC conversion the search form uses - otherwise the fixture and the
        # window are in different time zones and nothing matches.
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
            "area_code": "isb-f7",
        }
        params.update(overrides)
        return self.client.get(reverse("search"), params)


class SearchPageTests(SearchFlowCase):
    def test_the_page_needs_a_session(self):
        """AC5 - an unauthenticated request gets no data."""
        self.client.post(reverse("sign_out"))

        response = self.search()

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("sign_in"), response.headers["Location"])

    def test_the_empty_form_offers_the_fixed_area_list(self):
        response = self.client.get(reverse("search"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Islamabad F-7")
        self.assertNotContains(response, "Results")

    def test_a_matching_player_is_shown_with_everything_needed_to_decide(self):
        """AC3 and ASR-13 - one round trip, no follow-up call per player."""
        self.add_partner()

        response = self.search()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Partner")
        self.assertContains(response, "Advanced")
        self.assertContains(response, "Islamabad F-8")
        self.assertContains(response, "18:00-20:00")
        self.assertContains(response, "km away")

    def test_the_distance_is_rounded_and_labelled_approximate(self):
        self.add_partner()

        body = self.search().content.decode()

        self.assertIn("about", body)
        self.assertRegex(body, r"about \d+ km away")

    def test_each_card_offers_an_invite_entry_point(self):
        """AC5 - wired to the invitation form in S7."""
        partner_id = self.add_partner()

        response = self.search()

        self.assertContains(response, "Invite")
        self.assertContains(response, reverse("player_profile", kwargs={"account_id": partner_id}))

    def test_no_results_shows_guidance_with_the_criteria_unchanged(self):
        """FR-13, FE-7 - never widened silently."""
        response = self.search()

        self.assertContains(response, "No players match that search")
        self.assertContains(response, f'value="{local_date(1)}"')
        self.assertContains(response, 'value="18:00"')


class MandatoryCriteriaTests(SearchFlowCase):
    """AC1 - date, time window and location are mandatory."""

    def test_a_missing_date_is_named_and_what_was_typed_is_kept(self):
        response = self.search(date="")

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Choose a date.", status_code=400)
        self.assertContains(response, 'value="18:00"', status_code=400)

    def test_a_missing_start_time_is_named(self):
        self.assertContains(self.search(start=""), "Choose a time to play from.", status_code=400)

    def test_a_missing_end_time_is_named(self):
        self.assertContains(self.search(end=""), "Choose a time to play until.", status_code=400)

    def test_a_missing_area_is_named(self):
        self.assertContains(self.search(area_code=""), "Choose the area", status_code=400)

    def test_an_area_outside_the_fixed_list_is_rejected(self):
        self.assertContains(self.search(area_code="atlantis"), "from the list", status_code=400)

    def test_a_window_in_the_past_is_rejected(self):
        self.assertContains(self.search(date=local_date(-2)), "already passed", status_code=400)

    def test_a_rejected_search_keeps_every_criterion_as_typed(self):
        response = self.search(date="")

        for value in ("18:00", "20:00", "isb-f7"):
            self.assertContains(response, value, status_code=400)


class PrivacyTests(SearchFlowCase):
    """AC6 - no email, phone or exact location anywhere in the response."""

    def test_the_results_page_carries_no_contact_data_or_coordinates(self):
        partner_id = self.add_partner()
        identity.set_phone(partner_id, "03001234567")

        body = self.search().content.decode()

        self.assertNotIn(PARTNER, body)
        self.assertNotIn("@", body)
        self.assertNotIn("03001234567", body)
        self.assertNotIn("33.70", body)
        self.assertNotIn("73.03", body)

    def test_no_contact_address_reaches_a_log_line(self):
        self.add_partner()

        with self.assertLogs("rally.operation", level="INFO") as captured:
            self.search()

        written = "\n".join(captured.output)
        self.assertIn("operation=search.run outcome=done", written)
        self.assertNotIn("@", written)


class DistanceShaperTests(TestCase):
    """Rule 13 and FE-6 - an unavailable distance is absent with a reason, never 0."""

    def _match(self, distance_km):
        return Match(
            account_id=7,
            display_name="Someone",
            playing_level="beginner",
            level_rank=1,
            area_name="Islamabad F-7",
            distance_km=distance_km,
            overlapping_slots=(MatchedSlot(starts_at=at(1, 18), ends_at=at(1, 20)),),
        )

    def test_an_absent_distance_carries_a_reason_and_no_number(self):
        view = result_view(self._match(None))

        self.assertIsNone(view.distance_text)
        self.assertEqual(view.distance_reason, DISTANCE_UNAVAILABLE)

    def test_a_present_distance_is_rounded_to_the_nearest_kilometre(self):
        self.assertEqual(result_view(self._match(4.4)).distance_text, "about 4 km away")
        self.assertEqual(result_view(self._match(4.6)).distance_text, "about 5 km away")

    def test_a_player_in_the_same_area_is_not_hidden_behind_a_zero(self):
        view = result_view(self._match(0.0))

        self.assertEqual(view.distance_text, "about 0 km away")
        self.assertIsNone(view.distance_reason)
