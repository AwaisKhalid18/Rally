"""AC4 - the two races, run for real against PostgreSQL.

`TransactionTestCase`, not `TestCase`: the threads need genuine commits, not a shared
outer transaction that would hide every interleaving the invariant is about (QA-03,
ASR-08, ADR-004).
"""
import datetime as _dt
import threading

from django.db import connection, connections
from django.test import TransactionTestCase

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


def run_together(*calls):
    """Run each callable in its own thread, released at the same instant.

    Each thread closes its own database connection afterwards, so the two really do
    contend on the database rather than sharing one connection.
    """
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait(timeout=10)
            results[index] = call()
        except Exception as error:  # surfaced by the assertions below
            results[index] = error
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(i, c)) for i, c in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


class RaceCase(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        profiles.replace_areas(AREAS)
        self.sender = self.make_player("sender")
        self.other_sender = self.make_player("othersender")
        self.recipient = self.make_player("recipient")

    def make_player(self, name):
        account_id = identity.register(f"{name}@example.com", PASSWORD).account_id
        assert profiles.save_profile(account_id, name.title(), "intermediate", "isb-f7").ok
        identity.verify_email(identity.get_verification_token(account_id))
        assert availability.add_slot(account_id, at(1, 8), at(1, 23)).ok
        return account_id

    def send(self, sender, start, end):
        result = invitations.send(
            sender_account_id=sender,
            recipient_account_id=self.recipient,
            starts_at=at(1, start),
            ends_at=at(1, end),
            venue=VENUE,
        )
        assert result.ok, result.errors
        return result.invitation_id


class TwoAcceptsOfOneInvitationTests(RaceCase):
    """Race 1 - the same invitation accepted twice at once."""

    def test_exactly_one_accept_wins(self):
        invitation_id = self.send(self.sender, 18, 20)

        results = run_together(
            lambda: invitations.accept(invitation_id, self.recipient),
            lambda: invitations.accept(invitation_id, self.recipient),
        )

        for result in results:
            self.assertNotIsInstance(result, Exception, f"a thread raised: {result!r}")
        won = [r for r in results if r.ok]
        lost = [r for r in results if not r.ok]

        self.assertEqual(len(won), 1, "both accepts succeeded")
        self.assertEqual(len(lost), 1)
        self.assertEqual(lost[0].error, invitations.NO_LONGER_PENDING)

    def test_only_one_game_and_one_pair_of_participants_exists(self):
        invitation_id = self.send(self.sender, 18, 20)

        run_together(
            lambda: invitations.accept(invitation_id, self.recipient),
            lambda: invitations.accept(invitation_id, self.recipient),
        )

        self.assertEqual(ConfirmedGame.objects.count(), 1)
        self.assertEqual(GameParticipant.objects.count(), 2)
        self.assertEqual(
            Invitation.objects.get(pk=invitation_id).status, InvitationStatus.ACCEPTED
        )

    def test_an_accept_racing_a_decline_leaves_one_answer(self):
        invitation_id = self.send(self.sender, 18, 20)

        results = run_together(
            lambda: invitations.accept(invitation_id, self.recipient),
            lambda: invitations.decline(invitation_id, self.recipient),
        )

        self.assertEqual(len([r for r in results if r.ok]), 1)
        status = Invitation.objects.get(pk=invitation_id).status
        self.assertIn(status, (InvitationStatus.ACCEPTED, InvitationStatus.DECLINED))
        # A declined invitation must not have produced a game.
        expected_games = 1 if status == InvitationStatus.ACCEPTED else 0
        self.assertEqual(ConfirmedGame.objects.count(), expected_games)


class TwoOverlappingInvitationsTests(RaceCase):
    """Race 2 - two overlapping invitations to one player, accepted at once."""

    def test_exactly_one_confirmed_game_is_created(self):
        first = self.send(self.sender, 18, 20)
        second = self.send(self.other_sender, 19, 21)

        results = run_together(
            lambda: invitations.accept(first, self.recipient),
            lambda: invitations.accept(second, self.recipient),
        )

        for result in results:
            self.assertNotIsInstance(result, Exception, f"a thread raised: {result!r}")
        won = [r for r in results if r.ok]
        lost = [r for r in results if not r.ok]

        self.assertEqual(len(won), 1, "both overlapping accepts succeeded")
        self.assertEqual(len(lost), 1)
        self.assertEqual(lost[0].error, invitations.OVERLAPPING_GAME)
        self.assertEqual(ConfirmedGame.objects.count(), 1)

    def test_the_loser_leaves_no_partial_rows(self):
        first = self.send(self.sender, 18, 20)
        second = self.send(self.other_sender, 19, 21)

        run_together(
            lambda: invitations.accept(first, self.recipient),
            lambda: invitations.accept(second, self.recipient),
        )

        self.assertEqual(GameParticipant.objects.count(), 2)
        pending = Invitation.objects.filter(status=InvitationStatus.PENDING).count()
        accepted = Invitation.objects.filter(status=InvitationStatus.ACCEPTED).count()
        self.assertEqual((accepted, pending), (1, 1))

    def test_zero_overlapping_confirmed_games_remain(self):
        """The property QA-03 actually states, asserted over the whole table."""
        first = self.send(self.sender, 18, 20)
        second = self.send(self.other_sender, 19, 21)

        run_together(
            lambda: invitations.accept(first, self.recipient),
            lambda: invitations.accept(second, self.recipient),
        )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*)
                FROM game_participant a
                JOIN game_participant b
                  ON a.account_id = b.account_id
                 AND a.id < b.id
                 AND a.cancelled_at IS NULL
                 AND b.cancelled_at IS NULL
                 AND a.starts_at < b.ends_at
                 AND a.ends_at   > b.starts_at
                """
            )
            (overlaps,) = cursor.fetchone()

        self.assertEqual(overlaps, 0)

    def test_back_to_back_accepts_both_win(self):
        """Nothing overlaps, so the race has no loser."""
        first = self.send(self.sender, 18, 20)
        second = self.send(self.other_sender, 20, 22)

        results = run_together(
            lambda: invitations.accept(first, self.recipient),
            lambda: invitations.accept(second, self.recipient),
        )

        self.assertEqual(len([r for r in results if r.ok]), 2, [r.error for r in results])
        self.assertEqual(ConfirmedGame.objects.count(), 2)


class CancelRacesAcceptTests(RaceCase):
    """AC4 - the sender withdraws at the moment the recipient answers."""

    def test_exactly_one_of_them_wins(self):
        invitation_id = self.send(self.sender, 18, 20)

        results = run_together(
            lambda: invitations.accept(invitation_id, self.recipient),
            lambda: invitations.cancel_invitation(invitation_id, self.sender),
        )

        for result in results:
            self.assertNotIsInstance(result, Exception, f"a thread raised: {result!r}")
        self.assertEqual(len([r for r in results if r.ok]), 1)
        self.assertEqual(
            [r.error for r in results if not r.ok], [invitations.NO_LONGER_PENDING]
        )

    def test_a_cancelled_invitation_never_leaves_a_game_behind(self):
        invitation_id = self.send(self.sender, 18, 20)

        run_together(
            lambda: invitations.accept(invitation_id, self.recipient),
            lambda: invitations.cancel_invitation(invitation_id, self.sender),
        )

        status = Invitation.objects.get(pk=invitation_id).status
        expected_games = 1 if status == InvitationStatus.ACCEPTED else 0
        self.assertEqual(ConfirmedGame.objects.count(), expected_games)
        self.assertEqual(GameParticipant.objects.count(), expected_games * 2)


class ExpiryRacesAcceptTests(RaceCase):
    """The sweep and an acceptance meeting on the same row (ASR-09)."""

    def test_the_two_never_disagree(self):
        invitation_id = self.send(self.sender, 18, 20)
        Invitation.objects.filter(pk=invitation_id).update(
            expires_at=clock.now() - _dt.timedelta(seconds=1)
        )

        results = run_together(
            lambda: invitations.accept(invitation_id, self.recipient),
            lambda: invitations.expire_pending(),
        )

        accept_result = results[0]
        self.assertNotIsInstance(accept_result, Exception, f"a thread raised: {accept_result!r}")
        # Whatever order they land in, the accept must lose: it is past the deadline.
        self.assertFalse(accept_result.ok)
        self.assertEqual(accept_result.error, invitations.HAS_EXPIRED)
        self.assertEqual(ConfirmedGame.objects.count(), 0)
        self.assertEqual(
            Invitation.objects.get(pk=invitation_id).status, InvitationStatus.EXPIRED
        )


class TwoPlayersCancelOneGameTests(RaceCase):
    """S11 AC2 - both participants may cancel, so they can race each other."""

    def setUp(self):
        super().setUp()
        self.invitation_id = self.send(self.sender, 18, 20)
        self.game_id = invitations.accept(self.invitation_id, self.recipient).game_id

    def test_exactly_one_cancellation_wins(self):
        results = run_together(
            lambda: invitations.cancel_game(self.game_id, self.sender),
            lambda: invitations.cancel_game(self.game_id, self.recipient),
        )

        for result in results:
            self.assertNotIsInstance(result, Exception, f"a thread raised: {result!r}")
        self.assertEqual(len([r for r in results if r.ok]), 1)
        self.assertEqual(
            [r.error for r in results if not r.ok], [invitations.ALREADY_CANCELLED]
        )

    def test_the_game_is_cancelled_once_and_both_rows_are_stamped(self):
        run_together(
            lambda: invitations.cancel_game(self.game_id, self.sender),
            lambda: invitations.cancel_game(self.game_id, self.recipient),
        )

        game = ConfirmedGame.objects.get(pk=self.game_id)
        self.assertTrue(game.is_cancelled)
        self.assertEqual(
            GameParticipant.objects.filter(game_id=self.game_id, cancelled_at__isnull=True).count(),
            0,
        )
        self.assertEqual(
            Invitation.objects.get(pk=self.invitation_id).status, InvitationStatus.ACCEPTED
        )


class CancelRacesAnAcceptOfTheFreedTimeTests(RaceCase):
    """The time a cancelled game frees, claimed at the same instant (G-10).

    Whichever order they land in, the result must be consistent: never a cancelled game
    plus an acceptance that was refused because of it, and never two live overlapping
    games.
    """

    def test_the_outcome_is_always_consistent(self):
        first = self.send(self.sender, 18, 20)
        game_id = invitations.accept(first, self.recipient).game_id
        second = self.send(self.other_sender, 19, 21)

        results = run_together(
            lambda: invitations.cancel_game(game_id, self.sender),
            lambda: invitations.accept(second, self.recipient),
        )

        for result in results:
            self.assertNotIsInstance(result, Exception, f"a thread raised: {result!r}")
        cancelled, accepted = results
        self.assertTrue(cancelled.ok, cancelled.error)
        if accepted.ok:
            # It ran after the cancellation committed: the freed time was taken.
            live = GameParticipant.objects.filter(
                account_id=self.recipient, cancelled_at__isnull=True
            )
            self.assertEqual(live.count(), 1)
        else:
            self.assertEqual(accepted.error, invitations.OVERLAPPING_GAME)

    def test_no_two_live_participations_ever_overlap(self):
        """The property QA-03 states, asserted over the table whatever the order."""
        first = self.send(self.sender, 18, 20)
        game_id = invitations.accept(first, self.recipient).game_id
        second = self.send(self.other_sender, 19, 21)

        run_together(
            lambda: invitations.cancel_game(game_id, self.sender),
            lambda: invitations.accept(second, self.recipient),
        )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*)
                FROM game_participant a
                JOIN game_participant b
                  ON a.account_id = b.account_id
                 AND a.id < b.id
                 AND a.cancelled_at IS NULL
                 AND b.cancelled_at IS NULL
                 AND a.starts_at < b.ends_at
                 AND a.ends_at   > b.starts_at
                """
            )
            (overlaps,) = cursor.fetchone()

        self.assertEqual(overlaps, 0)
