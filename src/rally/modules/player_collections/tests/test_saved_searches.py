"""M8 saved searches - plan.md S15 AC1, AC2, AC3."""
import datetime as _dt

from django.test import TestCase, override_settings

from rally.core import clock
from rally.modules.identity.api import facade as identity
from rally.modules.player_collections.api import facade as collections
from rally.modules.player_collections.internal.models import SavedSearch
from rally.modules.player_collections.internal.saved_searches import today_locally

PASSWORD = "longenough"
NINE = _dt.time(9, 0)
ELEVEN = _dt.time(11, 0)


class SavedSearchCase(TestCase):
    def setUp(self):
        self.owner = identity.register("owner@example.com", PASSWORD).account_id
        self.other = identity.register("other@example.com", PASSWORD).account_id

    def save(self, name="Saturday mornings", owner=None, **overrides):
        fields = {
            "start_time": NINE,
            "end_time": ELEVEN,
            "area_code": "isb-f7",
            "day_rule": "saturday",
        }
        fields.update(overrides)
        return collections.save_search(owner or self.owner, name=name, **fields)

    def names(self, owner=None):
        return [record.name for record in collections.list_searches(owner or self.owner)]


class SavingTests(SavedSearchCase):
    """AC1."""

    def test_a_named_search_is_saved(self):
        result = self.save()

        self.assertTrue(result.ok, result.errors)
        self.assertEqual(self.names(), ["Saturday mornings"])

    def test_a_name_is_required(self):
        self.assertEqual(self.save(name="").errors, {"name": collections.NAME_REQUIRED})

    def test_a_blank_name_is_refused(self):
        self.assertEqual(self.save(name="   ").errors, {"name": collections.NAME_REQUIRED})

    def test_a_name_at_the_limit_is_accepted(self):
        """BVA on a real bound."""
        self.assertTrue(self.save(name="x" * collections.SEARCH_NAME_MAX_LENGTH).ok)

    def test_a_name_one_character_over_is_refused(self):
        result = self.save(name="x" * (collections.SEARCH_NAME_MAX_LENGTH + 1))

        self.assertEqual(result.errors, {"name": collections.NAME_TOO_LONG})

    def test_the_same_name_twice_is_refused(self):
        self.save()

        self.assertEqual(self.save().errors, {"name": collections.NAME_TAKEN})

    def test_another_player_may_use_the_same_name(self):
        self.save()

        self.assertTrue(self.save(owner=self.other).ok)

    def test_the_times_must_both_be_given(self):
        self.assertEqual(
            self.save(start_time=None).errors, {"times": collections.TIMES_REQUIRED}
        )

    def test_the_end_must_be_after_the_start(self):
        result = self.save(start_time=ELEVEN, end_time=NINE)

        self.assertEqual(result.errors, {"times": collections.SEARCH_END_BEFORE_START})

    def test_equal_times_are_refused(self):
        """BVA: the window must have width."""
        result = self.save(start_time=NINE, end_time=NINE)

        self.assertEqual(result.errors, {"times": collections.SEARCH_END_BEFORE_START})

    def test_an_area_is_required(self):
        self.assertEqual(self.save(area_code="").errors, {"area_code": collections.AREA_REQUIRED})

    def test_the_optional_filters_may_be_left_out(self):
        result = self.save()

        self.assertTrue(result.ok, result.errors)
        (record,) = collections.list_searches(self.owner)
        self.assertEqual(record.playing_level, "")
        self.assertIsNone(record.max_distance_km)

    def test_the_optional_filters_are_kept_when_given(self):
        self.save(playing_level="advanced", max_distance_km=20)

        (record,) = collections.list_searches(self.owner)
        self.assertEqual(record.playing_level, "advanced")
        self.assertEqual(record.max_distance_km, 20)


class WhichDayTests(SavedSearchCase):
    """AC1 and AC2 - G-05, the decision this slice turns on."""

    def test_a_day_rule_is_accepted(self):
        self.assertTrue(self.save(day_rule="tomorrow").ok)

    def test_a_fixed_date_is_accepted(self):
        result = self.save(day_rule="", fixed_date=today_locally() + _dt.timedelta(days=3))

        self.assertTrue(result.ok, result.errors)

    def test_one_of_the_two_is_required(self):
        self.assertEqual(self.save(day_rule="").errors, {"day": collections.DAY_REQUIRED})

    def test_both_together_are_refused(self):
        """Exactly one source of the day, so a search can never be ambiguous."""
        result = self.save(day_rule="saturday", fixed_date=today_locally())

        self.assertEqual(result.errors, {"day": collections.DAY_AMBIGUOUS})

    def test_a_day_rule_that_is_not_offered_is_refused(self):
        self.assertEqual(
            self.save(day_rule="someday").errors, {"day": collections.DAY_RULE_UNKNOWN}
        )

    def test_today_resolves_to_today(self):
        self.save(day_rule="today")

        (record,) = collections.list_searches(self.owner)
        self.assertEqual(record.resolved_date, today_locally())

    def test_tomorrow_resolves_to_tomorrow(self):
        self.save(day_rule="tomorrow")

        (record,) = collections.list_searches(self.owner)
        self.assertEqual(record.resolved_date, today_locally() + _dt.timedelta(days=1))

    def test_a_weekday_resolves_to_its_next_occurrence(self):
        self.save(day_rule="saturday")

        (record,) = collections.list_searches(self.owner)
        self.assertEqual(record.resolved_date.weekday(), 5)
        self.assertGreaterEqual(record.resolved_date, today_locally())
        self.assertLess(record.resolved_date, today_locally() + _dt.timedelta(days=7))

    def test_a_weekday_that_is_today_resolves_to_today(self):
        """'Next occurrence' includes today, so a Saturday search is usable on
        Saturday morning rather than jumping a week."""
        today = today_locally()
        rule = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][
            today.weekday()
        ]
        self.save(day_rule=rule)

        (record,) = collections.list_searches(self.owner)
        self.assertEqual(record.resolved_date, today)

    def test_a_future_fixed_date_resolves_to_itself(self):
        when = today_locally() + _dt.timedelta(days=5)
        self.save(day_rule="", fixed_date=when)

        (record,) = collections.list_searches(self.owner)
        self.assertEqual(record.resolved_date, when)

    def test_todays_fixed_date_still_runs(self):
        """BVA: the boundary is 'before today', so today itself is fine."""
        self.save(day_rule="", fixed_date=today_locally())

        (record,) = collections.list_searches(self.owner)
        self.assertTrue(record.can_run)

    def test_a_past_fixed_date_says_it_needs_a_new_one(self):
        """AC2 - and it is not run, and not silently moved to today (G-05)."""
        self.save(day_rule="", fixed_date=today_locally() - _dt.timedelta(days=1))

        (record,) = collections.list_searches(self.owner)
        self.assertFalse(record.can_run)
        self.assertIsNone(record.resolved_date)
        self.assertEqual(record.cannot_run_reason, collections.NEEDS_A_NEW_DATE)

    def test_a_past_fixed_date_is_still_saved_and_editable(self):
        """Refusing to save it would lose the player's other criteria."""
        result = self.save(day_rule="", fixed_date=today_locally() - _dt.timedelta(days=30))

        self.assertTrue(result.ok, result.errors)
        self.assertEqual(len(collections.list_searches(self.owner)), 1)

    def test_a_day_rule_never_goes_stale(self):
        """The point of G-05: the same saved search still runs a year later."""
        self.save(day_rule="saturday")
        previous = clock.set_clock(clock.FrozenClock(clock.now() + _dt.timedelta(days=365)))
        self.addCleanup(clock.set_clock, previous)

        (record,) = collections.list_searches(self.owner)
        self.assertTrue(record.can_run)
        self.assertGreaterEqual(record.resolved_date, today_locally())


class TheCapTests(SavedSearchCase):
    """AC1 - 'cap 20'."""

    def fill(self, count):
        now = clock.now()
        SavedSearch.objects.bulk_create(
            SavedSearch(
                owner_account_id=self.owner,
                name=f"Search {index}",
                day_rule="today",
                start_time=NINE,
                end_time=ELEVEN,
                area_code="isb-f7",
                created_at=now,
                updated_at=now,
            )
            for index in range(count)
        )

    def test_the_twentieth_is_accepted(self):
        self.fill(collections.max_saved_searches() - 1)

        self.assertTrue(self.save().ok)

    def test_the_twenty_first_is_refused_with_a_message_naming_the_limit(self):
        self.fill(collections.max_saved_searches())

        result = self.save()

        self.assertEqual(result.errors, {"name": collections.saved_search_cap_message()})
        self.assertIn(str(collections.max_saved_searches()), result.errors["name"])

    def test_deleting_one_makes_room(self):
        self.fill(collections.max_saved_searches())
        (first,) = collections.list_searches(self.owner)[:1]

        collections.delete_search(first.saved_search_id, self.owner)

        self.assertTrue(self.save().ok)

    def test_the_cap_is_per_owner(self):
        self.fill(collections.max_saved_searches())

        self.assertTrue(self.save(owner=self.other).ok)

    @override_settings(RALLY_MAX_SAVED_SEARCHES=1)
    def test_the_cap_is_configuration_not_code(self):
        self.assertEqual(collections.max_saved_searches(), 1)
        self.assertTrue(self.save().ok)

        self.assertIn("1", self.save(name="Another").errors["name"])


class EditingAndDeletingTests(SavedSearchCase):
    """AC1 and AC3 - owner-only."""

    def saved(self):
        self.save()
        return collections.list_searches(self.owner)[0]

    def test_editing_changes_the_criteria(self):
        record = self.saved()

        result = collections.update_search(
            record.saved_search_id,
            self.owner,
            name="Sunday evenings",
            start_time=_dt.time(18, 0),
            end_time=_dt.time(20, 0),
            area_code="isb-g9",
            day_rule="sunday",
        )

        self.assertTrue(result.ok, result.errors)
        (updated,) = collections.list_searches(self.owner)
        self.assertEqual(updated.name, "Sunday evenings")
        self.assertEqual(updated.area_code, "isb-g9")
        self.assertEqual(updated.day_rule, "sunday")

    def test_editing_validates_the_same_way_as_saving(self):
        record = self.saved()

        result = collections.update_search(
            record.saved_search_id,
            self.owner,
            name="",
            start_time=NINE,
            end_time=ELEVEN,
            area_code="isb-f7",
            day_rule="today",
        )

        self.assertEqual(result.errors, {"name": collections.NAME_REQUIRED})

    def test_you_cannot_edit_another_players_search(self):
        record = self.saved()

        result = collections.update_search(
            record.saved_search_id,
            self.other,
            name="Hijacked",
            start_time=NINE,
            end_time=ELEVEN,
            area_code="isb-f7",
            day_rule="today",
        )

        self.assertEqual(result.errors, {"name": collections.SEARCH_NOT_FOUND})
        self.assertEqual(self.names(), ["Saturday mornings"])

    def test_deleting_removes_it(self):
        record = self.saved()

        self.assertTrue(collections.delete_search(record.saved_search_id, self.owner))
        self.assertEqual(self.names(), [])

    def test_you_cannot_delete_another_players_search(self):
        record = self.saved()

        self.assertFalse(collections.delete_search(record.saved_search_id, self.other))
        self.assertEqual(self.names(), ["Saturday mornings"])

    def test_deleting_one_that_does_not_exist_gives_the_same_answer(self):
        """ASR-05: a different answer would confirm somebody else's search exists."""
        self.assertFalse(collections.delete_search(999_999, self.owner))

    def test_the_most_recently_changed_comes_first(self):
        self.save(name="First")
        self.save(name="Second")
        first = [r for r in collections.list_searches(self.owner) if r.name == "First"][0]

        collections.update_search(
            first.saved_search_id,
            self.owner,
            name="First",
            start_time=NINE,
            end_time=ELEVEN,
            area_code="isb-f7",
            day_rule="today",
        )

        self.assertEqual(self.names()[0], "First")


class OwnerOnlyAndNoCopiesTests(SavedSearchCase):
    """AC3."""

    def test_you_see_only_your_own(self):
        self.save(name="Mine")
        self.save(name="Theirs", owner=self.other)

        self.assertEqual(self.names(), ["Mine"])
        self.assertEqual(self.names(self.other), ["Theirs"])

    def test_you_cannot_read_another_players_search(self):
        self.save()
        record = collections.list_searches(self.owner)[0]

        self.assertIsNone(collections.get_search(record.saved_search_id, self.other))

    def test_the_table_stores_an_area_reference_and_no_coordinates(self):
        """ASR-03: storing the picked point would put location data in the schema."""
        self.save()

        columns = {field.attname for field in SavedSearch._meta.fields}

        self.assertIn("area_code", columns)
        for forbidden in ("latitude", "longitude", "centroid_lat", "centroid_lon", "lat", "lon"):
            self.assertNotIn(forbidden, columns)

    def test_no_column_holds_a_coordinate_or_an_address(self):
        self.save()

        row = SavedSearch.objects.get()
        stored = " ".join(str(getattr(row, f.attname)) for f in SavedSearch._meta.fields)

        for leaked in ("@", "33.7", "73.0"):
            self.assertNotIn(leaked, stored)

    def test_nothing_about_another_player_is_stored(self):
        """Rule 11: these are the owner's own criteria and nobody else's data."""
        self.save()

        columns = {field.attname for field in SavedSearch._meta.fields}

        self.assertEqual(
            columns,
            {
                "id", "owner_account_id", "name", "fixed_date", "day_rule",
                "start_time", "end_time", "area_code", "playing_level",
                "max_distance_km", "created_at", "updated_at",
            },
        )


class M8NeverRunsASearchTests(SavedSearchCase):
    """AC2 - 'M8 never calls M4'. The composition is Platform's (rule 12)."""

    def test_the_facade_publishes_no_way_to_run_one(self):
        operations = [
            name
            for name in dir(collections)
            if not name.startswith("_") and callable(getattr(collections, name))
        ]

        for name in operations:
            self.assertNotIn("run", name.lower(), f"M8 publishes a runner: {name}")
            self.assertNotIn("execute", name.lower(), f"M8 publishes a runner: {name}")

    def test_m8_holds_no_import_of_m4(self):
        from rally.modules.player_collections.api import facade
        from rally.modules.player_collections.internal import models, saved_searches

        for module in (facade, saved_searches, models):
            leaked = [
                name
                for name, value in vars(module).items()
                if getattr(value, "__module__", "").startswith("rally.modules.search")
                or getattr(value, "__name__", "").startswith("rally.modules.search")
            ]
            self.assertEqual(leaked, [], f"{module.__name__} imports M4: {leaked}")

    def test_getting_a_search_returns_criteria_and_nothing_else(self):
        """What Platform hands to M4: the criteria, not results."""
        self.save()
        record = collections.list_searches(self.owner)[0]

        fetched = collections.get_search(record.saved_search_id, self.owner)

        self.assertFalse(hasattr(fetched, "results"))
        self.assertEqual(fetched.area_code, "isb-f7")
        self.assertEqual(fetched.start_time, NINE)
