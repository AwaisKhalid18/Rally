"""M5 cancellation and expiry - plan.md S9 AC1, AC2, AC3."""
import datetime as _dt

from django.test import TestCase

from rally.core import clock
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.invitations.api import facade as invitations
from rally.modules.invitations.internal.models import Invitation, InvitationStatus
from rally.modules.profiles.api import facade as profiles

PASSWORD = "longenough"
AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
]
VENUE = "Rally Courts, F-7"


def at(day_offset: int, hour: int) -> _dt.datetime:
    midnight = clock.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + _dt.timedelta(days=day_offset, hours=hour)


class LifecycleCase(TestCase):
    def setUp(self):
        profiles.replace_areas(AREAS)
        self.sender = self.make_player("sender")
        self.recipient = self.make_player("recipient")
        self.invitation_id = self.send()

    def make_player(self, name):
        account_id = identity.register(f"{name}@example.com", PASSWORD).account_id
        assert profiles.save_profile(account_id, name.title(), "intermediate", "isb-f7").ok
        identity.verify_email(identity.get_verification_token(account_id))
        assert availability.add_slot(account_id, at(1, 8), at(1, 23)).ok
        return account_id

    def send(self, sender=None, start=18, end=20):
        result = invitations.send(
            sender_account_id=sender or self.sender,
            recipient_account_id=self.recipient,
            starts_at=at(1, start),
            ends_at=at(1, end),
            venue=VENUE,
        )
        assert result.ok, result.errors
        return result.invitation_id

    def status(self, invitation_id=None):
        return Invitation.objects.get(pk=invitation_id or self.invitation_id).status

    def set_expiry(self, when):
        Invitation.objects.filter(pk=self.invitation_id).update(expires_at=when)


class CancelTests(LifecycleCase):
    """AC1."""

    def test_the_sender_cancels_a_pending_invitation(self):
        result = invitations.cancel_invitation(self.invitation_id, self.sender)

        self.assertTrue(result.ok, result.error)
        self.assertEqual(self.status(), InvitationStatus.CANCELLED)

    def test_only_the_sender_may_cancel(self):
        result = invitations.cancel_invitation(self.invitation_id, self.recipient)

        self.assertEqual(result.error, invitations.NOT_THE_SENDER)
        self.assertEqual(self.status(), InvitationStatus.PENDING)

    def test_a_stranger_may_not_cancel(self):
        stranger = self.make_player("stranger")
        self.assertEqual(
            invitations.cancel_invitation(self.invitation_id, stranger).error,
            invitations.NOT_THE_SENDER,
        )

    def test_an_invitation_that_does_not_exist_says_so(self):
        self.assertEqual(
            invitations.cancel_invitation(999_999, self.sender).error, invitations.NOT_FOUND
        )

    def test_an_accepted_invitation_cannot_be_cancelled(self):
        invitations.accept(self.invitation_id, self.recipient)

        result = invitations.cancel_invitation(self.invitation_id, self.sender)

        self.assertEqual(result.error, invitations.NO_LONGER_PENDING)
        self.assertEqual(self.status(), InvitationStatus.ACCEPTED)

    def test_a_declined_invitation_cannot_be_cancelled(self):
        invitations.decline(self.invitation_id, self.recipient)

        self.assertEqual(
            invitations.cancel_invitation(self.invitation_id, self.sender).error,
            invitations.NO_LONGER_PENDING,
        )

    def test_cancelling_twice_is_refused_the_second_time(self):
        invitations.cancel_invitation(self.invitation_id, self.sender)

        self.assertEqual(
            invitations.cancel_invitation(self.invitation_id, self.sender).error,
            invitations.NO_LONGER_PENDING,
        )

    def test_a_cancelled_invitation_cannot_then_be_accepted(self):
        invitations.cancel_invitation(self.invitation_id, self.sender)

        self.assertEqual(
            invitations.accept(self.invitation_id, self.recipient).error,
            invitations.NO_LONGER_PENDING,
        )

    def test_an_expired_invitation_is_reported_as_expired_not_cancellable(self):
        self.set_expiry(clock.now() - _dt.timedelta(seconds=1))

        self.assertEqual(
            invitations.cancel_invitation(self.invitation_id, self.sender).error,
            invitations.HAS_EXPIRED,
        )

    def test_cancelling_frees_nothing_because_nothing_was_reserved(self):
        invitations.cancel_invitation(self.invitation_id, self.sender)

        self.assertTrue(availability.has_availability(self.recipient, at(1, 18), at(1, 20)))


class ExpiryDeadlineTests(LifecycleCase):
    """AC2 and AC3 - the deadline, judged at the moment of the action."""

    def test_the_deadline_is_the_earlier_of_start_and_twenty_four_hours(self):
        """AC3."""
        row = Invitation.objects.get(pk=self.invitation_id)

        self.assertEqual(row.expires_at, min(row.created_at + invitations.EXPIRY_WINDOW, row.starts_at))

    def test_one_second_before_the_deadline_it_is_still_acceptable(self):
        """AC2."""
        deadline = clock.now() + _dt.timedelta(hours=1)
        self.set_expiry(deadline)
        previous = clock.set_clock(clock.FrozenClock(deadline - _dt.timedelta(seconds=1)))
        self.addCleanup(clock.set_clock, previous)

        self.assertTrue(invitations.accept(self.invitation_id, self.recipient).ok)

    def test_at_the_deadline_exactly_it_has_expired(self):
        """AC2 - the boundary is inclusive of expiry."""
        deadline = clock.now() + _dt.timedelta(hours=1)
        self.set_expiry(deadline)
        previous = clock.set_clock(clock.FrozenClock(deadline))
        self.addCleanup(clock.set_clock, previous)

        self.assertEqual(
            invitations.accept(self.invitation_id, self.recipient).error, invitations.HAS_EXPIRED
        )

    def test_an_expired_invitation_cannot_be_accepted_though_the_sweep_never_ran(self):
        """AC2 - correctness does not wait for the worker (ASR-09, ADR-005)."""
        self.set_expiry(clock.now() - _dt.timedelta(minutes=1))

        self.assertEqual(self.status(), InvitationStatus.PENDING, "precondition: sweep has not run")
        self.assertEqual(
            invitations.accept(self.invitation_id, self.recipient).error, invitations.HAS_EXPIRED
        )
        self.assertEqual(
            invitations.decline(self.invitation_id, self.recipient).error, invitations.HAS_EXPIRED
        )
        self.assertEqual(
            invitations.cancel_invitation(self.invitation_id, self.sender).error,
            invitations.HAS_EXPIRED,
        )


class ExpireSweepTests(LifecycleCase):
    """AC3 - the sweep refreshes what is displayed, and nothing else."""

    def test_it_marks_a_passed_invitation_expired(self):
        self.set_expiry(clock.now() - _dt.timedelta(minutes=1))

        self.assertEqual(invitations.expire_pending(), 1)
        self.assertEqual(self.status(), InvitationStatus.EXPIRED)

    def test_it_leaves_a_live_invitation_alone(self):
        self.assertEqual(invitations.expire_pending(), 0)
        self.assertEqual(self.status(), InvitationStatus.PENDING)

    def test_at_the_deadline_exactly_it_expires(self):
        deadline = clock.now() + _dt.timedelta(hours=1)
        self.set_expiry(deadline)
        previous = clock.set_clock(clock.FrozenClock(deadline))
        self.addCleanup(clock.set_clock, previous)

        self.assertEqual(invitations.expire_pending(), 1)

    def test_it_never_touches_a_terminal_status(self):
        accepted = self.invitation_id
        invitations.accept(accepted, self.recipient)
        Invitation.objects.filter(pk=accepted).update(
            expires_at=clock.now() - _dt.timedelta(days=1)
        )

        self.assertEqual(invitations.expire_pending(), 0)
        self.assertEqual(self.status(accepted), InvitationStatus.ACCEPTED)

    def test_running_it_twice_changes_nothing_the_second_time(self):
        self.set_expiry(clock.now() - _dt.timedelta(minutes=1))

        self.assertEqual(invitations.expire_pending(), 1)
        self.assertEqual(invitations.expire_pending(), 0)

    def test_it_expires_every_passed_invitation_in_one_pass(self):
        other_sender = self.make_player("other")
        second = self.send(sender=other_sender, start=20, end=22)
        Invitation.objects.all().update(expires_at=clock.now() - _dt.timedelta(minutes=1))

        self.assertEqual(invitations.expire_pending(), 2)
        self.assertEqual(self.status(second), InvitationStatus.EXPIRED)


class ExpiredMessageIsStableTests(LifecycleCase):
    """The reason must not depend on whether the sweep has run yet.

    Found by the sweep-vs-accept race: before the fix, an invitation past its deadline
    reported "no longer pending" once the sweep had refreshed its status, and "has
    expired" before that. Both refused correctly; only one said why.
    """

    def test_the_same_reason_before_and_after_the_sweep(self):
        self.set_expiry(clock.now() - _dt.timedelta(minutes=1))

        before = invitations.accept(self.invitation_id, self.recipient).error
        invitations.expire_pending()
        after = invitations.accept(self.invitation_id, self.recipient).error

        self.assertEqual(before, invitations.HAS_EXPIRED)
        self.assertEqual(after, invitations.HAS_EXPIRED)

    def test_that_holds_for_declining_and_cancelling_too(self):
        self.set_expiry(clock.now() - _dt.timedelta(minutes=1))
        invitations.expire_pending()

        self.assertEqual(
            invitations.decline(self.invitation_id, self.recipient).error,
            invitations.HAS_EXPIRED,
        )
        self.assertEqual(
            invitations.cancel_invitation(self.invitation_id, self.sender).error,
            invitations.HAS_EXPIRED,
        )

    def test_a_cancelled_invitation_still_reads_as_no_longer_pending(self):
        """Only expiry gets the specific wording; the other terminal states do not."""
        invitations.cancel_invitation(self.invitation_id, self.sender)

        self.assertEqual(
            invitations.accept(self.invitation_id, self.recipient).error,
            invitations.NO_LONGER_PENDING,
        )
