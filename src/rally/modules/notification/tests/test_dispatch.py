"""M7 dispatch and the retry policy - plan.md S2 AC2 and AC5.

These are M7's own tests, so they may read M7's internals. They reach M1 only through
its facade (rule 2).
"""
import datetime as _dt

from django.test import TestCase

from rally.core import clock
from rally.core.ports.outbox import (
    EVENT_ACCOUNT_VERIFICATION_REQUESTED,
    RECIPIENT_KEY,
    append_outbox,
)
from rally.modules.identity.api import facade as identity
from rally.modules.notification.api import facade as notification
from rally.modules.notification.internal import adapters
from rally.modules.notification.internal.models import Notification, Outbox, OutboxStatus

EMAIL = "worker@example.com"
PASSWORD = "longenough"


class AdapterCase(TestCase):
    """Installs a test double for the provider so no real email is attempted."""

    adapter_class = adapters.RecordingEmailAdapter

    def setUp(self):
        self.adapter = self.adapter_class()
        self._previous = adapters.set_adapter(self.adapter)
        self.addCleanup(adapters.set_adapter, self._previous)
        self.account_id = identity.register(EMAIL, PASSWORD).account_id


class SuccessfulDispatchTests(AdapterCase):
    def test_registration_left_exactly_one_queued_record(self):
        record = Outbox.objects.get()
        self.assertEqual(record.event_type, EVENT_ACCOUNT_VERIFICATION_REQUESTED)
        self.assertEqual(record.status, OutboxStatus.QUEUED)
        self.assertEqual(record.attempts, 0)
        self.assertEqual(record.entity_refs, {RECIPIENT_KEY: self.account_id})

    def test_dispatch_sends_and_marks_the_record_sent(self):
        run = notification.dispatch_due()

        self.assertEqual((run.claimed, run.sent, run.failed), (1, 1, 0))
        record = Outbox.objects.get()
        self.assertEqual(record.status, OutboxStatus.SENT)
        self.assertEqual(record.attempts, 1)
        self.assertIsNotNone(record.sent_at)
        self.assertEqual(record.provider_response, "accepted:1")

    def test_the_address_is_read_from_m1_at_send_time(self):
        notification.dispatch_due()
        self.assertEqual(self.adapter.sent[0]["to"], EMAIL)

    def test_the_message_carries_the_verification_link(self):
        token = identity.get_verification_token(self.account_id)
        notification.dispatch_due()
        self.assertIn(f"/verify-email/{token}/", self.adapter.sent[0]["body"])

    def test_an_in_app_notification_is_created_whatever_email_does(self):
        notification.dispatch_due()

        row = Notification.objects.get()
        self.assertEqual(row.recipient_account_id, self.account_id)
        self.assertEqual(row.notification_type, EVENT_ACCOUNT_VERIFICATION_REQUESTED)
        self.assertIsNone(row.read_at)

    def test_a_sent_record_is_not_dispatched_again(self):
        notification.dispatch_due()
        second = notification.dispatch_due()

        self.assertEqual(second.claimed, 0)
        self.assertEqual(len(self.adapter.sent), 1)
        self.assertEqual(Notification.objects.count(), 1)


class RetryPolicyTests(AdapterCase):
    """PRD 12.3: up to 3 retries within 15 minutes, then log and stop."""

    adapter_class = adapters.AlwaysFailingEmailAdapter

    def test_a_failure_is_recorded_and_queued_for_another_attempt(self):
        run = notification.dispatch_due()

        self.assertEqual((run.claimed, run.sent, run.retrying, run.failed), (1, 0, 1, 0))
        record = Outbox.objects.get()
        self.assertEqual(record.status, OutboxStatus.QUEUED)
        self.assertEqual(record.attempts, 1)
        self.assertIn("provider unavailable", record.last_error)

    def test_the_next_attempt_is_five_minutes_after_the_failure_and_not_due_yet(self):
        failed_at = clock.now()
        previous = clock.set_clock(clock.FrozenClock(failed_at))
        self.addCleanup(clock.set_clock, previous)

        notification.dispatch_due()

        record = Outbox.objects.get()
        self.assertEqual(record.next_attempt_at, failed_at + notification.RETRY_INTERVAL)
        # A second pass at the same instant must not touch it.
        self.assertEqual(notification.dispatch_due().claimed, 0)

    def test_it_gives_up_after_the_first_attempt_and_three_retries(self):
        created = clock.now()
        previous = clock.set_clock(clock.FrozenClock(created))
        self.addCleanup(clock.set_clock, previous)

        attempts = 0
        for minute in (0, 5, 10, 15):
            clock.set_clock(clock.FrozenClock(created + _dt.timedelta(minutes=minute)))
            attempts += notification.dispatch_due().claimed

        record = Outbox.objects.get()
        self.assertEqual(attempts, notification.MAX_ATTEMPTS)
        self.assertEqual(record.attempts, notification.MAX_ATTEMPTS)
        self.assertEqual(record.status, OutboxStatus.FAILED)

    def test_every_attempt_falls_inside_the_fifteen_minute_window(self):
        self.assertEqual(
            (notification.MAX_ATTEMPTS - 1) * notification.RETRY_INTERVAL,
            notification.RETRY_WINDOW,
        )

    def test_a_failed_record_is_left_alone(self):
        created = clock.now()
        previous = clock.set_clock(clock.FrozenClock(created))
        self.addCleanup(clock.set_clock, previous)
        for minute in (0, 5, 10, 15):
            clock.set_clock(clock.FrozenClock(created + _dt.timedelta(minutes=minute)))
            notification.dispatch_due()

        clock.set_clock(clock.FrozenClock(created + _dt.timedelta(minutes=60)))
        self.assertEqual(notification.dispatch_due().claimed, 0)

    def test_the_player_still_gets_the_in_app_notification(self):
        notification.dispatch_due()
        self.assertEqual(Notification.objects.count(), 1)


class NoContactDataLeavesM1Tests(AdapterCase):
    """Rule 6 - the address is in no outbox row, no notification row and no log."""

    def test_no_outbox_or_notification_column_holds_an_address(self):
        notification.dispatch_due()

        written = []
        for row in Outbox.objects.values():
            written.extend(str(value) for value in row.values())
        for row in Notification.objects.values():
            written.extend(str(value) for value in row.values())

        blob = " ".join(written)
        self.assertNotIn(EMAIL, blob)
        self.assertNotIn("@", blob)

    def test_the_dispatch_log_names_ids_and_never_an_address(self):
        with self.assertLogs("rally.operation", level="INFO") as captured:
            notification.dispatch_due()

        written = "\n".join(captured.output)
        self.assertIn("operation=notification.email outcome=sent", written)
        self.assertNotIn(EMAIL, written)
        self.assertNotIn("@", written)

    def test_the_appender_refuses_an_address_in_entity_refs(self):
        with self.assertRaises(ValueError):
            append_outbox("test.event", {RECIPIENT_KEY: 1, "slipped": EMAIL})


class UndeliverableEventTests(AdapterCase):
    def test_an_event_whose_account_is_already_verified_fails_without_a_retry(self):
        token = identity.get_verification_token(self.account_id)
        identity.verify_email(token)

        run = notification.dispatch_due()

        self.assertEqual((run.claimed, run.sent, run.failed), (1, 0, 1))
        self.assertEqual(Outbox.objects.get().status, OutboxStatus.FAILED)
        self.assertEqual(self.adapter.sent, [])
