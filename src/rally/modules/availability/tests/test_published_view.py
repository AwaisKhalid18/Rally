"""M3's published read view - the contract M4 and M8 will depend on (ADR-002, ADR-006)."""
import datetime as _dt

from django.db import connection
from django.test import TestCase

from rally.core import clock
from rally.modules.availability.api import facade as availability
from rally.modules.availability.internal.models import AvailabilitySlot
from rally.modules.availability.views import ACTIVE_AVAILABILITY, ACTIVE_AVAILABILITY_COLUMNS

OWNER = 1


def columns(view_name: str) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s ORDER BY ordinal_position",
            [view_name],
        )
        return [row[0] for row in cursor.fetchall()]


def rows():
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT slot_id, account_id FROM {ACTIVE_AVAILABILITY} ORDER BY slot_id")
        return cursor.fetchall()


class ActiveAvailabilityViewTests(TestCase):
    def test_the_view_exposes_exactly_its_declared_columns(self):
        self.assertEqual(tuple(columns(ACTIVE_AVAILABILITY)), ACTIVE_AVAILABILITY_COLUMNS)

    def test_the_view_carries_no_contact_field_and_no_location(self):
        present = set(columns(ACTIVE_AVAILABILITY))
        self.assertFalse(present & {"email", "phone", "latitude", "longitude", "location"})

    def test_a_future_slot_appears(self):
        slot_id = availability.add_slot(
            OWNER, clock.now() + _dt.timedelta(days=1), clock.now() + _dt.timedelta(days=1, hours=2)
        ).slot_id

        self.assertEqual(rows(), [(slot_id, OWNER)])

    def test_a_passed_slot_is_already_gone_before_the_sweep_runs(self):
        """The view filters on the database clock, which is what keeps a stalled worker
        a freshness problem and never a correctness one (ADR-005)."""
        AvailabilitySlot.objects.create(
            account_id=OWNER,
            starts_at=clock.now() - _dt.timedelta(hours=3),
            ends_at=clock.now() - _dt.timedelta(hours=1),
        )

        self.assertEqual(rows(), [])
        self.assertEqual(AvailabilitySlot.objects.count(), 1)

    def test_the_sweep_then_removes_the_row_for_good(self):
        AvailabilitySlot.objects.create(
            account_id=OWNER,
            starts_at=clock.now() - _dt.timedelta(hours=3),
            ends_at=clock.now() - _dt.timedelta(hours=1),
        )

        availability.remove_expired_slots()

        self.assertEqual(rows(), [])
        self.assertEqual(AvailabilitySlot.objects.count(), 0)
