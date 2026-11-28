"""The S15 vertical slice end to end - plan.md S15 AC1, AC2, AC3."""
import datetime as _dt

from django.test import TestCase
from django.urls import reverse

from rally.core import clock
from rally.core.localtime import DATE_FORMAT, parse_local, to_local
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.player_collections.api import facade as collections
from rally.modules.profiles.api import facade as profiles

PASSWORD = "longenough"
ME = "me@example.com"
OTHER = "other@example.com"
def today_locally():
    """Today in the display time zone - Platform's own clock, not M8's internals,
    which Platform may not import (rule 2)."""
    return to_local(clock.now()).date()


AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
    {"code": "isb-g9", "name": "Islamabad G-9", "centroid_lat": "33.6889", "centroid_lon": "73.0369"},
]


class SavedSearchPageCase(TestCase):
    def setUp(self):
        profiles.replace_areas(AREAS)
        self.me = self.make_player(ME, "My Name")
        self.other = self.make_player(OTHER, "Other Name")
        self.sign_in(ME)

    def make_player(self, email, name, slots=True):
        account_id = identity.register(email, PASSWORD).account_id
        assert profiles.save_profile(account_id, name, "intermediate", "isb-f7").ok
        identity.verify_email(identity.get_verification_token(account_id))
        if slots:
            tomorrow = (today_locally() + _dt.timedelta(days=1)).strftime(DATE_FORMAT)
            assert availability.add_slot(
                account_id, parse_local(tomorrow, "09:00"), parse_local(tomorrow, "11:00")
            ).ok
        return account_id

    def sign_in(self, email):
        self.client.post(reverse("sign_out"))
        self.client.post(reverse("sign_in"), {"email": email, "password": PASSWORD})

    def form(self, **overrides):
        values = {
            "name": "Tomorrow mornings",
            "day_kind": "rule",
            "day_rule": "tomorrow",
            "fixed_date": "",
            "start": "09:00",
            "end": "11:00",
            "area_code": "isb-f7",
            "playing_level": "",
            "max_distance_km": "",
        }
        values.update(overrides)
        return values

    def create(self, **overrides):
        return self.client.post(reverse("saved_search_new"), self.form(**overrides))

    def page(self):
        return self.client.get(reverse("saved_searches"))

    def only(self, owner=None):
        return collections.list_searches(owner or self.me)[0]


class SavingThroughThePageTests(SavedSearchPageCase):
    """AC1."""

    def test_an_empty_list_explains_itself(self):
        """FE-6."""
        self.assertContains(self.page(), "no saved searches yet")

    def test_a_search_can_be_saved_and_appears_on_the_list(self):
        response = self.create()

        self.assertRedirects(response, reverse("saved_searches"))
        page = self.page()
        self.assertContains(page, "Tomorrow mornings")
        self.assertContains(page, "1 of 20")

    def test_the_criteria_are_shown_back(self):
        self.create(playing_level="advanced", max_distance_km="20")

        page = self.page()

        self.assertContains(page, "09:00-11:00")
        self.assertContains(page, "Islamabad F-7")
        self.assertContains(page, "Advanced")
        self.assertContains(page, "within 20 km")

    def test_a_search_without_optional_filters_says_so_rather_than_blank(self):
        """FE-6, rule 13."""
        self.create()

        page = self.page()

        self.assertContains(page, "Any level")
        self.assertContains(page, "the default distance")

    def test_a_refused_save_shows_the_reason_and_keeps_what_was_typed(self):
        response = self.create(name="")

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, collections.NAME_REQUIRED, status_code=400)
        self.assertContains(response, 'value="09:00"', status_code=400)

    def test_an_unparseable_date_is_reported(self):
        response = self.create(day_kind="date", fixed_date="not-a-date")

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "YYYY-MM-DD", status_code=400)

    def test_saving_does_not_run_a_search(self):
        """Architecture 16.8: editing is an M8 write and never triggers a search."""
        response = self.create()

        self.assertRedirects(response, reverse("saved_searches"))
        self.assertNotIn(reverse("search"), response["Location"])


class EditingAndDeletingTests(SavedSearchPageCase):
    """AC1 and AC3."""

    def test_the_edit_form_is_filled_with_what_was_saved(self):
        self.create(playing_level="advanced")
        record = self.only()

        response = self.client.get(
            reverse("saved_search_edit", kwargs={"saved_search_id": record.saved_search_id})
        )

        self.assertContains(response, 'value="Tomorrow mornings"')
        self.assertContains(response, 'value="09:00"')
        self.assertContains(response, "selected")

    def test_editing_changes_it(self):
        self.create()
        record = self.only()

        self.client.post(
            reverse("saved_search_edit", kwargs={"saved_search_id": record.saved_search_id}),
            self.form(name="Renamed", start="18:00", end="20:00"),
        )

        page = self.page()
        self.assertContains(page, "Renamed")
        self.assertContains(page, "18:00-20:00")

    def test_another_players_search_is_a_not_found(self):
        """ASR-05."""
        self.create()
        record = self.only()
        self.sign_in(OTHER)

        response = self.client.get(
            reverse("saved_search_edit", kwargs={"saved_search_id": record.saved_search_id})
        )

        self.assertEqual(response.status_code, 404)

    def test_deleting_removes_it(self):
        self.create()
        record = self.only()

        response = self.client.post(
            reverse("saved_search_delete", kwargs={"saved_search_id": record.saved_search_id}),
            follow=True,
        )

        self.assertContains(response, "Deleted.")
        self.assertContains(response, "no saved searches yet")

    def test_deleting_is_not_reachable_by_get(self):
        """FE-9."""
        self.create()
        record = self.only()

        response = self.client.get(
            reverse("saved_search_delete", kwargs={"saved_search_id": record.saved_search_id})
        )

        self.assertEqual(response.status_code, 405)
        self.assertEqual(collections.count_searches(self.me), 1)

    def test_another_player_cannot_delete_it_by_posting_directly(self):
        self.create()
        record = self.only()
        self.sign_in(OTHER)

        self.client.post(
            reverse("saved_search_delete", kwargs={"saved_search_id": record.saved_search_id})
        )

        self.assertEqual(collections.count_searches(self.me), 1)

    def test_one_players_list_is_not_anothers(self):
        self.create()
        self.sign_in(OTHER)

        self.assertContains(self.page(), "no saved searches yet")


class ReusingASearchTests(SavedSearchPageCase):
    """AC2 - the composition this slice exists for."""

    def test_running_it_lands_on_the_search_results_with_the_criteria(self):
        self.create()
        record = self.only()

        response = self.client.get(
            reverse("saved_search_run", kwargs={"saved_search_id": record.saved_search_id})
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("search"), response["Location"])
        tomorrow = (today_locally() + _dt.timedelta(days=1)).strftime(DATE_FORMAT)
        self.assertIn(f"date={tomorrow}", response["Location"])
        self.assertIn("area_code=isb-f7", response["Location"])

    def test_the_results_are_the_ones_a_typed_search_would_give(self):
        """M8 hands the criteria to M4's ordinary entry point (rule 12)."""
        self.create()
        record = self.only()

        response = self.client.get(
            reverse("saved_search_run", kwargs={"saved_search_id": record.saved_search_id}),
            follow=True,
        )

        self.assertContains(response, "Other Name")

    def test_the_criteria_are_echoed_back_unchanged(self):
        """FR-13, FE-7."""
        self.create()
        record = self.only()

        response = self.client.get(
            reverse("saved_search_run", kwargs={"saved_search_id": record.saved_search_id}),
            follow=True,
        )

        self.assertContains(response, 'value="09:00"')
        self.assertContains(response, 'value="11:00"')

    def test_a_past_fixed_date_is_not_run_and_says_why(self):
        """AC2, G-05 - never silently shifted to today."""
        yesterday = (today_locally() - _dt.timedelta(days=1)).strftime(DATE_FORMAT)
        self.create(day_kind="date", fixed_date=yesterday, day_rule="")
        record = self.only()

        response = self.client.get(
            reverse("saved_search_run", kwargs={"saved_search_id": record.saved_search_id}),
            follow=True,
        )

        self.assertContains(response, collections.NEEDS_A_NEW_DATE)
        self.assertNotIn(reverse("search"), response.redirect_chain[-1][0])

    def test_such_a_search_offers_no_run_button(self):
        yesterday = (today_locally() - _dt.timedelta(days=1)).strftime(DATE_FORMAT)
        self.create(day_kind="date", fixed_date=yesterday, day_rule="")
        record = self.only()

        page = self.page()

        self.assertContains(page, collections.NEEDS_A_NEW_DATE)
        self.assertNotContains(
            page, reverse("saved_search_run", kwargs={"saved_search_id": record.saved_search_id})
        )

    def test_giving_it_a_new_date_makes_it_runnable_again(self):
        yesterday = (today_locally() - _dt.timedelta(days=1)).strftime(DATE_FORMAT)
        self.create(day_kind="date", fixed_date=yesterday, day_rule="")
        record = self.only()

        tomorrow = (today_locally() + _dt.timedelta(days=1)).strftime(DATE_FORMAT)
        self.client.post(
            reverse("saved_search_edit", kwargs={"saved_search_id": record.saved_search_id}),
            self.form(day_kind="date", fixed_date=tomorrow, day_rule=""),
        )

        self.assertContains(
            self.page(),
            reverse("saved_search_run", kwargs={"saved_search_id": record.saved_search_id}),
        )

    def test_another_players_search_cannot_be_run(self):
        self.create()
        record = self.only()
        self.sign_in(OTHER)

        response = self.client.get(
            reverse("saved_search_run", kwargs={"saved_search_id": record.saved_search_id})
        )

        self.assertEqual(response.status_code, 404)

    def test_a_day_rule_still_runs_a_year_later(self):
        """The point of G-05."""
        self.create(day_rule="saturday")
        record = self.only()
        previous = clock.set_clock(clock.FrozenClock(clock.now() + _dt.timedelta(days=365)))
        self.addCleanup(clock.set_clock, previous)

        response = self.client.get(
            reverse("saved_search_run", kwargs={"saved_search_id": record.saved_search_id})
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("search"), response["Location"])


class ThePagesAreOwnerOnlyTests(SavedSearchPageCase):
    """AC3."""

    def test_they_need_a_session_and_are_not_cached(self):
        """FE-3, FE-9."""
        self.assertIn("no-store", self.page()["Cache-Control"])

        self.client.post(reverse("sign_out"))

        for name in ("saved_searches", "saved_search_new"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn(reverse("sign_in"), response["Location"])

    def test_no_contact_address_appears_on_them(self):
        """FE-2."""
        self.create()

        self.assertNotIn("@", self.page().content.decode())
        self.assertNotIn("@", self.client.get(reverse("saved_search_new")).content.decode())

    def test_no_coordinate_appears_on_them(self):
        """ASR-03."""
        self.create()

        body = self.page().content.decode()

        for coordinate in ("33.7211", "73.0551"):
            self.assertNotIn(coordinate, body)
