"""The S13 vertical slice end to end - plan.md S13 AC1, AC2, AC3."""
import datetime as _dt

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from rally.core import clock
from rally.core.localtime import DATE_FORMAT, parse_local
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.notification.api import facade as notification
from rally.modules.player_collections.api import facade as collections
from rally.modules.profiles.api import facade as profiles
from rally.modules.safety.api import facade as safety

PASSWORD = "longenough"
ME = "me@example.com"
OTHER = "other@example.com"
AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
]


def local_date(day_offset: int) -> str:
    return (timezone.localtime(clock.now()) + _dt.timedelta(days=day_offset)).strftime(DATE_FORMAT)


class FavoritesPageCase(TestCase):
    def setUp(self):
        previous = notification.set_email_adapter(notification.RecordingEmailAdapter())
        self.addCleanup(notification.set_email_adapter, previous)
        profiles.replace_areas(AREAS)
        self.me = self.make_player(ME, "My Name")
        self.other = self.make_player(OTHER, "Other Name")
        self.sign_in(ME)

    def make_player(self, email, name, slots=True):
        account_id = identity.register(email, PASSWORD).account_id
        assert profiles.save_profile(account_id, name, "intermediate", "isb-f7").ok
        identity.verify_email(identity.get_verification_token(account_id))
        if slots:
            assert availability.add_slot(
                account_id,
                parse_local(local_date(1), "08:00"),
                parse_local(local_date(1), "23:00"),
            ).ok
        return account_id

    def sign_in(self, email):
        self.client.post(reverse("sign_out"))
        self.client.post(reverse("sign_in"), {"email": email, "password": PASSWORD})

    def add_url(self, account_id=None):
        return reverse("favorite_add", kwargs={"account_id": account_id or self.other})

    def remove_url(self, account_id=None):
        return reverse("favorite_remove", kwargs={"account_id": account_id or self.other})

    def page(self):
        return self.client.get(reverse("favorites"))

    def flush_messages(self):
        """A POST that was not followed leaves its flash message queued, and it renders
        on the next page - which would match an assertion about the list itself."""
        self.client.get(reverse("home"))

    def search_results(self):
        return self.client.get(
            reverse("search"),
            {"date": local_date(1), "start": "18:00", "end": "20:00", "area_code": "isb-f7"},
        )


class WhereFavoritingIsOfferedTests(FavoritesPageCase):
    """AC1."""

    def test_from_the_players_profile(self):
        response = self.client.get(reverse("player_profile", kwargs={"account_id": self.other}))

        self.assertContains(response, self.add_url())
        self.assertContains(response, "Add to favorites")

    def test_from_a_search_result(self):
        response = self.search_results()

        self.assertContains(response, "Other Name")
        self.assertContains(response, self.add_url())

    def test_the_profile_offers_removal_once_they_are_a_favorite(self):
        """The page is told which to show; it never guesses (FE-4)."""
        collections.add_favorite(self.me, self.other)

        response = self.client.get(reverse("player_profile", kwargs={"account_id": self.other}))

        self.assertContains(response, self.remove_url())
        self.assertContains(response, "Remove from favorites")
        self.assertNotContains(response, "Add to favorites")

    def test_a_search_result_does_too(self):
        collections.add_favorite(self.me, self.other)

        response = self.search_results()

        self.assertContains(response, self.remove_url())
        self.assertNotContains(response, "Add to favorites")

    def test_favoriting_is_not_reachable_by_get(self):
        """FE-9."""
        response = self.client.get(self.add_url())

        self.assertEqual(response.status_code, 405)
        self.assertFalse(collections.is_favorite(self.me, self.other))

    def test_removing_is_not_reachable_by_get_either(self):
        collections.add_favorite(self.me, self.other)

        response = self.client.get(self.remove_url())

        self.assertEqual(response.status_code, 405)
        self.assertTrue(collections.is_favorite(self.me, self.other))

    def test_favoriting_a_player_who_does_not_exist_is_a_not_found(self):
        self.assertEqual(
            self.client.post(reverse("favorite_add", kwargs={"account_id": 999999})).status_code,
            404,
        )

    def test_favoriting_yourself_is_a_not_found(self):
        self.assertEqual(self.client.post(self.add_url(self.me)).status_code, 404)


class AddingAndRemovingTests(FavoritesPageCase):
    """AC1."""

    def test_adding_says_so_and_returns_the_player_where_they_were(self):
        response = self.client.post(
            self.add_url(), {"next": reverse("favorites")}, follow=True
        )

        self.assertContains(response, "Other Name is in your favorites.")

    def test_the_player_then_appears_on_the_list(self):
        self.client.post(self.add_url())

        response = self.page()

        self.assertContains(response, "Other Name")
        self.assertContains(response, "1 of 50")

    def test_removing_from_the_list_says_so(self):
        self.client.post(self.add_url())
        self.flush_messages()

        response = self.client.post(
            self.remove_url(), {"next": reverse("favorites")}, follow=True
        )

        self.assertContains(response, "Removed from your favorites.")
        self.assertContains(response, "no favorites yet")

    def test_adding_twice_shows_the_reason(self):
        self.client.post(self.add_url())

        response = self.client.post(
            self.add_url(), {"next": reverse("favorites")}, follow=True
        )

        self.assertContains(response, collections.ALREADY_A_FAVORITE)

    def test_you_cannot_remove_from_another_players_list(self):
        """ASR-05."""
        collections.add_favorite(self.other, self.me)

        self.client.post(self.remove_url(self.me))

        self.assertTrue(collections.is_favorite(self.other, self.me))

    @override_settings(RALLY_MAX_FAVORITES=1)
    def test_the_cap_is_reported_on_the_page_with_the_number(self):
        """AC1 - server-side, and the message names the limit."""
        self.client.post(self.add_url())
        third = self.make_player("third@example.com", "Third Name", slots=False)

        response = self.client.post(
            reverse("favorite_add", kwargs={"account_id": third}),
            {"next": reverse("favorites")},
            follow=True,
        )

        self.assertContains(response, "full at 1 players")
        self.assertEqual(collections.count_favorites(self.me), 1)


class WhatTheListShowsTests(FavoritesPageCase):
    """AC2."""

    def test_an_empty_list_explains_itself(self):
        """FE-6."""
        self.assertContains(self.page(), "no favorites yet")

    def test_it_shows_name_level_area_and_times(self):
        self.client.post(self.add_url())

        response = self.page()

        self.assertContains(response, "Other Name")
        self.assertContains(response, "Intermediate")
        self.assertContains(response, "Islamabad F-7")
        self.assertContains(response, "Available:")

    def test_a_player_with_no_times_is_shown_with_the_reason(self):
        """AC2 - shown, not hidden."""
        quiet = self.make_player("quiet@example.com", "Quiet Name", slots=False)
        collections.add_favorite(self.me, quiet)

        response = self.page()

        self.assertContains(response, "Quiet Name")
        self.assertContains(response, collections.NO_AVAILABILITY_REASON)
        self.assertNotContains(response, "Available:")

    def test_an_unresolvable_account_shows_the_reason_and_stays_removable(self):
        """AC2, G-06."""
        collections.add_favorite(self.me, 999999)

        response = self.page()

        self.assertContains(response, collections.UNAVAILABLE_ACCOUNT_REASON)
        self.assertContains(response, reverse("favorite_remove", kwargs={"account_id": 999999}))
        # The exact href: the remove action's URL contains the profile's path as a
        # prefix, so a bare substring match would always find it.
        self.assertNotContains(
            response,
            'href="' + reverse("player_profile", kwargs={"account_id": 999999}) + '"',
            msg_prefix="an account that cannot be resolved has no profile to open",
        )

    def test_that_entry_can_actually_be_removed(self):
        collections.add_favorite(self.me, 999999)

        self.client.post(reverse("favorite_remove", kwargs={"account_id": 999999}))

        self.assertEqual(collections.list_favorites(self.me), [])

    def test_a_blocked_pair_is_omitted_both_ways(self):
        """AC2, ASR-10."""
        collections.add_favorite(self.me, self.other)
        safety.block(self.me, self.other)

        self.assertNotContains(self.page(), "Other Name")

        safety.unblock(self.me, self.other)
        safety.block(self.other, self.me)

        self.assertNotContains(self.page(), "Other Name")

    def test_the_list_reflects_a_changed_profile(self):
        """AC3 - references, not copies, as a player sees it."""
        self.client.post(self.add_url())
        self.flush_messages()

        assert profiles.save_profile(self.other, "Renamed Player", "advanced", "isb-f7").ok

        response = self.page()
        self.assertContains(response, "Renamed Player")
        self.assertContains(response, "Advanced")
        self.assertNotContains(response, "Other Name")

    def test_the_page_needs_a_session_and_is_not_cached(self):
        """FE-3, FE-9."""
        self.assertIn("no-store", self.page()["Cache-Control"])

        self.client.post(reverse("sign_out"))
        response = self.client.get(reverse("favorites"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("sign_in"), response["Location"])

    def test_no_contact_address_appears_on_the_page(self):
        """FE-2, rule 6."""
        self.client.post(self.add_url())

        self.assertNotIn("@", self.page().content.decode())

    def test_one_players_list_is_not_anothers(self):
        """ASR-04."""
        self.client.post(self.add_url())
        self.sign_in(OTHER)

        self.assertContains(self.page(), "no favorites yet")


class FavoritingIsSilentTests(FavoritesPageCase):
    """AC3."""

    def test_the_favorited_player_is_not_notified(self):
        before = len(notification.list_for_player(self.other))

        self.client.post(self.add_url())

        self.assertEqual(len(notification.list_for_player(self.other)), before)

    def test_no_outbox_record_is_written(self):
        from rally.modules.notification.internal.models import Outbox

        before = Outbox.objects.count()

        self.client.post(self.add_url())
        self.client.post(self.remove_url())

        self.assertEqual(Outbox.objects.count(), before)

    def test_the_other_player_cannot_see_they_were_favorited(self):
        self.client.post(self.add_url())
        self.sign_in(OTHER)

        response = self.client.get(reverse("player_profile", kwargs={"account_id": self.me}))

        self.assertNotContains(response, "Remove from favorites")
        self.assertContains(response, "Add to favorites")
