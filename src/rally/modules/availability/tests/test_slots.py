"""M3 slot rules - plan.md S4 AC1, AC2, AC3.

M3's own tests. M3 depends on nothing, so no other module appears here at all; an
account id is just an integer to this module.
"""
import datetime as _dt

from django.test import TestCase

from rally.core import clock
from rally.modules.availability.api import facade as availability
from rally.modules.availability.internal.models import AvailabilitySlot

OWNER = 1
OTHER = 2


def at(day_offset: int, hour: int, minute: int = 0) -> _dt.datetime:
    # Anchored on midnight, not on "now": re-reading the clock per call made the
    # fixture and the search window disagree whenever the hour rolled over mid-test.
    midnight = clock.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + _dt.timedelta(days=day_offset, hours=hour, minutes=minute)


class AddSlotTests(TestCase):
    def test_an_owner_adds_a_slot(self):
        """AC1."""
        result = availability.add_slot(OWNER, at(1, 18), at(1, 20))

        self.assertTrue(result.ok, result.error)
        slots = availability.list_slots(OWNER)
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0].account_id, OWNER)

    def test_several_slots_are_allowed(self):
        availability.add_slot(OWNER, at(1, 18), at(1, 20))
        availability.add_slot(OWNER, at(2, 9), at(2, 11))
        availability.add_slot(OWNER, at(3, 7), at(3, 8))

        self.assertEqual(len(availability.list_slots(OWNER)), 3)

    def test_slots_come_back_earliest_first(self):
        availability.add_slot(OWNER, at(3, 7), at(3, 8))
        availability.add_slot(OWNER, at(1, 18), at(1, 20))

        starts = [slot.starts_at for slot in availability.list_slots(OWNER)]
        self.assertEqual(starts, sorted(starts))

    def test_two_players_keep_their_own_slots(self):
        availability.add_slot(OWNER, at(1, 18), at(1, 20))
        availability.add_slot(OTHER, at(1, 18), at(1, 20))

        self.assertEqual(len(availability.list_slots(OWNER)), 1)
        self.assertEqual(len(availability.list_slots(OTHER)), 1)


class RejectedSlotTests(TestCase):
    """AC2."""

    def test_an_end_before_the_start_is_rejected(self):
        result = availability.add_slot(OWNER, at(1, 20), at(1, 18))

        self.assertEqual(result.error, availability.END_BEFORE_START)
        self.assertEqual(AvailabilitySlot.objects.count(), 0)

    def test_an_end_equal_to_the_start_is_rejected(self):
        result = availability.add_slot(OWNER, at(1, 18), at(1, 18))
        self.assertEqual(result.error, availability.END_BEFORE_START)

    def test_a_slot_that_has_already_ended_is_rejected(self):
        result = availability.add_slot(OWNER, at(-1, 18), at(-1, 20))

        self.assertEqual(result.error, availability.ALREADY_PASSED)
        self.assertEqual(AvailabilitySlot.objects.count(), 0)

    def test_a_slot_that_is_under_way_is_still_acceptable(self):
        """A slot is valid until its END time passes (PRD §12.1)."""
        now = clock.now()
        result = availability.add_slot(
            OWNER, now - _dt.timedelta(minutes=30), now + _dt.timedelta(minutes=30)
        )
        self.assertTrue(result.ok, result.error)

    def test_a_slot_ending_exactly_now_is_rejected(self):
        frozen = clock.now()
        previous = clock.set_clock(clock.FrozenClock(frozen))
        self.addCleanup(clock.set_clock, previous)

        result = availability.add_slot(OWNER, frozen - _dt.timedelta(hours=1), frozen)

        self.assertEqual(result.error, availability.ALREADY_PASSED)


class OwnSlotsMayNotOverlapTests(TestCase):
    """AC2, G-12. Enforced twice: a readable check and a database constraint."""

    def setUp(self):
        self.assertTrue(availability.add_slot(OWNER, at(1, 18), at(1, 20)).ok)

    def test_an_overlapping_slot_is_rejected_with_a_sentence(self):
        result = availability.add_slot(OWNER, at(1, 19), at(1, 21))

        self.assertEqual(result.error, availability.OVERLAPS_OWN_SLOT)
        self.assertEqual(AvailabilitySlot.objects.count(), 1)

    def test_a_slot_inside_an_existing_one_is_rejected(self):
        self.assertEqual(
            availability.add_slot(OWNER, at(1, 18, 30), at(1, 19)).error,
            availability.OVERLAPS_OWN_SLOT,
        )

    def test_a_slot_swallowing_an_existing_one_is_rejected(self):
        self.assertEqual(
            availability.add_slot(OWNER, at(1, 17), at(1, 21)).error,
            availability.OVERLAPS_OWN_SLOT,
        )

    def test_back_to_back_slots_do_not_overlap(self):
        """The range is half-open, so one ending as the next starts is fine."""
        self.assertTrue(availability.add_slot(OWNER, at(1, 20), at(1, 22)).ok)
        self.assertTrue(availability.add_slot(OWNER, at(1, 16), at(1, 18)).ok)
        self.assertEqual(len(availability.list_slots(OWNER)), 3)

    def test_another_players_slot_may_cover_the_same_time(self):
        self.assertTrue(availability.add_slot(OTHER, at(1, 18), at(1, 20)).ok)

    def test_the_database_refuses_an_overlap_the_application_check_did_not_see(self):
        """The constraint is the backstop that holds under concurrency (ADR-004's
        pattern). Writing straight to the model skips the readable check."""
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError), transaction.atomic():
            AvailabilitySlot.objects.create(
                account_id=OWNER, starts_at=at(1, 19), ends_at=at(1, 21)
            )


class EditAndRemoveTests(TestCase):
    """AC1 and AC4 - only the owner changes a slot (ADR-003)."""

    def setUp(self):
        self.slot_id = availability.add_slot(OWNER, at(1, 18), at(1, 20)).slot_id

    def test_the_owner_edits_a_slot(self):
        result = availability.edit_slot(OWNER, self.slot_id, at(2, 9), at(2, 11))

        self.assertTrue(result.ok, result.error)
        (slot,) = availability.list_slots(OWNER)
        self.assertEqual(slot.starts_at, at(2, 9))

    def test_editing_keeps_the_same_slot_rather_than_adding_one(self):
        availability.edit_slot(OWNER, self.slot_id, at(2, 9), at(2, 11))
        self.assertEqual(AvailabilitySlot.objects.count(), 1)

    def test_an_edit_that_would_overlap_another_own_slot_is_rejected(self):
        availability.add_slot(OWNER, at(2, 9), at(2, 11))

        result = availability.edit_slot(OWNER, self.slot_id, at(2, 10), at(2, 12))

        self.assertEqual(result.error, availability.OVERLAPS_OWN_SLOT)

    def test_an_edit_may_keep_its_own_times(self):
        self.assertTrue(availability.edit_slot(OWNER, self.slot_id, at(1, 18), at(1, 21)).ok)

    def test_another_player_cannot_edit_it(self):
        result = availability.edit_slot(OTHER, self.slot_id, at(2, 9), at(2, 11))

        self.assertEqual(result.error, availability.NOT_YOURS)
        self.assertEqual(availability.list_slots(OWNER)[0].starts_at, at(1, 18))

    def test_another_player_cannot_remove_it(self):
        result = availability.remove_slot(OTHER, self.slot_id)

        self.assertEqual(result.error, availability.NOT_YOURS)
        self.assertEqual(AvailabilitySlot.objects.count(), 1)

    def test_the_owner_removes_it(self):
        self.assertTrue(availability.remove_slot(OWNER, self.slot_id).ok)
        self.assertEqual(availability.list_slots(OWNER), [])

    def test_a_slot_that_is_gone_says_so(self):
        availability.remove_slot(OWNER, self.slot_id)
        self.assertEqual(availability.remove_slot(OWNER, self.slot_id).error, availability.NOT_FOUND)

    def test_get_slot_only_returns_the_callers_own(self):
        self.assertIsNotNone(availability.get_slot(OWNER, self.slot_id))
        self.assertIsNone(availability.get_slot(OTHER, self.slot_id))


class ExpiryTests(TestCase):
    """AC3 - a slot is removed once its end time has passed."""

    def _past_slot(self, ends_at):
        """Past slots cannot be created through the facade, which is the point of AC2."""
        return AvailabilitySlot.objects.create(
            account_id=OWNER, starts_at=ends_at - _dt.timedelta(hours=2), ends_at=ends_at
        )

    def test_a_passed_slot_is_removed(self):
        self._past_slot(clock.now() - _dt.timedelta(hours=1))

        self.assertEqual(availability.remove_expired_slots(), 1)
        self.assertEqual(AvailabilitySlot.objects.count(), 0)

    def test_a_slot_ending_exactly_now_counts_as_passed(self):
        frozen = clock.now()
        self._past_slot(frozen)
        previous = clock.set_clock(clock.FrozenClock(frozen))
        self.addCleanup(clock.set_clock, previous)

        self.assertEqual(availability.remove_expired_slots(), 1)

    def test_a_future_slot_is_left_alone(self):
        availability.add_slot(OWNER, at(1, 18), at(1, 20))

        self.assertEqual(availability.remove_expired_slots(), 0)
        self.assertEqual(AvailabilitySlot.objects.count(), 1)

    def test_a_passed_slot_is_hidden_before_the_sweep_has_run(self):
        """The list filters by time as well, so a late sweep never shows a stale slot."""
        self._past_slot(clock.now() - _dt.timedelta(hours=1))

        self.assertEqual(availability.list_slots(OWNER), [])
        self.assertEqual(AvailabilitySlot.objects.count(), 1)
        self.assertEqual(len(availability.list_slots(OWNER, include_past=True)), 1)


class HasAvailabilityTests(TestCase):
    """What M5 will ask at send and at accept (PRD §12.4, ASR-08)."""

    def setUp(self):
        availability.add_slot(OWNER, at(1, 18), at(1, 22))

    def test_a_window_inside_a_slot_is_available(self):
        self.assertTrue(availability.has_availability(OWNER, at(1, 19), at(1, 21)))

    def test_the_whole_slot_is_available(self):
        self.assertTrue(availability.has_availability(OWNER, at(1, 18), at(1, 22)))

    def test_a_window_starting_before_the_slot_is_not(self):
        self.assertFalse(availability.has_availability(OWNER, at(1, 17), at(1, 20)))

    def test_a_window_ending_after_the_slot_is_not(self):
        self.assertFalse(availability.has_availability(OWNER, at(1, 20), at(1, 23)))

    def test_two_adjoining_slots_do_not_add_up(self):
        """A game is one continuous booking, so it must sit inside a single slot."""
        availability.add_slot(OWNER, at(1, 22), at(1, 23))
        self.assertFalse(availability.has_availability(OWNER, at(1, 21), at(1, 23)))

    def test_another_player_is_not_available_on_this_slot(self):
        self.assertFalse(availability.has_availability(OTHER, at(1, 19), at(1, 21)))
