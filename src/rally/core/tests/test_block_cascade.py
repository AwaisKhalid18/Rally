"""The block cascade through M6's port - plan.md S12 AC2 and AC5.

It lives in Platform's tests because it spans M5, M6 and M7: M6 must not import M5
(the `.importlinter` contract), and M5 must not look at M7's tables. Platform may call
every facade (rule 14), so this is the one place the whole cascade can be asserted.
"""
import datetime as _dt

from django.test import TestCase

from rally.core import clock
from rally.core.ports.outbox import EVENT_INVITATION_CANCELLED_BY_BLOCK
from rally.core.wiring import registry
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.invitations.api import facade as invitations
from rally.modules.notification.api import facade as notification
from rally.modules.profiles.api import facade as profiles
from rally.modules.safety.api import facade as safety
from rally.modules.safety.api.ports import PENDING_INVITATION_CANCELLER

PASSWORD = "longenough"
VENUE = "Rally Courts, F-7"
AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
]


def at(day_offset: int, hour: int) -> _dt.datetime:
    midnight = clock.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + _dt.timedelta(days=day_offset, hours=hour)


class CascadeCase(TestCase):
    def setUp(self):
        self.adapter = notification.RecordingEmailAdapter()
        previous = notification.set_email_adapter(self.adapter)
        self.addCleanup(notification.set_email_adapter, previous)
        profiles.replace_areas(AREAS)
        self.first = self.make_player("first")
        self.second = self.make_player("second")
        self.third = self.make_player("third")

    def make_player(self, name):
        account_id = identity.register(f"{name}@example.com", PASSWORD).account_id
        assert profiles.save_profile(account_id, name.title(), "intermediate", "isb-f7").ok
        identity.verify_email(identity.get_verification_token(account_id))
        assert availability.add_slot(account_id, at(1, 8), at(1, 23)).ok
        return account_id

    def send(self, sender, recipient, start=18, end=20):
        result = invitations.send(
            sender_account_id=sender,
            recipient_account_id=recipient,
            starts_at=at(1, start),
            ends_at=at(1, end),
            venue=VENUE,
        )
        assert result.ok, result.errors
        return result.invitation_id

    def status(self, invitation_id, viewer):
        record = invitations.get_for_participant(invitation_id, viewer)
        return record.status if record else None


class TheWiringTests(TestCase):
    """AC5 - the port is registered at startup."""

    def test_both_ports_are_bound(self):
        self.assertIn("OutboxAppender", registry.registered())
        self.assertIn(PENDING_INVITATION_CANCELLER, registry.registered())

    def test_the_canceller_resolves_to_something_that_can_be_called(self):
        from rally.modules.safety.api.ports import pending_invitation_canceller

        implementation = pending_invitation_canceller()

        self.assertTrue(callable(getattr(implementation, "cancel_pending_between", None)))

    # The matching "M6 holds no import of M5" assertion lives in M6's own tests: it
    # has to read M6's internals, which Platform may not do (rule 2). The contract
    # `safety-depends-on-nothing` in .importlinter is the guard either way.


class ThePendingInvitationsGoTests(CascadeCase):
    """AC2."""

    def test_a_pending_invitation_the_blocker_sent_is_cancelled(self):
        invitation_id = self.send(self.first, self.second)

        result = safety.block(self.first, self.second)

        self.assertEqual(result.cancelled_invitation_ids, (invitation_id,))
        self.assertEqual(self.status(invitation_id, self.first), "cancelled")

    def test_a_pending_invitation_the_blocker_received_is_cancelled_too(self):
        """'All Pending invitations between the two players' - both directions."""
        invitation_id = self.send(self.second, self.first)

        safety.block(self.first, self.second)

        self.assertEqual(self.status(invitation_id, self.first), "cancelled")

    def test_both_directions_go_in_one_block(self):
        sent = self.send(self.first, self.second, 18, 20)
        received = self.send(self.second, self.first, 20, 22)

        result = safety.block(self.first, self.second)

        self.assertEqual(sorted(result.cancelled_invitation_ids), sorted([sent, received]))
        self.assertEqual(self.status(sent, self.first), "cancelled")
        self.assertEqual(self.status(received, self.first), "cancelled")

    def test_invitations_with_other_players_are_untouched(self):
        mine = self.send(self.first, self.second)
        elsewhere = self.send(self.first, self.third)

        safety.block(self.first, self.second)

        self.assertEqual(self.status(mine, self.first), "cancelled")
        self.assertEqual(self.status(elsewhere, self.first), "pending")

    def test_a_terminal_invitation_is_left_exactly_as_it_was(self):
        """Nothing leaves a terminal status, not even for a block (ASR-07)."""
        declined = self.send(self.first, self.second)
        invitations.decline(declined, self.second)

        result = safety.block(self.first, self.second)

        self.assertEqual(result.cancelled_invitation_ids, ())
        self.assertEqual(self.status(declined, self.first), "declined")

    def test_blocking_with_nothing_pending_cancels_nothing(self):
        result = safety.block(self.first, self.second)

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.cancelled_invitation_ids, ())

    def test_neither_player_can_send_a_new_invitation_afterwards(self):
        """AC1 - in both directions."""
        safety.block(self.first, self.second)

        self.assertEqual(
            invitations.send(
                sender_account_id=self.first,
                recipient_account_id=self.second,
                starts_at=at(1, 18),
                ends_at=at(1, 20),
                venue=VENUE,
            ).errors.get("form"),
            invitations.BLOCKED,
        )
        self.assertEqual(
            invitations.send(
                sender_account_id=self.second,
                recipient_account_id=self.first,
                starts_at=at(1, 18),
                ends_at=at(1, 20),
                venue=VENUE,
            ).errors.get("form"),
            invitations.BLOCKED,
        )


class ConfirmedGamesSurviveTests(CascadeCase):
    """AC2 - 'existing confirmed games are unaffected until either player cancels'."""

    def test_the_game_and_its_invitation_are_untouched(self):
        invitation_id = self.send(self.first, self.second)
        game_id = invitations.accept(invitation_id, self.second).game_id

        safety.block(self.first, self.second)

        self.assertEqual(self.status(invitation_id, self.first), "accepted")
        detail = invitations.get_game_for_participant(game_id, self.first)
        self.assertIsNotNone(detail)
        self.assertFalse(detail.is_cancelled)

    def test_either_player_can_still_cancel_the_game(self):
        invitation_id = self.send(self.first, self.second)
        game_id = invitations.accept(invitation_id, self.second).game_id
        safety.block(self.first, self.second)

        self.assertTrue(invitations.cancel_game(game_id, self.second).ok)

    def test_a_pending_invitation_goes_while_the_game_stays(self):
        accepted = self.send(self.first, self.second, 18, 20)
        invitations.accept(accepted, self.second)
        pending = self.send(self.second, self.first, 20, 22)

        safety.block(self.first, self.second)

        self.assertEqual(self.status(accepted, self.first), "accepted")
        self.assertEqual(self.status(pending, self.first), "cancelled")


class WhatTheCascadeSaysTests(CascadeCase):
    """AC2 - 'outbox records are written', and what they are allowed to say."""

    def test_one_notification_per_cancelled_invitation(self):
        self.send(self.first, self.second, 18, 20)
        self.send(self.second, self.first, 20, 22)
        notification.mark_all_read(self.second)

        safety.block(self.first, self.second)

        cascade = [
            item
            for item in notification.list_for_player(self.second)
            if item.notification_type == EVENT_INVITATION_CANCELLED_BY_BLOCK
        ]
        self.assertEqual(len(cascade), 2)

    def test_it_goes_to_the_player_who_did_not_block(self):
        self.send(self.first, self.second)

        safety.block(self.first, self.second)

        types = [item.notification_type for item in notification.list_for_player(self.first)]
        self.assertNotIn(EVENT_INVITATION_CANCELLED_BY_BLOCK, types)

    def test_the_notification_never_says_a_block_happened(self):
        """The PRD does not resolve whether the blocked player learns of the block, and
        saying so would make blocking unsafe to use. Nothing in the wording may hint."""
        self.send(self.first, self.second)
        safety.block(self.first, self.second)
        notification.dispatch_due()

        from rally.core.shapers.notifications import notification_views

        item = notification.list_for_player(self.second)[0]
        (view,) = notification_views([item])
        email = [m for m in self.adapter.sent if "invitation was cancelled" in m["subject"]]

        for text in (view.text, email[0]["subject"], email[0]["body"]):
            lowered = text.lower()
            for word in ("block", "blocked", "blocking"):
                self.assertNotIn(word, lowered, f"the wording discloses the block: {text!r}")

    def test_the_outbox_record_carries_ids_only(self):
        """Rule 6 and ASR-11."""
        invitation_id = self.send(self.first, self.second)

        safety.block(self.first, self.second)

        item = notification.list_for_player(self.second)[0]
        self.assertEqual(item.invitation_id, invitation_id)
        for value in vars(item).values():
            self.assertNotIn("@", str(value))

    def test_nothing_is_queued_when_nothing_was_cancelled(self):
        notification.mark_all_read(self.second)

        safety.block(self.first, self.second)

        types = [item.notification_type for item in notification.list_for_player(self.second)]
        self.assertNotIn(EVENT_INVITATION_CANCELLED_BY_BLOCK, types)

    def test_no_contact_address_reaches_a_log_line(self):
        self.send(self.first, self.second)

        with self.assertLogs("rally.operation", level="INFO") as captured:
            safety.block(self.first, self.second)
            notification.dispatch_due()

        written = "\n".join(captured.output)
        self.assertIn("operation=safety.block outcome=blocked", written)
        self.assertIn("invitations_cancelled=1", written)
        self.assertNotIn("@", written)


class UnblockingDoesNotUndoTheCascadeTests(CascadeCase):
    """AC3 - 'unblocking restores visibility but does not restore cancelled
    invitations'."""

    def test_the_cancelled_invitation_stays_cancelled(self):
        invitation_id = self.send(self.first, self.second)
        safety.block(self.first, self.second)

        safety.unblock(self.first, self.second)

        self.assertEqual(self.status(invitation_id, self.first), "cancelled")

    def test_it_cannot_be_accepted_after_the_unblock(self):
        invitation_id = self.send(self.first, self.second)
        safety.block(self.first, self.second)
        safety.unblock(self.first, self.second)

        result = invitations.accept(invitation_id, self.second)

        self.assertEqual(result.error, invitations.NO_LONGER_PENDING)

    def test_a_new_invitation_can_be_sent_instead(self):
        self.send(self.first, self.second)
        safety.block(self.first, self.second)
        safety.unblock(self.first, self.second)

        result = invitations.send(
            sender_account_id=self.first,
            recipient_account_id=self.second,
            starts_at=at(1, 18),
            ends_at=at(1, 20),
            venue=VENUE,
        )

        self.assertTrue(result.ok, result.errors)


class TheBlockAndTheCascadeCommitTogetherTests(CascadeCase):
    """AC2 - 'inside M6's transaction'.

    The point of putting the cascade inside M6's transaction is that a half-done block
    cannot exist. Asserted by making the cascade fail: the block must not survive it.
    """

    def test_a_failing_cascade_rolls_the_block_back(self):
        invitation_id = self.send(self.first, self.second)

        class Exploding:
            def cancel_pending_between(self, first_account_id, second_account_id):
                raise RuntimeError("the cascade failed")

        previous = registry.resolve(PENDING_INVITATION_CANCELLER)
        registry.register(PENDING_INVITATION_CANCELLER, Exploding())
        self.addCleanup(registry.register, PENDING_INVITATION_CANCELLER, previous)

        with self.assertRaises(RuntimeError):
            safety.block(self.first, self.second)

        self.assertFalse(
            safety.is_blocked_between(self.first, self.second),
            "the block committed although the cascade failed",
        )
        self.assertEqual(self.status(invitation_id, self.first), "pending")
