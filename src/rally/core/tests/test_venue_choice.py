"""Choosing where to play, on the invitation form (PRD §12.3).

The list is M2's reference data. M5 is untouched: it still receives, validates and
stores the venue as free text, so a player may always name somewhere that is not on
the list. Nothing here books a court — that is excluded from the MVP (PRD §12.5).
"""
import datetime as _dt

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rally.core import clock
from rally.core.localtime import DATE_FORMAT, parse_local
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.invitations.api import facade as invitations
from rally.modules.profiles.api import facade as profiles

PASSWORD = "longenough"
ME = "me@example.com"
THEM = "them@example.com"
AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
    {"code": "isb-g9", "name": "Islamabad G-9", "centroid_lat": "33.6889", "centroid_lon": "73.0369"},
]
VENUES = [
    {"code": "f7-club", "area_code": "isb-f7", "name": "F-7 Racquet Club"},
    {"code": "g9-complex", "area_code": "isb-g9", "name": "G-9 Sports Complex"},
]


def local_date(day_offset: int) -> str:
    return (timezone.localtime(clock.now()) + _dt.timedelta(days=day_offset)).strftime(DATE_FORMAT)


class VenueChoiceCase(TestCase):
    def setUp(self):
        profiles.replace_areas(AREAS)
        profiles.replace_venues(VENUES)
        self.me = self.make_player(ME, "My Name", "isb-f7")
        # The recipient is in G-9, so the G-9 venue should be offered first.
        self.them = self.make_player(THEM, "Their Name", "isb-g9")
        self.client.post(reverse("sign_in"), {"email": ME, "password": PASSWORD})

    def make_player(self, email, name, area):
        account_id = identity.register(email, PASSWORD).account_id
        assert profiles.save_profile(account_id, name, "intermediate", area).ok
        identity.verify_email(identity.get_verification_token(account_id))
        assert availability.add_slot(
            account_id,
            parse_local(local_date(1), "08:00"),
            parse_local(local_date(1), "23:00"),
        ).ok
        return account_id

    def invite_url(self):
        return reverse("invitation_new", kwargs={"account_id": self.them})

    def send(self, **overrides):
        values = {
            "date": local_date(1),
            "start": "18:00",
            "end": "20:00",
            "venue": "",
            "venue_code": "",
        }
        values.update(overrides)
        return self.client.post(self.invite_url(), values)

    def venue_of_the_only_invitation(self):
        sent, _ = invitations.list_for_player(self.me)
        return sent[0].venue


class TheFormOffersPlacesTests(VenueChoiceCase):
    def test_the_places_are_listed(self):
        response = self.client.get(self.invite_url())

        self.assertContains(response, "F-7 Racquet Club")
        self.assertContains(response, "G-9 Sports Complex")

    def test_each_one_names_the_area_it_is_in(self):
        response = self.client.get(self.invite_url())

        self.assertContains(response, "G-9 Sports Complex — Islamabad G-9")

    def test_places_in_the_recipients_area_come_first(self):
        """They are the ones the other player is likely to play at."""
        body = self.client.get(self.invite_url()).content.decode()

        self.assertLess(body.index("G-9 Sports Complex"), body.index("F-7 Racquet Club"))

    def test_typing_one_is_still_offered(self):
        """PRD §12.3 keeps the venue free text; the list is a convenience."""
        response = self.client.get(self.invite_url())

        self.assertContains(response, "Somewhere else")
        self.assertContains(response, 'name="venue"')

    def test_the_form_says_rally_books_nothing(self):
        """PRD §12.5: court booking is excluded, and the page must not imply it."""
        self.assertContains(self.client.get(self.invite_url()), "not</strong> book courts")


class ChoosingOneTests(VenueChoiceCase):
    def test_a_chosen_place_becomes_the_invitations_venue(self):
        response = self.send(venue_code="g9-complex")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.venue_of_the_only_invitation(), "G-9 Sports Complex")

    def test_the_recipient_sees_it_on_the_invitation(self):
        self.send(venue_code="g9-complex")
        sent, _ = invitations.list_for_player(self.me)

        self.client.post(reverse("sign_out"))
        self.client.post(reverse("sign_in"), {"email": THEM, "password": PASSWORD})
        response = self.client.get(
            reverse("invitation_detail", kwargs={"invitation_id": sent[0].invitation_id})
        )

        self.assertContains(response, "G-9 Sports Complex")

    def test_a_typed_venue_still_works(self):
        response = self.send(venue="The court behind the school")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.venue_of_the_only_invitation(), "The court behind the school")

    def test_a_chosen_place_wins_over_a_typed_one(self):
        """The dropdown is the explicit choice; a leftover in the text box cannot
        quietly override it."""
        self.send(venue_code="f7-club", venue="Something stale")

        self.assertEqual(self.venue_of_the_only_invitation(), "F-7 Racquet Club")

    def test_neither_given_is_refused_by_m5_as_before(self):
        response = self.send()

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, invitations.VENUE_REQUIRED, status_code=400)

    def test_a_place_that_is_no_longer_listed_is_reported(self):
        """The list can be reloaded between rendering the form and submitting it."""
        response = self.send(venue_code="no-such-venue")

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "no longer listed", status_code=400)
        self.assertEqual(invitations.list_for_player(self.me)[0], [])

    def test_m5_still_validates_the_venue_text(self):
        """M5 never learns the list exists; its own bounds still apply."""
        response = self.send(venue="x" * (invitations.VENUE_MAX_LENGTH + 1))

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, invitations.VENUE_TOO_LONG, status_code=400)


class NothingLocationLikeReachesThePageTests(VenueChoiceCase):
    """Rule 7, ASR-03: a venue is a name, not a point."""

    def test_no_coordinate_appears_on_the_form(self):
        body = self.client.get(self.invite_url()).content.decode()

        for coordinate in ("33.7211", "73.0551", "33.6889", "73.0369"):
            self.assertNotIn(coordinate, body)

    def test_no_contact_address_appears_on_the_form(self):
        self.assertNotIn("@", self.client.get(self.invite_url()).content.decode())
