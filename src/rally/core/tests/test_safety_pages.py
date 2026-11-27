"""The S12 vertical slice end to end - plan.md S12 AC1, AC3, AC4."""
import datetime as _dt

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rally.core import clock
from rally.core.localtime import DATE_FORMAT, parse_local
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.invitations.api import facade as invitations
from rally.modules.notification.api import facade as notification
from rally.modules.profiles.api import facade as profiles
from rally.modules.safety.api import facade as safety

PASSWORD = "longenough"
ME = "me@example.com"
OTHER = "other@example.com"
VENUE = "Rally Courts, F-7"
AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
]


def local_date(day_offset: int) -> str:
    return (timezone.localtime(clock.now()) + _dt.timedelta(days=day_offset)).strftime(DATE_FORMAT)


class SafetyPageCase(TestCase):
    def setUp(self):
        previous = notification.set_email_adapter(notification.RecordingEmailAdapter())
        self.addCleanup(notification.set_email_adapter, previous)
        profiles.replace_areas(AREAS)
        self.me = self.make_player(ME, "My Name")
        self.other = self.make_player(OTHER, "Other Name")
        self.sign_in(ME)

    def make_player(self, email, name):
        account_id = identity.register(email, PASSWORD).account_id
        assert profiles.save_profile(account_id, name, "intermediate", "isb-f7").ok
        identity.verify_email(identity.get_verification_token(account_id))
        assert availability.add_slot(
            account_id,
            parse_local(local_date(1), "08:00"),
            parse_local(local_date(1), "23:00"),
        ).ok
        return account_id

    def sign_in(self, email):
        self.client.post(reverse("sign_out"))
        self.client.post(reverse("sign_in"), {"email": email, "password": PASSWORD})

    def block_url(self, account_id=None):
        return reverse("block_player", kwargs={"account_id": account_id or self.other})

    def report_url(self, account_id=None):
        return reverse("report_player", kwargs={"account_id": account_id or self.other})

    def profile_url(self, account_id=None):
        return reverse("player_profile", kwargs={"account_id": account_id or self.other})

    def search_results(self):
        return self.client.get(
            reverse("search"),
            {
                "date": local_date(1),
                "start": "18:00",
                "end": "20:00",
                "area_code": "isb-f7",
            },
        )

    def send_invitation(self):
        return invitations.send(
            sender_account_id=self.me,
            recipient_account_id=self.other,
            starts_at=parse_local(local_date(1), "18:00"),
            ends_at=parse_local(local_date(1), "20:00"),
            venue=VENUE,
        ).invitation_id


class WhereBlockingIsOfferedTests(SafetyPageCase):
    """AC1 - 'from a profile, result or invitation'."""

    def test_from_the_players_profile(self):
        self.assertContains(self.client.get(self.profile_url()), self.block_url())

    def test_from_a_search_result(self):
        response = self.search_results()

        self.assertContains(response, "Other Name")
        self.assertContains(response, self.block_url())

    def test_from_an_invitation(self):
        invitation_id = self.send_invitation()

        response = self.client.get(
            reverse("invitation_detail", kwargs={"invitation_id": invitation_id})
        )

        self.assertContains(response, self.block_url())

    def test_reporting_is_offered_in_the_same_three_places(self):
        """AC4 - 'from a profile or an invitation'; the result card carries it too."""
        invitation_id = self.send_invitation()

        self.assertContains(self.client.get(self.profile_url()), self.report_url())
        self.assertContains(self.search_results(), self.report_url())
        self.assertContains(
            self.client.get(reverse("invitation_detail", kwargs={"invitation_id": invitation_id})),
            self.report_url(),
        )

    def test_blocking_is_not_reachable_by_get(self):
        """FE-9 - it changes state and cancels invitations."""
        response = self.client.get(self.block_url())

        self.assertEqual(response.status_code, 405)
        self.assertFalse(safety.is_blocked_between(self.me, self.other))

    def test_blocking_a_player_who_does_not_exist_is_a_not_found(self):
        response = self.client.post(reverse("block_player", kwargs={"account_id": 999999}))

        self.assertEqual(response.status_code, 404)

    def test_blocking_yourself_is_a_not_found(self):
        response = self.client.post(reverse("block_player", kwargs={"account_id": self.me}))

        self.assertEqual(response.status_code, 404)


class BlockingThroughThePageTests(SafetyPageCase):
    """AC1."""

    def test_it_says_so_and_lands_on_the_blocked_list(self):
        response = self.client.post(self.block_url(), follow=True)

        self.assertContains(response, "You have blocked Other Name.")
        self.assertContains(response, "Players you have blocked")

    def test_the_pair_disappears_from_search_both_ways(self):
        self.client.post(self.block_url())

        # Asserted on the result card's own link, not on the name: the flash message
        # "You have blocked Other Name." is still on the next page and would match.
        self.assertNotContains(
            self.search_results(),
            reverse("invitation_new", kwargs={"account_id": self.other}),
        )

        self.sign_in(OTHER)
        self.assertNotContains(
            self.search_results(),
            reverse("invitation_new", kwargs={"account_id": self.me}),
        )

    def test_neither_can_send_an_invitation_afterwards(self):
        self.client.post(self.block_url())

        refused = self.client.post(
            reverse("invitation_new", kwargs={"account_id": self.other}),
            {
                "date": local_date(1),
                "start": "18:00",
                "end": "20:00",
                "venue": VENUE,
            },
        )

        self.assertEqual(refused.status_code, 400)
        self.assertContains(refused, invitations.BLOCKED, status_code=400)

    def test_the_cancelled_invitations_are_counted_in_the_message(self):
        """AC2 as a player experiences it."""
        self.send_invitation()

        response = self.client.post(self.block_url(), follow=True)

        self.assertContains(response, "1 pending invitation(s) between you were cancelled")
        self.assertContains(response, "Any confirmed game is unaffected")

    def test_blocking_twice_says_so_rather_than_failing_silently(self):
        self.client.post(self.block_url())

        response = self.client.post(self.block_url(), follow=True)

        self.assertContains(response, safety.ALREADY_BLOCKED)


class TheBlockedListTests(SafetyPageCase):
    """AC3."""

    def test_an_empty_list_explains_itself(self):
        """FE-6."""
        self.assertContains(self.client.get(reverse("blocked_players")), "not blocked anyone")

    def test_it_shows_who_you_blocked_and_offers_unblocking(self):
        self.client.post(self.block_url())

        response = self.client.get(reverse("blocked_players"))

        self.assertContains(response, "Other Name")
        self.assertContains(
            response, reverse("unblock_player", kwargs={"account_id": self.other})
        )

    def test_the_other_player_is_never_told_they_were_blocked(self):
        """PRD 12.5 - and the whole point of blocking."""
        self.client.post(self.block_url())
        self.sign_in(OTHER)

        response = self.client.get(reverse("blocked_players"))

        self.assertNotContains(response, "My Name")
        self.assertContains(response, "not blocked anyone")

    def test_unblocking_restores_visibility(self):
        self.client.post(self.block_url())

        response = self.client.post(
            reverse("unblock_player", kwargs={"account_id": self.other}), follow=True
        )

        self.assertContains(response, "Unblocked.")
        self.assertContains(self.search_results(), "Other Name")

    def test_unblocking_says_the_cancelled_invitations_stay_cancelled(self):
        """AC3 - said plainly, because a player would otherwise expect them back."""
        invitation_id = self.send_invitation()
        self.client.post(self.block_url())

        response = self.client.post(
            reverse("unblock_player", kwargs={"account_id": self.other}), follow=True
        )

        self.assertContains(response, "stay cancelled")
        self.assertEqual(
            invitations.get_for_participant(invitation_id, self.me).status, "cancelled"
        )

    def test_unblocking_is_not_reachable_by_get(self):
        """FE-9."""
        self.client.post(self.block_url())

        response = self.client.get(reverse("unblock_player", kwargs={"account_id": self.other}))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(safety.is_blocked_between(self.me, self.other))

    def test_you_cannot_unblock_somebody_elses_block(self):
        self.client.post(self.block_url())
        self.sign_in(OTHER)

        self.client.post(reverse("unblock_player", kwargs={"account_id": self.me}))

        self.assertTrue(safety.is_blocked_between(self.me, self.other))

    def test_the_page_needs_a_session_and_is_not_cached(self):
        """FE-3, FE-9."""
        self.assertIn("no-store", self.client.get(reverse("blocked_players"))["Cache-Control"])

        self.client.post(reverse("sign_out"))
        response = self.client.get(reverse("blocked_players"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("sign_in"), response["Location"])

    def test_no_contact_address_appears_on_it(self):
        """FE-2."""
        self.client.post(self.block_url())

        self.assertNotIn("@", self.client.get(reverse("blocked_players")).content.decode())


class ReportingThroughThePageTests(SafetyPageCase):
    """AC4."""

    def test_the_form_offers_exactly_the_categories_m6_accepts(self):
        response = self.client.get(self.report_url())

        for value, label in safety.REPORT_CATEGORIES:
            self.assertContains(response, f'value="{value}"')
            self.assertContains(response, label)

    def test_it_says_the_details_are_optional_and_the_player_is_not_told(self):
        response = self.client.get(self.report_url())

        self.assertContains(response, "Details (optional)")
        self.assertContains(response, "is not told that you reported them")

    def test_a_report_with_a_category_is_accepted(self):
        response = self.client.post(
            self.report_url(), {"category": "harassment"}, follow=True
        )

        self.assertContains(response, "Your report has been recorded")

    def test_a_report_with_details_is_accepted(self):
        response = self.client.post(
            self.report_url(),
            {"category": "other", "details": "They never turned up."},
            follow=True,
        )

        self.assertContains(response, "has been recorded")

    def test_a_report_without_a_category_is_refused_with_the_reason(self):
        response = self.client.post(self.report_url(), {"details": "Something happened."})

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, safety.CATEGORY_REQUIRED, status_code=400)

    def test_the_typed_details_survive_a_refusal(self):
        response = self.client.post(self.report_url(), {"details": "Kept text."})

        self.assertContains(response, "Kept text.", status_code=400)

    def test_reporting_from_an_invitation_keeps_the_invitation(self):
        invitation_id = self.send_invitation()

        form = self.client.get(self.report_url(), {"invitation_id": invitation_id})

        self.assertContains(form, f'name="invitation_id" value="{invitation_id}"')

    def test_reporting_does_not_block(self):
        self.client.post(self.report_url(), {"category": "harassment"})

        self.assertFalse(safety.is_blocked_between(self.me, self.other))
        self.assertContains(self.search_results(), "Other Name")

    def test_the_reported_player_is_not_notified(self):
        before = len(notification.list_for_player(self.other))

        self.client.post(self.report_url(), {"category": "harassment"})

        self.assertEqual(len(notification.list_for_player(self.other)), before)

    def test_the_reporter_is_offered_no_way_to_read_it_back(self):
        """AC4 - 'reporters cannot read reports'. There is no route to one."""
        self.client.post(self.report_url(), {"category": "harassment"})

        from rally.core.web import urls

        names = [
            pattern.name
            for pattern in urls.urlpatterns
            if pattern.name and "report" in pattern.name
        ]

        self.assertEqual(names, ["report_player"])

    def test_reporting_yourself_is_a_not_found(self):
        response = self.client.get(reverse("report_player", kwargs={"account_id": self.me}))

        self.assertEqual(response.status_code, 404)

    def test_the_form_needs_a_session(self):
        """FE-3."""
        self.client.post(reverse("sign_out"))

        response = self.client.get(self.report_url())

        self.assertEqual(response.status_code, 302)

    def test_no_contact_address_appears_on_the_form(self):
        """FE-2."""
        self.assertNotIn("@", self.client.get(self.report_url()).content.decode())
