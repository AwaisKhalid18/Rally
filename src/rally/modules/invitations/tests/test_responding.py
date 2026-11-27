"""M5 accept and decline - plan.md S8 AC1, AC2, AC3, AC5."""
import datetime as _dt

from django.db import IntegrityError, transaction
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


class RespondCase(TestCase):
    def setUp(self):
        profiles.replace_areas(AREAS)
        self.sender = self.make_player("sender", slot=(1, 8, 23))
        self.recipient = self.make_player("recipient", slot=(1, 8, 23))
        self.invitation_id = self.send().invitation_id

    def make_player(self, name, slot=None):
        account_id = identity.register(f"{name}@example.com", PASSWORD).account_id
        assert profiles.save_profile(account_id, name.title(), "intermediate", "isb-f7").ok
        identity.verify_email(identity.get_verification_token(account_id))
        if slot:
            day, start, end = slot
            assert availability.add_slot(account_id, at(day, start), at(day, end)).ok
        return account_id

    def send(self, sender=None, recipient=None, start=18, end=20):
        result = invitations.send(
            sender_account_id=sender or self.sender,
            recipient_account_id=recipient or self.recipient,
            starts_at=at(1, start),
            ends_at=at(1, end),
            venue=VENUE,
        )
        assert result.ok, result.errors
        return result


class AcceptTests(RespondCase):
    def test_accepting_creates_a_confirmed_game(self):
        result = invitations.accept(self.invitation_id, self.recipient)

        self.assertTrue(result.ok, result.error)
        game = ConfirmedGame.objects.get(pk=result.game_id)
        self.assertEqual(game.invitation_id, self.invitation_id)
        self.assertEqual(game.starts_at, at(1, 18))
        self.assertEqual(game.venue, VENUE)
        self.assertIsNone(game.cancelled_at)

    def test_the_invitation_stays_accepted_and_the_game_is_separate(self):
        """AC5 - two records, two concepts (PRD 6.1)."""
        invitations.accept(self.invitation_id, self.recipient)

        self.assertEqual(
            Invitation.objects.get(pk=self.invitation_id).status, InvitationStatus.ACCEPTED
        )
        self.assertEqual(ConfirmedGame.objects.count(), 1)

    def test_both_players_get_a_participant_row(self):
        """AC2 - the shape the no-double-booking invariant needs."""
        result = invitations.accept(self.invitation_id, self.recipient)

        accounts = set(
            GameParticipant.objects.filter(game_id=result.game_id).values_list(
                "account_id", flat=True
            )
        )
        self.assertEqual(accounts, {self.sender, self.recipient})

    def test_only_the_recipient_may_accept(self):
        """AC1."""
        result = invitations.accept(self.invitation_id, self.sender)

        self.assertEqual(result.error, invitations.NOT_THE_RECIPIENT)
        self.assertEqual(ConfirmedGame.objects.count(), 0)

    def test_a_stranger_may_not_accept(self):
        stranger = self.make_player("stranger")
        self.assertEqual(
            invitations.accept(self.invitation_id, stranger).error,
            invitations.NOT_THE_RECIPIENT,
        )

    def test_an_invitation_that_does_not_exist_says_so(self):
        self.assertEqual(
            invitations.accept(999_999, self.recipient).error, invitations.NOT_FOUND
        )

    def test_a_recorded_response_cannot_be_changed(self):
        """AC1 and AC3."""
        invitations.accept(self.invitation_id, self.recipient)

        again = invitations.accept(self.invitation_id, self.recipient)
        declined = invitations.decline(self.invitation_id, self.recipient)

        self.assertEqual(again.error, invitations.NO_LONGER_PENDING)
        self.assertEqual(declined.error, invitations.NO_LONGER_PENDING)
        self.assertEqual(
            Invitation.objects.get(pk=self.invitation_id).status, InvitationStatus.ACCEPTED
        )

    def test_an_expired_invitation_cannot_be_accepted_even_before_a_sweep_runs(self):
        """ASR-09 - expiry is judged here, at commit, not by the worker."""
        Invitation.objects.filter(pk=self.invitation_id).update(
            expires_at=clock.now() - _dt.timedelta(minutes=1)
        )

        result = invitations.accept(self.invitation_id, self.recipient)

        self.assertEqual(result.error, invitations.HAS_EXPIRED)
        self.assertEqual(ConfirmedGame.objects.count(), 0)
        # The stored status is untouched: the sweep updates display, not correctness.
        self.assertEqual(
            Invitation.objects.get(pk=self.invitation_id).status, InvitationStatus.PENDING
        )

    def test_a_recipient_who_removed_the_time_cannot_accept(self):
        """PRD 12.4 - availability is revalidated at acceptance."""
        for slot in availability.list_slots(self.recipient):
            availability.remove_slot(self.recipient, slot.slot_id)

        result = invitations.accept(self.invitation_id, self.recipient)

        self.assertEqual(result.error, invitations.NO_LONGER_AVAILABLE)
        self.assertEqual(ConfirmedGame.objects.count(), 0)


class NoDoubleBookingTests(RespondCase):
    """FR-15, AC3 - no player holds two overlapping confirmed games."""

    def test_an_overlapping_second_game_is_refused_with_a_sentence(self):
        invitations.accept(self.invitation_id, self.recipient)
        other_sender = self.make_player("other", slot=(1, 8, 23))
        second = self.send(sender=other_sender, start=19, end=21).invitation_id

        result = invitations.accept(second, self.recipient)

        self.assertEqual(result.error, invitations.OVERLAPPING_GAME)
        self.assertEqual(ConfirmedGame.objects.count(), 1)

    def test_back_to_back_games_do_not_conflict(self):
        invitations.accept(self.invitation_id, self.recipient)
        other_sender = self.make_player("other", slot=(1, 8, 23))
        second = self.send(sender=other_sender, start=20, end=22).invitation_id

        self.assertTrue(invitations.accept(second, self.recipient).ok)
        self.assertEqual(ConfirmedGame.objects.count(), 2)

    def test_the_senders_own_diary_is_protected_too(self):
        """AC2 - 'no overlapping confirmed game for EITHER player'."""
        invitations.accept(self.invitation_id, self.recipient)
        other_recipient = self.make_player("other", slot=(1, 8, 23))
        second = self.send(recipient=other_recipient, start=19, end=21).invitation_id

        result = invitations.accept(second, other_recipient)

        self.assertEqual(result.error, invitations.OVERLAPPING_GAME)

    def test_two_different_players_may_play_at_the_same_time(self):
        invitations.accept(self.invitation_id, self.recipient)
        third = self.make_player("third", slot=(1, 8, 23))
        fourth = self.make_player("fourth", slot=(1, 8, 23))
        second = self.send(sender=third, recipient=fourth).invitation_id

        self.assertTrue(invitations.accept(second, fourth).ok)
        self.assertEqual(ConfirmedGame.objects.count(), 2)

    def test_the_database_refuses_an_overlap_the_application_check_did_not_see(self):
        """AC5 - the constraint is the backstop, not the message (ADR-004)."""
        result = invitations.accept(self.invitation_id, self.recipient)
        game = ConfirmedGame.objects.get(pk=result.game_id)

        with self.assertRaises(IntegrityError), transaction.atomic():
            GameParticipant.objects.create(
                game=game,
                account_id=self.recipient,
                starts_at=at(1, 19),
                ends_at=at(1, 21),
            )

    def test_a_cancelled_participation_stops_blocking_the_time(self):
        """G-10 - cancelling frees the time without a slot write."""
        result = invitations.accept(self.invitation_id, self.recipient)
        GameParticipant.objects.filter(game_id=result.game_id).update(cancelled_at=clock.now())
        ConfirmedGame.objects.filter(pk=result.game_id).update(cancelled_at=clock.now())

        other_sender = self.make_player("other", slot=(1, 8, 23))
        second = self.send(sender=other_sender, start=19, end=21).invitation_id

        self.assertTrue(invitations.accept(second, self.recipient).ok)


class DeclineTests(RespondCase):
    def test_declining_needs_no_reason_and_creates_nothing(self):
        """AC1."""
        result = invitations.decline(self.invitation_id, self.recipient)

        self.assertTrue(result.ok, result.error)
        self.assertEqual(
            Invitation.objects.get(pk=self.invitation_id).status, InvitationStatus.DECLINED
        )
        self.assertEqual(ConfirmedGame.objects.count(), 0)

    def test_only_the_recipient_may_decline(self):
        self.assertEqual(
            invitations.decline(self.invitation_id, self.sender).error,
            invitations.NOT_THE_RECIPIENT,
        )

    def test_a_declined_invitation_cannot_then_be_accepted(self):
        invitations.decline(self.invitation_id, self.recipient)

        self.assertEqual(
            invitations.accept(self.invitation_id, self.recipient).error,
            invitations.NO_LONGER_PENDING,
        )

    def test_an_expired_invitation_cannot_be_declined(self):
        Invitation.objects.filter(pk=self.invitation_id).update(
            expires_at=clock.now() - _dt.timedelta(minutes=1)
        )

        self.assertEqual(
            invitations.decline(self.invitation_id, self.recipient).error,
            invitations.HAS_EXPIRED,
        )

    def test_declining_frees_nothing_because_nothing_was_reserved(self):
        """PRD 12.4 - a pending invitation never reserved time."""
        invitations.decline(self.invitation_id, self.recipient)

        self.assertTrue(
            availability.has_availability(self.recipient, at(1, 18), at(1, 20))
        )


class GameLookupTests(RespondCase):
    def test_a_participant_can_see_the_game_their_invitation_created(self):
        invitations.accept(self.invitation_id, self.recipient)

        for viewer in (self.sender, self.recipient):
            with self.subTest(viewer=viewer):
                game = invitations.get_game_for_invitation(self.invitation_id, viewer)
                self.assertIsNotNone(game)
                self.assertEqual(game.venue, VENUE)
                self.assertFalse(game.is_cancelled)

    def test_a_non_participant_cannot(self):
        invitations.accept(self.invitation_id, self.recipient)
        stranger = self.make_player("stranger")

        self.assertIsNone(invitations.get_game_for_invitation(self.invitation_id, stranger))

    def test_a_pending_invitation_has_no_game(self):
        self.assertIsNone(
            invitations.get_game_for_invitation(self.invitation_id, self.recipient)
        )
