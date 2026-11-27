"""Confirmed games and cancelling one - plan.md S11 AC1, AC2, AC3, AC4."""
import datetime as _dt

from django.test import TestCase

from rally.core import clock
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.invitations.api import facade as invitations
from rally.modules.invitations.internal.models import (
    ConfirmedGame,
    GameParticipant,
    Invitation,
    InvitationStatus,
)
from rally.modules.profiles.api import facade as profiles

PASSWORD = "longenough"
AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
]
VENUE = "Rally Courts, F-7"


def at(day_offset: int, hour: int) -> _dt.datetime:
    midnight = clock.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + _dt.timedelta(days=day_offset, hours=hour)


class GameCase(TestCase):
    def setUp(self):
        profiles.replace_areas(AREAS)
        self.sender = self.make_player("sender")
        self.recipient = self.make_player("recipient")
        self.stranger = self.make_player("stranger")
        self.invitation_id = self.send(self.sender)
        self.game_id = invitations.accept(self.invitation_id, self.recipient).game_id

    def make_player(self, name):
        account_id = identity.register(f"{name}@example.com", PASSWORD).account_id
        assert profiles.save_profile(account_id, name.title(), "intermediate", "isb-f7").ok
        identity.verify_email(identity.get_verification_token(account_id))
        assert availability.add_slot(account_id, at(1, 8), at(1, 23)).ok
        return account_id

    def send(self, sender, start=18, end=20):
        result = invitations.send(
            sender_account_id=sender,
            recipient_account_id=self.recipient,
            starts_at=at(1, start),
            ends_at=at(1, end),
            venue=VENUE,
        )
        assert result.ok, result.errors
        return result.invitation_id

    def freeze(self, when):
        previous = clock.set_clock(clock.FrozenClock(when))
        self.addCleanup(clock.set_clock, previous)


class BothPlayersSeeTheSameGameTests(GameCase):
    """AC1."""

    def test_each_participant_has_it_as_an_upcoming_game(self):
        for account_id in (self.sender, self.recipient):
            upcoming, finished = invitations.list_games_for_player(account_id)

            self.assertEqual([game.game_id for game in upcoming], [self.game_id])
            self.assertEqual(finished, [])

    def test_the_facts_are_the_same_for_both_of_them(self):
        (theirs,), _ = invitations.list_games_for_player(self.sender)
        (ours,), _ = invitations.list_games_for_player(self.recipient)

        self.assertEqual(
            (theirs.starts_at, theirs.ends_at, theirs.venue, theirs.can_cancel),
            (ours.starts_at, ours.ends_at, ours.venue, ours.can_cancel),
        )

    def test_each_is_told_who_the_other_player_is(self):
        (for_sender,), _ = invitations.list_games_for_player(self.sender)
        (for_recipient,), _ = invitations.list_games_for_player(self.recipient)

        self.assertEqual(for_sender.other_party_account_id, self.recipient)
        self.assertEqual(for_recipient.other_party_account_id, self.sender)

    def test_a_player_who_is_not_in_it_sees_nothing(self):
        self.assertEqual(invitations.list_games_for_player(self.stranger), ([], []))

    def test_a_non_participant_cannot_read_it(self):
        """ASR-05."""
        self.assertIsNone(invitations.get_game_for_participant(self.game_id, self.stranger))

    def test_a_game_whose_end_time_has_passed_is_no_longer_upcoming(self):
        self.freeze(at(1, 21))

        upcoming, finished = invitations.list_games_for_player(self.sender)

        self.assertEqual(upcoming, [])
        self.assertEqual([game.game_id for game in finished], [self.game_id])


class WhoMayCancelAndWhenTests(GameCase):
    """AC2 - either participant, before the start time."""

    def test_the_recipient_may_cancel(self):
        result = invitations.cancel_game(self.game_id, self.recipient)

        self.assertTrue(result.ok, result.error)

    def test_the_sender_may_cancel_too(self):
        """PRD 12.4: 'either of the two players'."""
        result = invitations.cancel_game(self.game_id, self.sender)

        self.assertTrue(result.ok, result.error)

    def test_a_stranger_gets_a_not_found_not_a_refusal(self):
        """ASR-05: naming it 'forbidden' would confirm the game exists."""
        result = invitations.cancel_game(self.game_id, self.stranger)

        self.assertEqual(result.error, invitations.GAME_NOT_FOUND)
        self.assertFalse(ConfirmedGame.objects.get(pk=self.game_id).is_cancelled)

    def test_a_game_that_does_not_exist_says_the_same(self):
        self.assertEqual(
            invitations.cancel_game(999_999, self.sender).error, invitations.GAME_NOT_FOUND
        )

    def test_one_second_before_the_start_it_can_still_be_cancelled(self):
        self.freeze(at(1, 18) - _dt.timedelta(seconds=1))

        self.assertTrue(invitations.cancel_game(self.game_id, self.sender).ok)

    def test_at_the_start_time_exactly_it_is_too_late(self):
        """The boundary is inclusive of 'started'."""
        self.freeze(at(1, 18))

        result = invitations.cancel_game(self.game_id, self.sender)

        self.assertEqual(result.error, invitations.ALREADY_STARTED)
        self.assertFalse(ConfirmedGame.objects.get(pk=self.game_id).is_cancelled)

    def test_a_game_in_progress_cannot_be_cancelled(self):
        self.freeze(at(1, 19))

        self.assertEqual(
            invitations.cancel_game(self.game_id, self.sender).error,
            invitations.ALREADY_STARTED,
        )

    def test_a_started_game_no_longer_offers_cancelling(self):
        self.freeze(at(1, 18))

        detail = invitations.get_game_for_participant(self.game_id, self.sender)

        self.assertTrue(detail.has_started)
        self.assertFalse(detail.can_cancel)

    def test_cancelling_twice_is_refused_the_second_time(self):
        invitations.cancel_game(self.game_id, self.sender)

        result = invitations.cancel_game(self.game_id, self.recipient)

        self.assertEqual(result.error, invitations.ALREADY_CANCELLED)

    def test_a_cancelled_game_cannot_be_cancelled_by_the_other_player_either(self):
        invitations.cancel_game(self.game_id, self.recipient)

        self.assertEqual(
            invitations.cancel_game(self.game_id, self.sender).error,
            invitations.ALREADY_CANCELLED,
        )


class WhatCancellingChangesTests(GameCase):
    """AC3."""

    def test_both_participant_rows_are_stamped(self):
        invitations.cancel_game(self.game_id, self.sender)

        rows = GameParticipant.objects.filter(game_id=self.game_id)

        self.assertEqual(rows.count(), 2)
        self.assertEqual(rows.filter(cancelled_at__isnull=True).count(), 0)

    def test_the_game_records_who_cancelled_it(self):
        invitations.cancel_game(self.game_id, self.recipient)

        game = ConfirmedGame.objects.get(pk=self.game_id)

        self.assertTrue(game.is_cancelled)
        self.assertEqual(game.cancelled_by_account_id, self.recipient)

    def test_each_player_is_told_whether_it_was_their_own_doing(self):
        invitations.cancel_game(self.game_id, self.recipient)

        _, (theirs,) = invitations.list_games_for_player(self.recipient)
        _, (others,) = invitations.list_games_for_player(self.sender)

        self.assertTrue(theirs.cancelled_by_you)
        self.assertFalse(others.cancelled_by_you)

    def test_the_invitation_stays_accepted(self):
        """PRD 12.3: an accepted invitation and a confirmed game are different things."""
        invitations.cancel_game(self.game_id, self.sender)

        self.assertEqual(
            Invitation.objects.get(pk=self.invitation_id).status, InvitationStatus.ACCEPTED
        )

    def test_the_time_is_free_again_so_a_new_game_can_be_accepted(self):
        """AC3, G-10 - the point of the whole thing, asserted by using the time."""
        other_sender = self.make_player("other")
        overlapping = self.send(other_sender, start=19, end=21)
        self.assertEqual(
            invitations.accept(overlapping, self.recipient).error,
            invitations.OVERLAPPING_GAME,
            "precondition: the live game blocks the time",
        )

        invitations.cancel_game(self.game_id, self.sender)

        self.assertTrue(invitations.accept(overlapping, self.recipient).ok)

    def test_no_availability_slot_was_touched(self):
        """G-10 - nothing was ever consumed, so nothing is restored."""
        before = len(availability.list_slots(self.recipient))

        invitations.cancel_game(self.game_id, self.sender)

        self.assertEqual(len(availability.list_slots(self.recipient)), before)
        self.assertTrue(availability.has_availability(self.recipient, at(1, 18), at(1, 20)))

    def test_it_leaves_the_games_history_in_place(self):
        invitations.cancel_game(self.game_id, self.sender)

        upcoming, finished = invitations.list_games_for_player(self.sender)

        self.assertEqual(upcoming, [])
        self.assertEqual([game.game_id for game in finished], [self.game_id])
        self.assertTrue(finished[0].is_cancelled)


class ARefusedCancellationChangesNothingTests(GameCase):
    """AC4's other half stays in Platform's test: M5 may not look at M7's tables
    (rules 2, 3), so who was notified is asserted where M7's facade is in reach."""

    def test_a_refused_cancellation_leaves_the_game_exactly_as_it_was(self):
        self.freeze(at(1, 18))

        invitations.cancel_game(self.game_id, self.sender)

        game = ConfirmedGame.objects.get(pk=self.game_id)
        self.assertFalse(game.is_cancelled)
        self.assertIsNone(game.cancelled_by_account_id)
        self.assertEqual(
            GameParticipant.objects.filter(game_id=self.game_id, cancelled_at__isnull=True).count(),
            2,
        )
