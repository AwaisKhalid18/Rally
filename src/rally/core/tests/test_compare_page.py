"""The S14 vertical slice end to end - plan.md S14 AC1, AC2, AC3."""
import datetime as _dt

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rally.core import clock
from rally.core.localtime import DATE_FORMAT, parse_local
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.profiles.api import facade as profiles
from rally.modules.safety.api import facade as safety
from rally.modules.search.api import facade as search_api

PASSWORD = "longenough"
ME = "me@example.com"
AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
    {"code": "isb-g9", "name": "Islamabad G-9", "centroid_lat": "33.6889", "centroid_lon": "73.0369"},
]


def local_date(day_offset: int) -> str:
    return (timezone.localtime(clock.now()) + _dt.timedelta(days=day_offset)).strftime(DATE_FORMAT)


class ComparePageCase(TestCase):
    def setUp(self):
        profiles.replace_areas(AREAS)
        self.me = self.make_player(ME, "My Name")
        self.one = self.make_player("one@example.com", "Player One")
        self.two = self.make_player("two@example.com", "Player Two", area="isb-g9")
        self.three = self.make_player("three@example.com", "Player Three")
        self.sign_in(ME)

    def make_player(self, email, name, slots=True, area="isb-f7"):
        account_id = identity.register(email, PASSWORD).account_id
        assert profiles.save_profile(account_id, name, "intermediate", area).ok
        identity.verify_email(identity.get_verification_token(account_id))
        if slots:
            assert availability.add_slot(
                account_id,
                parse_local(local_date(1), "18:00"),
                parse_local(local_date(1), "20:00"),
            ).ok
        return account_id

    def sign_in(self, email):
        self.client.post(reverse("sign_out"))
        self.client.post(reverse("sign_in"), {"email": email, "password": PASSWORD})

    def compare(self, ids):
        return self.client.get(reverse("compare"), {"player": [str(i) for i in ids]})


class TheComparisonTests(ComparePageCase):
    """AC1."""

    def test_nothing_selected_explains_what_to_do(self):
        """FE-6."""
        self.assertContains(self.client.get(reverse("compare")), "Nobody selected yet")

    def test_three_players_appear_side_by_side(self):
        response = self.compare([self.one, self.two, self.three])

        for name in ("Player One", "Player Two", "Player Three"):
            self.assertContains(response, name)

    def test_each_column_shows_level_area_times_and_distance(self):
        response = self.compare([self.one])

        self.assertContains(response, "Intermediate")
        self.assertContains(response, "Islamabad F-7")
        self.assertContains(response, "km away")
        self.assertContains(response, "18:00-20:00")

    def test_the_distance_is_labelled_approximate(self):
        """Rule 7, FE-6: measured between area centres."""
        response = self.compare([self.two])

        self.assertContains(response, "approximate")

    def test_a_player_with_no_times_shows_the_reason(self):
        """AC1, rule 13 - never blank."""
        quiet = self.make_player("quiet@example.com", "Quiet Player", slots=False)

        response = self.compare([quiet])

        self.assertContains(response, "Quiet Player")
        self.assertContains(response, search_api.NO_SLOTS_REASON)

    def test_a_viewer_with_no_area_gets_the_distance_reason_not_a_zero(self):
        """AC1: without a reference point no distance can be worked out."""
        stranger = identity.register("nowhere@example.com", PASSWORD).account_id
        identity.verify_email(identity.get_verification_token(stranger))
        self.sign_in("nowhere@example.com")

        response = self.compare([self.one])

        self.assertContains(response, search_api.NO_DISTANCE_REASON)
        self.assertNotContains(response, "0 km away")

    def test_each_column_offers_an_invitation(self):
        response = self.compare([self.one])

        self.assertContains(
            response, reverse("invitation_new", kwargs={"account_id": self.one})
        )


class TheServerEnforcesTheCapTests(ComparePageCase):
    """AC2."""

    def test_four_players_are_refused_by_the_server(self):
        fourth = self.make_player("four@example.com", "Player Four")

        response = self.compare([self.one, self.two, self.three, fourth])

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, search_api.TOO_MANY, status_code=400)

    def test_three_is_accepted(self):
        response = self.compare([self.one, self.two, self.three])

        self.assertEqual(response.status_code, 200)

    def test_the_page_says_the_limit_before_it_bites(self):
        self.assertContains(self.client.get(reverse("compare")), "up to 3")

    def test_comparing_yourself_is_refused(self):
        response = self.compare([self.me, self.one])

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, search_api.CANNOT_COMPARE_YOURSELF, status_code=400)

    def test_search_results_offer_a_compare_checkbox(self):
        response = self.client.get(
            reverse("search"),
            {"date": local_date(1), "start": "18:00", "end": "20:00", "area_code": "isb-f7"},
        )

        self.assertContains(response, 'name="player"')
        self.assertContains(response, 'form="compare-form"')

    def test_the_compare_form_does_not_nest_inside_the_cards(self):
        """The cards hold POST forms for favoriting and blocking, and forms may not
        nest - the checkboxes join the comparison form by its id instead."""
        response = self.client.get(
            reverse("search"),
            {"date": local_date(1), "start": "18:00", "end": "20:00", "area_code": "isb-f7"},
        )

        body = response.content.decode()
        self.assertEqual(body.count("<form"), body.count("</form>"))
        # The comparison form opens after the last result card closes.
        self.assertLess(body.rindex("</li>"), body.index('id="compare-form"'))


class RemovingIsANewRequestTests(ComparePageCase):
    """AC2 - 'removing/replacing is a new request; nothing is stored'."""

    def test_each_column_offers_a_link_that_drops_it(self):
        response = self.compare([self.one, self.two])

        body = response.content.decode()
        self.assertIn(f"{reverse('compare')}?player={self.two}", body)
        self.assertIn(f"{reverse('compare')}?player={self.one}", body)

    def test_the_comparison_is_not_remembered_between_requests(self):
        self.compare([self.one, self.two])

        response = self.client.get(reverse("compare"))

        self.assertContains(response, "Nobody selected yet")
        self.assertNotContains(response, "Player One")

    def test_it_is_a_get_because_it_changes_nothing(self):
        """A read, so a GET is right here - FE-9 forbids state changes on GET, and
        this changes none."""
        self.assertEqual(self.compare([self.one]).status_code, 200)
        self.assertEqual(
            self.client.post(reverse("compare"), {"player": str(self.one)}).status_code, 405
        )


class BlockedAndMissingLookTheSameTests(ComparePageCase):
    """AC3."""

    def test_a_blocked_player_shows_as_no_longer_available(self):
        safety.block(self.me, self.one)

        response = self.compare([self.one])

        self.assertContains(response, search_api.NOT_FOUND_REASON)
        self.assertNotContains(response, "Player One")

    def test_an_account_that_does_not_exist_shows_the_same(self):
        response = self.compare([999999])

        self.assertContains(response, search_api.NOT_FOUND_REASON)

    def test_the_two_pages_are_identical_apart_from_the_id(self):
        safety.block(self.me, self.one)

        blocked = self.compare([self.one]).content.decode().replace(str(self.one), "X")
        missing = self.compare([999999]).content.decode().replace("999999", "X")

        # The CSRF token differs per response, so compare what the page says instead.
        self.assertEqual(blocked.count(search_api.NOT_FOUND_REASON),
                         missing.count(search_api.NOT_FOUND_REASON))
        self.assertNotIn("Player One", blocked)

    def test_the_rest_of_the_comparison_still_works(self):
        safety.block(self.me, self.one)

        response = self.compare([self.one, self.two])

        self.assertContains(response, search_api.NOT_FOUND_REASON)
        self.assertContains(response, "Player Two")


class PrivacyTests(ComparePageCase):
    """ASR-04, rules 6 and 7."""

    def test_no_contact_address_appears_on_the_page(self):
        self.assertNotIn("@", self.compare([self.one, self.two]).content.decode())

    def test_no_coordinate_appears_on_the_page(self):
        body = self.compare([self.one, self.two]).content.decode()

        for coordinate in ("33.7211", "73.0551", "33.6889", "73.0369"):
            self.assertNotIn(coordinate, body)

    def test_the_page_needs_a_session_and_is_not_cached(self):
        """FE-3, FE-9."""
        self.assertIn("no-store", self.compare([self.one])["Cache-Control"])

        self.client.post(reverse("sign_out"))
        response = self.client.get(reverse("compare"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("sign_in"), response["Location"])
