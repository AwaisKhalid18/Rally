"""M5's send rules - plan.md S7 AC2, AC3, AC6."""
import datetime as _dt

from django.test import TestCase

from rally.core import clock
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.invitations.api import facade as invitations
from rally.modules.invitations.internal.models import Invitation, InvitationStatus
from rally.modules.profiles.api import facade as profiles
from rally.modules.safety.api import facade as safety

PASSWORD = "longenough"
AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
]
VENUE = "Rally Courts, F-7"


def at(day_offset: int, hour: int) -> _dt.datetime:
    midnight = clock.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + _dt.timedelta(days=day_offset, hours=hour)


class SendCase(TestCase):
    def setUp(self):
        profiles.replace_areas(AREAS)
        self.sender = self.make_player("sender", verified=True)
        self.recipient = self.make_player("recipient", verified=True, slot=(1, 17, 21))

    def make_player(self, name, verified=True, slot=None):
        account_id = identity.register(f"{name}@example.com", PASSWORD).account_id
        saved = profiles.save_profile(account_id, name.title(), "intermediate", "isb-f7")
        assert saved.ok, saved.errors
        if verified:
            identity.verify_email(identity.get_verification_token(account_id))
        if slot:
            day, start, end = slot
            assert availability.add_slot(account_id, at(day, start), at(day, end)).ok
        return account_id

    def send(self, **overrides):
        payload = {
            "sender_account_id": self.sender,
            "recipient_account_id": self.recipient,
            "starts_at": at(1, 18),
            "ends_at": at(1, 20),
            "venue": VENUE,
        }
        payload.update(overrides)
        return invitations.send(**payload)


class SuccessfulSendTests(SendCase):
    def test_an_invitation_is_created_pending(self):
        result = self.send()

        self.assertTrue(result.ok, result.errors)
        row = Invitation.objects.get(pk=result.invitation_id)
        self.assertEqual(row.status, InvitationStatus.PENDING)
        self.assertEqual(row.sender_account_id, self.sender)
        self.assertEqual(row.recipient_account_id, self.recipient)
        self.assertEqual(row.venue, VENUE)

    def test_it_expires_at_the_proposed_start_when_that_comes_first(self):
        """AC3 - min(created + 24h, start). A game two hours away expires at kick-off."""
        soon = clock.now().replace(minute=0, second=0, microsecond=0) + _dt.timedelta(hours=2)
        soon_end = soon + _dt.timedelta(hours=2)
        near = self.make_player("near", verified=True)
        self.assertTrue(availability.add_slot(near, soon, soon_end).ok)

        result = self.send(recipient_account_id=near, starts_at=soon, ends_at=soon_end)

        self.assertTrue(result.ok, result.errors)
        self.assertEqual(Invitation.objects.get(pk=result.invitation_id).expires_at, soon)

    def test_it_expires_after_twenty_four_hours_when_the_game_is_further_off(self):
        far = self.make_player("far", verified=True, slot=(5, 17, 21))

        before = clock.now()
        result = self.send(recipient_account_id=far, starts_at=at(5, 18), ends_at=at(5, 20))
        after = clock.now()

        self.assertTrue(result.ok, result.errors)
        row = Invitation.objects.get(pk=result.invitation_id)
        self.assertGreaterEqual(row.expires_at, before + invitations.EXPIRY_WINDOW)
        self.assertLessEqual(row.expires_at, after + invitations.EXPIRY_WINDOW)

    def test_the_venue_is_trimmed(self):
        result = self.send(venue="  Rally Courts  ")
        self.assertEqual(Invitation.objects.get(pk=result.invitation_id).venue, "Rally Courts")

    def test_a_refused_send_creates_no_invitation(self):
        # M5 must not import M7, not even in a test (rule 2), so what reaches the
        # outbox is asserted where Platform drives the worker:
        # rally/core/tests/test_invitation_flow.py.
        self.send(venue="")

        self.assertEqual(Invitation.objects.count(), 0)

    def test_two_invitations_for_different_times_are_both_allowed(self):
        self.assertTrue(self.send().ok)
        self.assertTrue(self.send(starts_at=at(1, 20), ends_at=at(1, 21)).ok)
        self.assertEqual(Invitation.objects.count(), 2)


class RefusedSendTests(SendCase):
    """AC2 - each refusal says exactly what is wrong."""

    def test_an_unverified_sender_cannot_send(self):
        unverified = self.make_player("unverified", verified=False)

        result = self.send(sender_account_id=unverified)

        self.assertEqual(result.errors, {"form": invitations.SENDER_UNVERIFIED})
        self.assertEqual(Invitation.objects.count(), 0)

    def test_a_player_cannot_invite_themselves(self):
        result = self.send(recipient_account_id=self.sender)
        self.assertEqual(result.errors, {"form": invitations.RECIPIENT_IS_SELF})

    def test_an_unknown_recipient_is_refused(self):
        self.assertEqual(
            self.send(recipient_account_id=999_999).errors,
            {"form": invitations.RECIPIENT_UNKNOWN},
        )

    def test_a_block_by_the_sender_refuses_the_send(self):
        safety.block(self.sender, self.recipient)
        self.assertEqual(self.send().errors, {"form": invitations.BLOCKED})

    def test_a_block_by_the_recipient_refuses_the_send(self):
        """ASR-10 - the rule applies in both directions."""
        safety.block(self.recipient, self.sender)
        self.assertEqual(self.send().errors, {"form": invitations.BLOCKED})

    def test_an_end_before_the_start_is_refused(self):
        self.assertEqual(
            self.send(starts_at=at(1, 20), ends_at=at(1, 18)).errors,
            {"end": invitations.END_BEFORE_START},
        )

    def test_a_start_in_the_past_is_refused(self):
        self.assertEqual(
            self.send(starts_at=at(-1, 18), ends_at=at(-1, 20)).errors,
            {"date": invitations.START_IN_PAST},
        )

    def test_a_recipient_without_covering_availability_is_refused(self):
        bare = self.make_player("bare", verified=True, slot=None)

        self.assertEqual(
            self.send(recipient_account_id=bare).errors,
            {"form": invitations.RECIPIENT_UNAVAILABLE},
        )

    def test_a_time_spilling_outside_the_recipients_slot_is_refused(self):
        """Their slot is 17:00-21:00, so 20:00-22:00 is not fully covered."""
        self.assertEqual(
            self.send(starts_at=at(1, 20), ends_at=at(1, 22)).errors,
            {"form": invitations.RECIPIENT_UNAVAILABLE},
        )

    def test_a_second_overlapping_pending_invitation_is_refused(self):
        self.assertTrue(self.send().ok)

        result = self.send(starts_at=at(1, 19), ends_at=at(1, 21))

        self.assertEqual(result.errors, {"form": invitations.DUPLICATE_PENDING})
        self.assertEqual(Invitation.objects.count(), 1)

    def test_a_back_to_back_pending_invitation_is_allowed(self):
        self.assertTrue(self.send(starts_at=at(1, 18), ends_at=at(1, 19)).ok)
        self.assertTrue(self.send(starts_at=at(1, 19), ends_at=at(1, 20)).ok)

    def test_another_sender_may_invite_the_same_player_for_the_same_time(self):
        """The duplicate rule is per sender-recipient pair (PRD 12.3)."""
        other_sender = self.make_player("other", verified=True)
        self.assertTrue(self.send().ok)

        self.assertTrue(self.send(sender_account_id=other_sender).ok)


class VenueBoundaryTests(SendCase):
    """G-12 proposes 2 to 100 characters, so 1 / 2 and 100 / 101 are what matter."""

    def test_a_missing_venue_is_refused(self):
        self.assertEqual(self.send(venue="   ").errors, {"venue": invitations.VENUE_REQUIRED})

    def test_one_character_is_refused(self):
        self.assertEqual(self.send(venue="x").errors, {"venue": invitations.VENUE_TOO_SHORT})

    def test_two_characters_is_accepted(self):
        self.assertTrue(self.send(venue="xy").ok)

    def test_one_hundred_characters_is_accepted(self):
        self.assertTrue(self.send(venue="x" * 100).ok)

    def test_one_hundred_and_one_characters_is_refused(self):
        self.assertEqual(
            self.send(venue="x" * 101).errors, {"venue": invitations.VENUE_TOO_LONG}
        )


class ListingTests(SendCase):
    """AC5 - a participant sees their own invitations and nobody else's."""

    def setUp(self):
        super().setUp()
        self.invitation_id = self.send().invitation_id

    def test_the_sender_sees_it_as_sent(self):
        sent, received = invitations.list_for_player(self.sender)

        self.assertEqual([r.invitation_id for r in sent], [self.invitation_id])
        self.assertEqual(received, [])

    def test_the_recipient_sees_it_as_received(self):
        sent, received = invitations.list_for_player(self.recipient)

        self.assertEqual(sent, [])
        self.assertEqual([r.invitation_id for r in received], [self.invitation_id])

    def test_a_stranger_sees_nothing(self):
        stranger = self.make_player("stranger", verified=True)

        self.assertEqual(invitations.list_for_player(stranger), ([], []))

    def test_a_participant_can_read_it(self):
        for viewer in (self.sender, self.recipient):
            with self.subTest(viewer=viewer):
                record = invitations.get_for_participant(self.invitation_id, viewer)
                self.assertIsNotNone(record)
                self.assertEqual(record.status, "pending")

    def test_a_non_participant_cannot(self):
        stranger = self.make_player("stranger", verified=True)

        self.assertIsNone(invitations.get_for_participant(self.invitation_id, stranger))

    def test_an_invitation_that_does_not_exist_reads_as_absent(self):
        self.assertIsNone(invitations.get_for_participant(999_999, self.sender))

    def test_the_record_carries_no_contact_data(self):
        record = invitations.get_for_participant(self.invitation_id, self.sender)

        blob = " ".join(str(value) for value in vars(record).values())
        self.assertNotIn("@", blob)

    def test_the_record_knows_which_side_the_viewer_was_on(self):
        record = invitations.get_for_participant(self.invitation_id, self.sender)

        self.assertTrue(record.was_sent_by(self.sender))
        self.assertFalse(record.was_sent_by(self.recipient))
        self.assertEqual(record.other_party(self.sender), self.recipient)
        self.assertEqual(record.other_party(self.recipient), self.sender)
