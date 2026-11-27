"""M8 favorites - plan.md S13 AC1, AC2, AC3.

M8's own tests. They create the players and profiles they need through other modules'
facades, which is fixture setup; M8's production code imports none of them and composes
its display from the published views instead (the `.importlinter` contract enforces it).
"""
import datetime as _dt

from django.test import TestCase, override_settings

from rally.core import clock
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.player_collections.api import facade as collections
from rally.modules.player_collections.internal.models import Favorite
from rally.modules.profiles.api import facade as profiles
from rally.modules.safety.api import facade as safety

PASSWORD = "longenough"
AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
    {"code": "isb-g9", "name": "Islamabad G-9", "centroid_lat": "33.6889", "centroid_lon": "73.0369"},
]


def at(day_offset: int, hour: int) -> _dt.datetime:
    midnight = clock.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + _dt.timedelta(days=day_offset, hours=hour)


class FavoriteCase(TestCase):
    def setUp(self):
        profiles.replace_areas(AREAS)
        self.owner = self.make_player("owner", slots=True)
        self.other = self.make_player("other", slots=True)
        self.third = self.make_player("third", slots=True)

    def make_player(self, name, slots=False, level="intermediate", area="isb-f7"):
        account_id = identity.register(f"{name}@example.com", PASSWORD).account_id
        assert profiles.save_profile(account_id, name.title(), level, area).ok
        identity.verify_email(identity.get_verification_token(account_id))
        if slots:
            assert availability.add_slot(account_id, at(1, 18), at(1, 20)).ok
        return account_id

    def names(self, owner=None):
        return [entry.display_name for entry in collections.list_favorites(owner or self.owner)]


class AddingTests(FavoriteCase):
    """AC1."""

    def test_adding_a_player_puts_them_on_the_list(self):
        result = collections.add_favorite(self.owner, self.other)

        self.assertTrue(result.ok, result.error)
        self.assertEqual(self.names(), ["Other"])

    def test_you_cannot_favorite_yourself(self):
        result = collections.add_favorite(self.owner, self.owner)

        self.assertEqual(result.error, collections.CANNOT_FAVORITE_YOURSELF)
        self.assertEqual(Favorite.objects.count(), 0)

    def test_adding_the_same_player_twice_is_refused(self):
        collections.add_favorite(self.owner, self.other)

        result = collections.add_favorite(self.owner, self.other)

        self.assertEqual(result.error, collections.ALREADY_A_FAVORITE)
        self.assertEqual(Favorite.objects.count(), 1)

    def test_two_players_may_favorite_the_same_person(self):
        collections.add_favorite(self.owner, self.other)

        self.assertTrue(collections.add_favorite(self.third, self.other).ok)

    def test_favoriting_is_not_mutual(self):
        """A list is the owner's own; being on one puts nobody on yours."""
        collections.add_favorite(self.owner, self.other)

        self.assertEqual(collections.list_favorites(self.other), [])

    def test_is_favorite_answers_for_the_owner_only(self):
        collections.add_favorite(self.owner, self.other)

        self.assertTrue(collections.is_favorite(self.owner, self.other))
        self.assertFalse(collections.is_favorite(self.other, self.owner))

    def test_the_newest_favorite_comes_first(self):
        collections.add_favorite(self.owner, self.other)
        Favorite.objects.all().update(created_at=clock.now() - _dt.timedelta(hours=1))
        collections.add_favorite(self.owner, self.third)

        self.assertEqual(self.names(), ["Third", "Other"])


class TheCapTests(FavoriteCase):
    """AC1 - 'cap 50 (the 51st is rejected with a message)'. BVA on a real bound."""

    def fill(self, count, owner=None):
        """Rows straight into the table: the cap is about the count, and 50 players
        with profiles would make this test about fixtures instead."""
        owner = owner or self.owner
        Favorite.objects.bulk_create(
            Favorite(
                owner_account_id=owner,
                favorited_account_id=900_000 + index,
                created_at=clock.now(),
            )
            for index in range(count)
        )

    def test_the_fiftieth_is_accepted(self):
        self.fill(collections.max_favorites() - 1)

        result = collections.add_favorite(self.owner, self.other)

        self.assertTrue(result.ok, result.error)
        self.assertEqual(collections.count_favorites(self.owner), collections.max_favorites())

    def test_the_fifty_first_is_refused_with_a_message_naming_the_limit(self):
        self.fill(collections.max_favorites())

        result = collections.add_favorite(self.owner, self.other)

        self.assertEqual(result.error, collections.cap_reached_message())
        self.assertIn(str(collections.max_favorites()), result.error)
        self.assertEqual(collections.count_favorites(self.owner), collections.max_favorites())

    def test_removing_one_makes_room_again(self):
        self.fill(collections.max_favorites())

        collections.remove_favorite(self.owner, 900_000)

        self.assertTrue(collections.add_favorite(self.owner, self.other).ok)

    def test_the_cap_is_per_owner_not_global(self):
        self.fill(collections.max_favorites())

        self.assertTrue(collections.add_favorite(self.third, self.other).ok)

    @override_settings(RALLY_MAX_FAVORITES=2)
    def test_the_cap_is_configuration_not_code(self):
        """R-15: the number is adjustable without an architecture change."""
        self.assertEqual(collections.max_favorites(), 2)
        self.assertTrue(collections.add_favorite(self.owner, self.other).ok)
        self.assertTrue(collections.add_favorite(self.owner, self.third).ok)

        result = collections.add_favorite(self.owner, 900_001)

        self.assertIn("2 players", result.error)


class RemovingTests(FavoriteCase):
    """AC1."""

    def test_removing_takes_them_off_the_list(self):
        collections.add_favorite(self.owner, self.other)

        result = collections.remove_favorite(self.owner, self.other)

        self.assertTrue(result.ok, result.error)
        self.assertEqual(collections.list_favorites(self.owner), [])

    def test_removing_someone_who_is_not_on_it_says_so(self):
        self.assertEqual(
            collections.remove_favorite(self.owner, self.other).error,
            collections.NOT_A_FAVORITE,
        )

    def test_you_cannot_remove_from_another_players_list(self):
        """AC1, ASR-05 - owner-only, and the same answer as for one that is not there."""
        collections.add_favorite(self.third, self.other)

        result = collections.remove_favorite(self.owner, self.other)

        self.assertEqual(result.error, collections.NOT_A_FAVORITE)
        self.assertEqual(self.names(self.third), ["Other"])

    def test_removing_twice_is_refused_the_second_time(self):
        collections.add_favorite(self.owner, self.other)
        collections.remove_favorite(self.owner, self.other)

        self.assertEqual(
            collections.remove_favorite(self.owner, self.other).error,
            collections.NOT_A_FAVORITE,
        )


class WhatTheListShowsTests(FavoriteCase):
    """AC2."""

    def test_it_shows_name_level_area_and_future_slots(self):
        collections.add_favorite(self.owner, self.other)

        (entry,) = collections.list_favorites(self.owner)

        self.assertEqual(entry.display_name, "Other")
        self.assertEqual(entry.playing_level, "intermediate")
        self.assertEqual(entry.area_name, "Islamabad F-7")
        self.assertEqual([(s.starts_at, s.ends_at) for s in entry.slots], [(at(1, 18), at(1, 20))])
        self.assertIsNone(entry.no_slots_reason)
        self.assertIsNone(entry.unavailable_reason)

    def test_every_slot_of_a_player_is_listed_in_time_order(self):
        assert availability.add_slot(self.other, at(2, 9), at(2, 11)).ok
        collections.add_favorite(self.owner, self.other)

        (entry,) = collections.list_favorites(self.owner)

        self.assertEqual([s.starts_at for s in entry.slots], [at(1, 18), at(2, 9)])

    def test_a_player_with_no_times_is_shown_with_a_reason_not_hidden(self):
        """AC2 - the asymmetry with search, architecture 16.8."""
        quiet = self.make_player("quiet", slots=False)
        collections.add_favorite(self.owner, quiet)

        (entry,) = collections.list_favorites(self.owner)

        self.assertEqual(entry.display_name, "Quiet")
        self.assertEqual(entry.slots, ())
        self.assertEqual(entry.no_slots_reason, collections.NO_AVAILABILITY_REASON)
        self.assertTrue(entry.is_resolvable)

    def test_a_past_slot_does_not_count_as_availability(self):
        past = self.make_player("past", slots=False)
        assert availability.add_slot(past, at(1, 18), at(1, 20)).ok
        collections.add_favorite(self.owner, past)
        previous = clock.set_clock(clock.FrozenClock(at(2, 12)))
        self.addCleanup(clock.set_clock, previous)

        (entry,) = collections.list_favorites(self.owner)

        self.assertEqual(entry.slots, (), "a slot in the past was listed")
        self.assertEqual(entry.no_slots_reason, collections.NO_AVAILABILITY_REASON)

    def test_an_unverified_player_is_still_shown(self):
        """AC2 - profile completeness is a relevance rule and belongs to search."""
        unverified = identity.register("unverified@example.com", PASSWORD).account_id
        assert profiles.save_profile(unverified, "Unverified", "beginner", "isb-f7").ok
        collections.add_favorite(self.owner, unverified)

        (entry,) = collections.list_favorites(self.owner)

        self.assertEqual(entry.display_name, "Unverified")
        self.assertTrue(entry.is_resolvable)

    def test_an_account_with_no_profile_shows_no_longer_available(self):
        """AC2, G-06 - and it stays on the list rather than vanishing."""
        collections.add_favorite(self.owner, 999_999)

        (entry,) = collections.list_favorites(self.owner)

        self.assertIsNone(entry.display_name)
        self.assertFalse(entry.is_resolvable)
        self.assertEqual(entry.unavailable_reason, collections.UNAVAILABLE_ACCOUNT_REASON)

    def test_an_unavailable_entry_can_still_be_removed(self):
        """AC2 - an entry you cannot remove would be worse than one that is gone."""
        collections.add_favorite(self.owner, 999_999)

        self.assertTrue(collections.remove_favorite(self.owner, 999_999).ok)
        self.assertEqual(collections.list_favorites(self.owner), [])

    def test_the_level_and_area_shown_are_the_current_ones(self):
        """AC3 - references, not copies: changing the profile changes the list."""
        collections.add_favorite(self.owner, self.other)

        assert profiles.save_profile(self.other, "Renamed", "advanced", "isb-g9").ok

        (entry,) = collections.list_favorites(self.owner)
        self.assertEqual(
            (entry.display_name, entry.playing_level, entry.area_name),
            ("Renamed", "advanced", "Islamabad G-9"),
        )

    def test_an_empty_list_is_empty_rather_than_an_error(self):
        self.assertEqual(collections.list_favorites(self.owner), [])


class BlockedPairsAreOmittedTests(FavoriteCase):
    """AC2 - 'blocked pairs omitted both ways' (ASR-10)."""

    def test_a_player_the_owner_blocked_disappears(self):
        collections.add_favorite(self.owner, self.other)

        safety.block(self.owner, self.other)

        self.assertEqual(collections.list_favorites(self.owner), [])

    def test_a_player_who_blocked_the_owner_disappears_too(self):
        """The other direction - the row is directed, the effect is not."""
        collections.add_favorite(self.owner, self.other)

        safety.block(self.other, self.owner)

        self.assertEqual(collections.list_favorites(self.owner), [])

    def test_the_others_on_the_list_are_untouched(self):
        collections.add_favorite(self.owner, self.other)
        collections.add_favorite(self.owner, self.third)

        safety.block(self.owner, self.other)

        self.assertEqual(self.names(), ["Third"])

    def test_the_favorite_row_survives_so_unblocking_brings_it_back(self):
        """Omitted from the display, not deleted: blocking cascades invitations, never
        favorites (architecture 16.7 'neither is cascaded by any other operation')."""
        collections.add_favorite(self.owner, self.other)
        safety.block(self.owner, self.other)

        safety.unblock(self.owner, self.other)

        self.assertEqual(self.names(), ["Other"])

    def test_a_blocked_pair_can_still_be_removed_from_the_list(self):
        collections.add_favorite(self.owner, self.other)
        safety.block(self.owner, self.other)

        self.assertTrue(collections.remove_favorite(self.owner, self.other).ok)


class ReferencesNotCopiesTests(FavoriteCase):
    """AC3 - rule 11."""

    def test_the_table_holds_nothing_but_references_and_a_timestamp(self):
        collections.add_favorite(self.owner, self.other)

        columns = {field.attname for field in Favorite._meta.fields}

        self.assertEqual(
            columns, {"id", "owner_account_id", "favorited_account_id", "created_at"}
        )

    def test_no_column_holds_a_name_level_area_contact_or_coordinate(self):
        collections.add_favorite(self.owner, self.other)

        row = Favorite.objects.get()
        stored = " ".join(str(getattr(row, f.attname)) for f in Favorite._meta.fields)

        for leaked in ("Other", "intermediate", "Islamabad", "@", "33.7", "73.0"):
            self.assertNotIn(leaked, stored, f"{leaked!r} was copied into the row")


class FavoritingIsSilentTests(FavoriteCase):
    """AC3 - 'no notification and no outbox record'.

    Asserted here through the row count of M7's tables, which M8's *tests* may read as
    fixture inspection; M8's production code has no path to them at all (rule 3, and the
    contract that forbids M8 importing M7).
    """

    def test_adding_writes_no_outbox_record_and_no_notification(self):
        from rally.modules.notification.internal.models import Notification, Outbox

        outbox_before = Outbox.objects.count()
        notifications_before = Notification.objects.count()

        collections.add_favorite(self.owner, self.other)

        self.assertEqual(Outbox.objects.count(), outbox_before)
        self.assertEqual(Notification.objects.count(), notifications_before)

    def test_removing_is_silent_too(self):
        from rally.modules.notification.internal.models import Outbox

        collections.add_favorite(self.owner, self.other)
        before = Outbox.objects.count()

        collections.remove_favorite(self.owner, self.other)

        self.assertEqual(Outbox.objects.count(), before)

    def test_the_favorited_player_has_no_way_to_learn_of_it(self):
        """The list is private: nothing M8 publishes answers 'who favorited me?'."""
        collections.add_favorite(self.owner, self.other)

        self.assertEqual(collections.list_favorites(self.other), [])
        self.assertFalse(collections.is_favorite(self.other, self.owner))
