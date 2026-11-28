"""M2's list of places to play (PRD §12.3).

A venue is reference data beside the areas: a name both players recognise. It carries
**no coordinates** (rule 7, ASR-03) and **reserves nothing** — court booking is
excluded from the MVP (PRD §12.5), and M5 still stores the venue as free text.
"""
from django.test import TestCase

from rally.modules.profiles.api import facade as profiles
from rally.modules.profiles.internal.models import Venue

AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
    {"code": "isb-g9", "name": "Islamabad G-9", "centroid_lat": "33.6889", "centroid_lon": "73.0369"},
]
VENUES = [
    {"code": "f7-club", "area_code": "isb-f7", "name": "F-7 Racquet Club"},
    {"code": "f7-courts", "area_code": "isb-f7", "name": "Rally Courts F-7"},
    {"code": "g9-complex", "area_code": "isb-g9", "name": "G-9 Sports Complex"},
]


class VenueCase(TestCase):
    def setUp(self):
        profiles.replace_areas(AREAS)
        profiles.replace_venues(VENUES)


class TheListTests(VenueCase):
    def test_every_venue_is_listed(self):
        self.assertEqual(len(profiles.list_venues()), 3)

    def test_one_area_can_be_asked_for(self):
        names = [v.name for v in profiles.list_venues("isb-f7")]

        self.assertEqual(sorted(names), ["F-7 Racquet Club", "Rally Courts F-7"])

    def test_an_area_with_no_venues_is_empty_not_an_error(self):
        profiles.replace_areas(AREAS + [
            {"code": "isb-h8", "name": "Islamabad H-8", "centroid_lat": "33.6", "centroid_lon": "73.0"}
        ])
        profiles.replace_venues(VENUES)

        self.assertEqual(profiles.list_venues("isb-h8"), [])

    def test_a_venue_reads_as_the_place_and_its_area(self):
        (venue,) = profiles.list_venues("isb-g9")

        self.assertEqual(venue.label, "G-9 Sports Complex — Islamabad G-9")

    def test_one_can_be_fetched_by_code(self):
        venue = profiles.get_venue("g9-complex")

        self.assertEqual(venue.name, "G-9 Sports Complex")
        self.assertEqual(venue.area_code, "isb-g9")

    def test_an_unknown_code_is_none_rather_than_an_error(self):
        self.assertIsNone(profiles.get_venue("no-such-venue"))


class LoadingTests(VenueCase):
    def test_loading_replaces_the_whole_list(self):
        count = profiles.replace_venues([VENUES[0]])

        self.assertEqual(count, 1)
        self.assertEqual(len(profiles.list_venues()), 1)

    def test_a_venue_naming_an_area_that_does_not_exist_is_refused(self):
        """Silently skipping it would hide a typo in the seed file for good."""
        with self.assertRaises(ValueError) as refused:
            profiles.replace_venues(
                VENUES + [{"code": "x", "area_code": "nowhere", "name": "Nowhere Hall"}]
            )

        self.assertIn("nowhere", str(refused.exception))

    def test_a_refused_load_leaves_the_previous_list_alone(self):
        try:
            profiles.replace_venues([{"code": "x", "area_code": "nowhere", "name": "X"}])
        except ValueError:
            pass

        self.assertEqual(len(profiles.list_venues()), 3)

    def test_the_shipped_seed_file_loads(self):
        """The file in ops/seed is data the demo depends on; a typo in it would only
        show up at the worst moment."""
        import csv
        from pathlib import Path

        from django.conf import settings

        path = Path(settings.BASE_DIR) / "ops" / "seed" / "venues.csv"
        with path.open(encoding="utf-8", newline="") as handle:
            lines = [line for line in handle if not line.lstrip().startswith("#")]
        rows = [
            {
                "code": row["code"].strip(),
                "area_code": row["area_code"].strip(),
                "name": row["name"].strip(),
            }
            for row in csv.DictReader(lines)
        ]
        self.assertTrue(rows, "the shipped venue list is empty")

        # Its areas must be the shipped area list's, or the demo cannot load it.
        area_path = Path(settings.BASE_DIR) / "ops" / "seed" / "areas.csv"
        with area_path.open(encoding="utf-8", newline="") as handle:
            area_lines = [line for line in handle if not line.lstrip().startswith("#")]
        areas = [
            {
                "code": row["code"].strip(),
                "name": row["name"].strip(),
                "centroid_lat": row["centroid_lat"].strip(),
                "centroid_lon": row["centroid_lon"].strip(),
            }
            for row in csv.DictReader(area_lines)
        ]
        profiles.replace_areas(areas)

        self.assertEqual(profiles.replace_venues(rows), len(rows))


class NothingLocationLikeIsStoredTests(VenueCase):
    """Rule 7, ASR-03."""

    def test_the_table_holds_no_coordinate(self):
        columns = {field.attname for field in Venue._meta.fields}

        self.assertEqual(columns, {"id", "code", "area_id", "name"})
        for forbidden in ("lat", "lon", "latitude", "longitude", "address", "postcode"):
            self.assertNotIn(forbidden, columns)

    def test_what_is_published_carries_no_coordinate(self):
        for venue in profiles.list_venues():
            for value in vars(venue).values():
                self.assertNotIn("33.7", str(value))
                self.assertNotIn("73.0", str(value))

    def test_a_venue_is_not_tied_to_a_player(self):
        """It is a place, not anybody's location: nothing links a venue to an account."""
        columns = {field.attname for field in Venue._meta.fields}

        self.assertNotIn("account_id", columns)
        self.assertNotIn("owner_account_id", columns)
