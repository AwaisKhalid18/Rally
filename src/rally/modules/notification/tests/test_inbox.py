"""M7's in-app inbox - plan.md S10 AC2, AC3, AC4.

These are M7's own tests, so they may read M7's internals. They reach M1 only through
its facade (rule 2).
"""
import datetime as _dt

from django.test import TestCase

from rally.core import clock
from rally.core.ports.outbox import (
    EVENT_INVITATION_ACCEPTED,
    EVENT_INVITATION_CANCELLED,
    RECIPIENT_KEY,
    append_outbox,
)
from rally.modules.identity.api import facade as identity
from rally.modules.notification.api import facade as notification
from rally.modules.notification.internal import adapters
from rally.modules.notification.internal.models import Notification, Outbox, OutboxStatus

PASSWORD = "longenough"


class InboxCase(TestCase):
    def setUp(self):
        self.adapter = adapters.RecordingEmailAdapter()
        previous = adapters.set_adapter(self.adapter)
        self.addCleanup(adapters.set_adapter, previous)
        self.player = identity.register("player@example.com", PASSWORD).account_id
        self.other = identity.register("other@example.com", PASSWORD).account_id
        # Registration itself notifies, and that record is part of the inbox. Clearing
        # it keeps each test about the event it appends.
        Notification.objects.all().delete()
        Outbox.objects.all().delete()

    def notify(self, account_id, event=EVENT_INVITATION_ACCEPTED, **refs):
        return append_outbox(event, {RECIPIENT_KEY: account_id, **refs})


class TheNotificationExistsBeforeTheWorkerRunsTests(InboxCase):
    """AC2 - 'the in-app notification always exists'.

    It is written by the appender, in the transaction that changed the business state,
    so a stopped worker or a dead provider cannot cost a player their inbox (ASR-12).
    """

    def test_appending_an_event_creates_the_notification_at_once(self):
        self.notify(self.player, invitation_id=7)

        (item,) = notification.list_for_player(self.player)

        self.assertEqual(item.notification_type, EVENT_INVITATION_ACCEPTED)
        self.assertEqual(item.invitation_id, 7)
        self.assertFalse(item.is_read)

    def test_it_is_there_although_nothing_has_been_dispatched(self):
        self.notify(self.player)

        self.assertEqual(self.adapter.sent, [], "precondition: the worker has not run")
        self.assertEqual(len(notification.list_for_player(self.player)), 1)

    def test_dispatching_does_not_create_a_second_one(self):
        self.notify(self.player)

        notification.dispatch_due()

        self.assertEqual(len(notification.list_for_player(self.player)), 1)

    def test_a_retried_record_still_has_exactly_one(self):
        previous = adapters.set_adapter(adapters.AlwaysFailingEmailAdapter())
        self.addCleanup(adapters.set_adapter, previous)
        self.notify(self.player)

        notification.dispatch_due()
        Outbox.objects.all().update(next_attempt_at=clock.now())
        notification.dispatch_due()

        self.assertEqual(len(notification.list_for_player(self.player)), 1)


class OnlyYourOwnInboxTests(InboxCase):
    """AC2 and ASR-04 - a player reads their own notifications and nobody else's."""

    def test_an_event_for_another_player_is_not_in_your_inbox(self):
        self.notify(self.other)

        self.assertEqual(notification.list_for_player(self.player), [])
        self.assertEqual(len(notification.list_for_player(self.other)), 1)

    def test_you_cannot_mark_another_players_notification_read(self):
        self.notify(self.other)
        (theirs,) = notification.list_for_player(self.other)

        self.assertFalse(notification.mark_read(theirs.notification_id, self.player))

        (still,) = notification.list_for_player(self.other)
        self.assertFalse(still.is_read)

    def test_a_notification_that_does_not_exist_gives_the_same_answer(self):
        """ASR-05: a different answer would confirm the other one exists."""
        self.assertFalse(notification.mark_read(999_999, self.player))


class ReadAndUnreadTests(InboxCase):
    """AC2 - read/unread."""

    def test_a_new_notification_is_unread_and_counted(self):
        self.notify(self.player)

        self.assertEqual(notification.unread_count(self.player), 1)

    def test_marking_it_read_clears_the_count(self):
        self.notify(self.player)
        (item,) = notification.list_for_player(self.player)

        self.assertTrue(notification.mark_read(item.notification_id, self.player))

        self.assertEqual(notification.unread_count(self.player), 0)
        (item,) = notification.list_for_player(self.player)
        self.assertTrue(item.is_read)

    def test_marking_it_read_twice_is_still_success(self):
        self.notify(self.player)
        (item,) = notification.list_for_player(self.player)
        notification.mark_read(item.notification_id, self.player)

        self.assertTrue(notification.mark_read(item.notification_id, self.player))

    def test_a_read_notification_stays_in_the_list(self):
        """Read is not deleted: the inbox is a record of what happened."""
        self.notify(self.player)
        (item,) = notification.list_for_player(self.player)
        notification.mark_read(item.notification_id, self.player)

        self.assertEqual(len(notification.list_for_player(self.player)), 1)

    def test_mark_all_read_clears_them_and_reports_how_many(self):
        self.notify(self.player)
        self.notify(self.player, event=EVENT_INVITATION_CANCELLED)

        self.assertEqual(notification.mark_all_read(self.player), 2)
        self.assertEqual(notification.unread_count(self.player), 0)
        self.assertEqual(notification.mark_all_read(self.player), 0)

    def test_mark_all_read_touches_nobody_elses(self):
        self.notify(self.other)
        self.notify(self.player)

        notification.mark_all_read(self.player)

        self.assertEqual(notification.unread_count(self.other), 1)

    def test_the_newest_notification_comes_first(self):
        self.notify(self.player, invitation_id=1)
        Notification.objects.all().update(created_at=clock.now() - _dt.timedelta(hours=1))
        self.notify(self.player, invitation_id=2)

        order = [item.invitation_id for item in notification.list_for_player(self.player)]

        self.assertEqual(order, [2, 1])


class EmailStatusWordingTests(InboxCase):
    """AC3 - queued, sent or failed, and never 'delivered'."""

    def test_a_fresh_notification_reports_queued(self):
        self.notify(self.player)

        (item,) = notification.list_for_player(self.player)

        self.assertEqual(item.email_status, OutboxStatus.QUEUED)

    def test_after_the_provider_accepts_it_reports_sent(self):
        self.notify(self.player)

        notification.dispatch_due()

        (item,) = notification.list_for_player(self.player)
        self.assertEqual(item.email_status, OutboxStatus.SENT)

    def test_after_the_retries_run_out_it_reports_failed(self):
        previous = adapters.set_adapter(adapters.AlwaysFailingEmailAdapter())
        self.addCleanup(adapters.set_adapter, previous)
        self.notify(self.player)

        for _ in range(notification.MAX_ATTEMPTS):
            Outbox.objects.all().update(next_attempt_at=clock.now())
            notification.dispatch_due()

        (item,) = notification.list_for_player(self.player)
        self.assertEqual(item.email_status, OutboxStatus.FAILED)

    def test_the_only_statuses_possible_are_those_three(self):
        self.notify(self.player)

        (item,) = notification.list_for_player(self.player)

        self.assertIn(item.email_status, notification.EMAIL_STATUSES)
        self.assertNotIn("delivered", [str(status) for status in notification.EMAIL_STATUSES])

    def test_a_notification_with_no_outbox_record_gives_a_reason_not_a_blank(self):
        """Rule 13. `source_outbox` is nullable, so the absent case must be honest."""
        Notification.objects.create(
            recipient_account_id=self.player,
            notification_type=EVENT_INVITATION_ACCEPTED,
            created_at=clock.now(),
            source_outbox=None,
        )

        (item,) = notification.list_for_player(self.player)

        self.assertIsNone(item.email_status)
        self.assertEqual(item.email_status_reason, notification.NO_EMAIL_REASON)


class NoContactDataInTheInboxTests(InboxCase):
    """AC4 and rule 6 - nothing M7 publishes can carry an address."""

    def test_no_field_of_a_published_record_contains_an_at_sign(self):
        self.notify(self.player, invitation_id=3)

        (item,) = notification.list_for_player(self.player)

        for value in vars(item).values():
            self.assertNotIn("@", str(value))

    def test_the_notification_row_itself_holds_no_address(self):
        self.notify(self.player)

        row = Notification.objects.get()

        for field in row._meta.fields:
            self.assertNotIn("@", str(getattr(row, field.attname)))
