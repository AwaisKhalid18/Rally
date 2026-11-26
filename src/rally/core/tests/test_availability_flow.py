"""The S4 vertical slice end to end - plan.md S4 AC1 to AC4."""
import datetime as _dt
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rally.core import clock
from rally.core.localtime import DATE_FORMAT
from rally.modules.availability.api import facade as availability
from rally.modules.availability.internal.models import AvailabilitySlot
from rally.modules.identity.api import facade as identity
from rally.modules.notification.api import facade as notification
from rally.modules.profiles.api import facade as profiles

PASSWORD = "longenough"
OWNER = "owner@example.com"
OTHER = "other@example.com"
AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
]


def local_date(day_offset: int) -> str:
    return (timezone.localtime(clock.now()) + _dt.timedelta(days=day_offset)).strftime(DATE_FORMAT)


class AvailabilityFlowCase(TestCase):
    def setUp(self):
        previous = notification.set_email_adapter(notification.RecordingEmailAdapter())
        self.addCleanup(notification.set_email_adapter, previous)
        profiles.replace_areas(AREAS)
        self.owner_id = identity.register(OWNER, PASSWORD).account_id
        self.client.post(reverse("sign_in"), {"email": OWNER, "password": PASSWORD})

    def add(self, day_offset=1, start="18:00", end="20:00"):
        return self.client.post(
            reverse("availability"),
            {"date": local_date(day_offset), "start": start, "end": end},
        )


class AvailabilityPageTests(AvailabilityFlowCase):
    def test_the_page_needs_a_session(self):
        self.client.post(reverse("sign_out"))
        self.assertEqual(self.client.get(reverse("availability")).status_code, 302)

    def test_an_owner_adds_a_slot(self):
        """AC1."""
        response = self.add()

        self.assertRedirects(response, reverse("availability"))
        self.assertEqual(len(availability.list_slots(self.owner_id)), 1)

    def test_several_slots_are_allowed_and_listed(self):
        self.add(day_offset=1)
        self.add(day_offset=2, start="09:00", end="11:00")

        body = self.client.get(reverse("availability")).content.decode()

        self.assertEqual(len(availability.list_slots(self.owner_id)), 2)
        self.assertIn("18:00", body)
        self.assertIn("09:00", body)

    def test_an_empty_list_says_why_rather_than_showing_nothing(self):
        """Rule 13, FE-6."""
        self.assertContains(self.client.get(reverse("availability")), "No available playing times yet")

    def test_the_page_offers_no_way_to_make_a_recurring_schedule(self):
        """PRD §12.1 and AGENTS.md §7: individual dates only."""
        body = self.client.get(reverse("availability")).content.decode().lower()
        for forbidden in ("repeat", "weekly", "recurring", "every week"):
            self.assertNotIn(forbidden, body)

    def test_what_was_typed_is_kept_when_the_slot_is_rejected(self):
        response = self.add(start="20:00", end="18:00")

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, availability.END_BEFORE_START, status_code=400)
        self.assertContains(response, local_date(1), status_code=400)

    def test_a_slot_already_in_the_past_is_rejected(self):
        """AC2."""
        response = self.add(day_offset=-1)

        self.assertContains(response, availability.ALREADY_PASSED, status_code=400)
        self.assertEqual(availability.list_slots(self.owner_id), [])

    def test_an_overlapping_slot_is_rejected(self):
        """AC2."""
        self.add()

        response = self.add(start="19:00", end="21:00")

        self.assertContains(response, availability.OVERLAPS_OWN_SLOT, status_code=400)
        self.assertEqual(len(availability.list_slots(self.owner_id)), 1)

    def test_unreadable_times_are_reported_as_shape_not_policy(self):
        response = self.client.post(
            reverse("availability"), {"date": "next tuesday", "start": "sixish", "end": ""}
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "YYYY-MM-DD", status_code=400)


class LocalTimeTests(AvailabilityFlowCase):
    """AGENTS.md §5 [v5]: the player types local time, Rally stores UTC."""

    def test_a_typed_local_time_is_stored_as_the_matching_utc_instant(self):
        self.add(day_offset=1, start="18:00", end="20:00")

        (slot,) = availability.list_slots(self.owner_id)

        self.assertEqual(slot.starts_at.tzinfo, _dt.timezone.utc)
        self.assertEqual(timezone.localtime(slot.starts_at).strftime("%H:%M"), "18:00")
        self.assertEqual(timezone.localtime(slot.ends_at).strftime("%H:%M"), "20:00")

    def test_the_same_local_time_is_shown_back(self):
        self.add(day_offset=1, start="18:00", end="20:00")
        self.assertContains(self.client.get(reverse("availability")), "18:00-20:00")


class EditAndDeleteTests(AvailabilityFlowCase):
    """AC1."""

    def setUp(self):
        super().setUp()
        self.add()
        self.slot_id = availability.list_slots(self.owner_id)[0].slot_id

    def test_the_owner_edits_a_slot(self):
        response = self.client.post(
            reverse("availability_edit", kwargs={"slot_id": self.slot_id}),
            {"date": local_date(2), "start": "09:00", "end": "11:00"},
        )

        self.assertRedirects(response, reverse("availability"))
        (slot,) = availability.list_slots(self.owner_id)
        self.assertEqual(timezone.localtime(slot.starts_at).strftime("%H:%M"), "09:00")

    def test_the_edit_form_is_filled_with_the_current_times(self):
        response = self.client.get(reverse("availability_edit", kwargs={"slot_id": self.slot_id}))

        self.assertContains(response, 'value="18:00"')
        self.assertContains(response, f'value="{local_date(1)}"')

    def test_the_owner_deletes_a_slot(self):
        response = self.client.post(
            reverse("availability_delete", kwargs={"slot_id": self.slot_id})
        )

        self.assertRedirects(response, reverse("availability"))
        self.assertEqual(availability.list_slots(self.owner_id), [])

    def test_deleting_is_not_reachable_by_get(self):
        """FE-9."""
        response = self.client.get(reverse("availability_delete", kwargs={"slot_id": self.slot_id}))

        self.assertEqual(response.status_code, 405)
        self.assertEqual(len(availability.list_slots(self.owner_id)), 1)


class OnlyTheOwnerChangesSlotsTests(AvailabilityFlowCase):
    """AC4 - only the owner can change them."""

    def setUp(self):
        super().setUp()
        self.add()
        self.slot_id = availability.list_slots(self.owner_id)[0].slot_id
        self.other_id = identity.register(OTHER, PASSWORD).account_id
        self.client.post(reverse("sign_out"))
        self.client.post(reverse("sign_in"), {"email": OTHER, "password": PASSWORD})

    def test_another_player_cannot_open_the_edit_form(self):
        response = self.client.get(reverse("availability_edit", kwargs={"slot_id": self.slot_id}))
        self.assertEqual(response.status_code, 404)

    def test_another_player_cannot_edit_it(self):
        response = self.client.post(
            reverse("availability_edit", kwargs={"slot_id": self.slot_id}),
            {"date": local_date(5), "start": "09:00", "end": "11:00"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            timezone.localtime(availability.list_slots(self.owner_id)[0].starts_at).strftime("%H:%M"),
            "18:00",
        )

    def test_another_player_cannot_delete_it(self):
        response = self.client.post(
            reverse("availability_delete", kwargs={"slot_id": self.slot_id})
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(availability.list_slots(self.owner_id)), 1)


class SlotsOnThePublicProfileTests(AvailabilityFlowCase):
    """AC4 - slots appear on the owner's public profile."""

    def setUp(self):
        super().setUp()
        profiles.save_profile(self.owner_id, "Maaiz", "intermediate", "isb-f7")
        self.add()
        self.other_id = identity.register(OTHER, PASSWORD).account_id
        self.client.post(reverse("sign_out"))
        self.client.post(reverse("sign_in"), {"email": OTHER, "password": PASSWORD})

    def test_another_player_sees_the_times(self):
        response = self.client.get(reverse("player_profile", kwargs={"account_id": self.owner_id}))

        self.assertContains(response, "18:00-20:00")
        self.assertContains(response, "Available playing times")

    def test_a_player_with_no_times_says_so(self):
        """Rule 13 - absent with a reason, never an empty space."""
        profiles.save_profile(self.other_id, "Other", "beginner", "isb-f7")
        self.client.post(reverse("sign_out"))
        self.client.post(reverse("sign_in"), {"email": OWNER, "password": PASSWORD})

        response = self.client.get(reverse("player_profile", kwargs={"account_id": self.other_id}))

        self.assertContains(response, "has not listed any available playing times")

    def test_the_page_still_shows_no_contact_data_or_coordinates(self):
        response = self.client.get(reverse("player_profile", kwargs={"account_id": self.owner_id}))

        body = response.content.decode()
        self.assertNotIn(OWNER, body)
        self.assertNotIn("@", body)
        self.assertNotIn("33.72", body)


class SweepTests(AvailabilityFlowCase):
    """AC3 - the worker removes slots whose end time has passed."""

    def test_the_worker_removes_a_passed_slot(self):
        AvailabilitySlot.objects.create(
            account_id=self.owner_id,
            starts_at=clock.now() - _dt.timedelta(hours=3),
            ends_at=clock.now() - _dt.timedelta(hours=1),
        )

        out = StringIO()
        call_command("run_worker", "--once", stdout=out)

        self.assertIn("slots_removed=1", out.getvalue())
        self.assertEqual(AvailabilitySlot.objects.count(), 0)

    def test_the_worker_leaves_future_slots_alone(self):
        self.add()

        out = StringIO()
        call_command("run_worker", "--once", stdout=out)

        self.assertNotIn("slots_removed", out.getvalue())
        self.assertEqual(len(availability.list_slots(self.owner_id)), 1)

    def test_a_passed_slot_is_hidden_even_if_the_worker_never_runs(self):
        AvailabilitySlot.objects.create(
            account_id=self.owner_id,
            starts_at=clock.now() - _dt.timedelta(hours=3),
            ends_at=clock.now() - _dt.timedelta(hours=1),
        )

        # The row is still in the table, but neither the page nor the published view
        # shows it: freshness does not depend on the worker having run (ADR-005).
        self.assertContains(self.client.get(reverse("availability")), "No available playing times yet")
        self.assertEqual(availability.list_slots(self.owner_id), [])
        self.assertEqual(AvailabilitySlot.objects.count(), 1)
