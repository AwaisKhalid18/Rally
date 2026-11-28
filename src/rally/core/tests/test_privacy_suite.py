"""The privacy suite - plan.md S16 AC2, NFR-03, QA-02, ASR-04, ASR-05.

NFR-03 asks that 100% of the defined privacy tests prevent unauthorised access to exact
location and personal contact information. PRD §12.6 and AGENTS.md §10 name the seven
cases: **unauthenticated, other player, search, profile, invitation, notification, and
a direct server request**. This file runs all seven against the finished system.

It is written to go stale loudly rather than quietly: the sweeps walk the URL conf, so
a route added later is covered without anybody remembering to add it here. A new route
that needs an argument this file does not know will fail the sweep until it is named.

Two players exist throughout, with every kind of record between them - profile,
availability, invitation, confirmed game, notification, favorite, saved search, block
and report - so the sweeps have something real to leak.
"""
import datetime as _dt

from django.test import TestCase
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch

from rally.core import clock
from rally.core.localtime import DATE_FORMAT, parse_local, to_local
from rally.core.pipeline.middleware import PUBLIC_URL_NAMES
from rally.core.web import urls as web_urls
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.invitations.api import facade as invitations
from rally.modules.notification.api import facade as notification
from rally.modules.player_collections.api import facade as collections
from rally.modules.profiles.api import facade as profiles
from rally.modules.safety.api import facade as safety

PASSWORD = "longenough"
MINE = "mine@example.com"
THEIRS = "theirs@example.com"
MY_PHONE = "03001234567"
THEIR_PHONE = "03007654321"
VENUE = "Rally Courts, F-7"

AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
    {"code": "isb-g9", "name": "Islamabad G-9", "centroid_lat": "33.6889", "centroid_lon": "73.0369"},
]

# Everything that must never reach another player, or any page at all (rules 6, 7).
CONTACT_DATA = (MINE, THEIRS, MY_PHONE, THEIR_PHONE, "@example.com")
COORDINATES = ("33.7211", "73.0551", "33.6889", "73.0369")


def local_date(day_offset: int) -> str:
    return (to_local(clock.now()) + _dt.timedelta(days=day_offset)).strftime(DATE_FORMAT)


class PrivacyCase(TestCase):
    """One fully populated pair of players."""

    @classmethod
    def setUpTestData(cls):
        profiles.replace_areas(AREAS)
        cls.me = cls.make_player(MINE, "My Name", MY_PHONE, "isb-f7")
        cls.them = cls.make_player(THEIRS, "Their Name", THEIR_PHONE, "isb-g9")
        cls.third = cls.make_player("third@example.com", "Third Name", "", "isb-f7")

        # An invitation they sent me, accepted, so a confirmed game exists too.
        sent = invitations.send(
            sender_account_id=cls.them,
            recipient_account_id=cls.me,
            starts_at=parse_local(local_date(1), "18:00"),
            ends_at=parse_local(local_date(1), "20:00"),
            venue=VENUE,
        )
        assert sent.ok, sent.errors
        cls.invitation = sent.invitation_id
        accepted = invitations.accept(cls.invitation, cls.me)
        assert accepted.ok, accepted.error
        cls.game = accepted.game_id

        # An invitation between the two players I am NOT, so "other player" has
        # records of their own to protect.
        # Later the same day: a pending invitation reserves nothing, so this is
        # unaffected by the confirmed game above (PRD §12.4).
        theirs = invitations.send(
            sender_account_id=cls.them,
            recipient_account_id=cls.third,
            starts_at=parse_local(local_date(1), "20:00"),
            ends_at=parse_local(local_date(1), "22:00"),
            venue=VENUE,
        )
        assert theirs.ok, theirs.errors
        cls.their_invitation = theirs.invitation_id

        collections.add_favorite(cls.them, cls.third)
        cls.their_search = collections.save_search(
            cls.them,
            name="Theirs",
            start_time=_dt.time(9, 0),
            end_time=_dt.time(11, 0),
            area_code="isb-f7",
            day_rule="tomorrow",
        ).saved_search_id
        safety.report(cls.them, cls.third, "harassment", "Private words about a player.")

        # A conversation, so the chat screens are swept with something real in them.
        from rally.modules.messaging.api import facade as messaging

        opened = messaging.open_conversation(cls.me, cls.them)
        assert opened.ok, opened.error
        cls.conversation = opened.conversation_id
        posted = messaging.post_message(cls.conversation, cls.them, "See you at six")
        assert posted.ok, posted.error

        cls.their_conversation = None  # they have no other thread; nothing to leak

        cls.my_favorite = collections.add_favorite(cls.me, cls.them)
        cls.my_search = collections.save_search(
            cls.me,
            name="Mine",
            start_time=_dt.time(9, 0),
            end_time=_dt.time(11, 0),
            area_code="isb-f7",
            day_rule="tomorrow",
        ).saved_search_id

    @classmethod
    def make_player(cls, email, name, phone, area):
        account_id = identity.register(email, PASSWORD).account_id
        assert profiles.save_profile(account_id, name, "intermediate", area).ok
        if phone:
            identity.set_phone(account_id, phone)
        identity.verify_email(identity.get_verification_token(account_id))
        assert availability.add_slot(
            account_id,
            parse_local(local_date(1), "08:00"),
            parse_local(local_date(1), "23:00"),
        ).ok
        return account_id

    def sign_in(self, email):
        self.client.post(reverse("sign_out"))
        response = self.client.post(
            reverse("sign_in"), {"email": email, "password": PASSWORD}
        )
        assert response.status_code == 302, "the fixture could not sign in"

    # --- the route sweep -----------------------------------------------------

    def arguments_for(self, name):
        """Real ids, so each page renders with real data rather than 404ing."""
        return {
            "verify_email": {"token": "no-such-token"},
            "player_profile": {"account_id": self.them},
            "availability_edit": {"slot_id": 1},
            "availability_delete": {"slot_id": 1},
            "invitation_new": {"account_id": self.them},
            "invitation_detail": {"invitation_id": self.invitation},
            "invitation_accept": {"invitation_id": self.invitation},
            "invitation_decline": {"invitation_id": self.invitation},
            "invitation_cancel": {"invitation_id": self.invitation},
            "game_cancel": {"game_id": self.game},
            "notification_read": {"notification_id": 1},
            "block_player": {"account_id": self.them},
            "unblock_player": {"account_id": self.them},
            "report_player": {"account_id": self.them},
            "favorite_add": {"account_id": self.third},
            "favorite_remove": {"account_id": self.them},
            "saved_search_edit": {"saved_search_id": self.my_search},
            "saved_search_run": {"saved_search_id": self.my_search},
            "saved_search_delete": {"saved_search_id": self.my_search},
            "conversation": {"conversation_id": self.conversation},
            "conversation_open": {"account_id": self.them},
        }.get(name, {})

    def every_route(self):
        for pattern in web_urls.urlpatterns:
            if pattern.name:
                yield pattern.name

    def url_for(self, name):
        return reverse(name, kwargs=self.arguments_for(name))


class UnauthenticatedAccessTests(PrivacyCase):
    """Case 1 - unauthenticated. ASR-05, FE-3."""

    def test_only_the_three_public_routes_answer_without_a_session(self):
        for name in self.every_route():
            with self.subTest(route=name):
                response = self.client.get(self.url_for(name))

                if name in PUBLIC_URL_NAMES:
                    self.assertIn(
                        response.status_code, (200, 404),
                        f"{name} is public and should answer",
                    )
                else:
                    self.assertEqual(
                        response.status_code, 302,
                        f"{name} answered without a session",
                    )
                    self.assertIn(reverse("sign_in"), response["Location"])

    def test_no_anonymous_page_carries_contact_data_or_a_coordinate(self):
        for name in PUBLIC_URL_NAMES:
            with self.subTest(route=name):
                body = self.client.get(self.url_for(name)).content.decode()

                for secret in CONTACT_DATA + COORDINATES:
                    self.assertNotIn(secret, body)

    def test_posting_to_a_state_changing_route_without_a_session_changes_nothing(self):
        before = invitations.get_for_participant(self.invitation, self.me).status

        for name in ("invitation_cancel", "block_player", "favorite_add", "game_cancel"):
            with self.subTest(route=name):
                response = self.client.post(self.url_for(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("sign_in"), response["Location"])

        self.assertEqual(
            invitations.get_for_participant(self.invitation, self.me).status, before
        )

    def test_the_three_public_routes_are_exactly_the_allowlist(self):
        """AGENTS §5: adding a fourth needs an ADR."""
        self.assertEqual(PUBLIC_URL_NAMES, frozenset({"register", "sign_in", "verify_email"}))


class EveryAuthenticatedPageTests(PrivacyCase):
    """Cases 3, 4, 5, 6 - search, profile, invitation, notification, and every other
    screen, swept together. QA-02: no page, anywhere, carries contact data."""

    def setUp(self):
        self.sign_in(MINE)

    def rendered_pages(self):
        """Every GET-able route, rendered for a signed-in player with real data."""
        for name in self.every_route():
            if name in PUBLIC_URL_NAMES:
                continue
            try:
                url = self.url_for(name)
            except NoReverseMatch:  # pragma: no cover - a route this file forgot
                self.fail(f"{name} needs arguments; add them to arguments_for()")
            response = self.client.get(url)
            if response.status_code == 200:
                yield name, response.content.decode()

    def test_no_page_contains_an_email_address_or_a_phone_number(self):
        """NFR-03, rule 6. Including my own: the pages never echo it back."""
        seen = 0
        for name, body in self.rendered_pages():
            seen += 1
            with self.subTest(page=name):
                for secret in CONTACT_DATA:
                    self.assertNotIn(secret, body, f"{name} leaked {secret!r}")
        self.assertGreater(seen, 10, "the sweep rendered almost nothing - check it")

    def test_no_page_contains_a_coordinate(self):
        """NFR-03, rule 7, ASR-03: distance is derived, never the point itself."""
        for name, body in self.rendered_pages():
            with self.subTest(page=name):
                for coordinate in COORDINATES:
                    self.assertNotIn(coordinate, body, f"{name} leaked {coordinate!r}")

    def test_the_search_results_carry_no_contact_data(self):
        """Case 3 - search."""
        body = self.client.get(
            reverse("search"),
            {"date": local_date(1), "start": "18:00", "end": "20:00", "area_code": "isb-f7"},
        ).content.decode()

        self.assertIn("Their Name", body, "precondition: the other player was found")
        for secret in CONTACT_DATA + COORDINATES:
            self.assertNotIn(secret, body)

    def test_a_profile_carries_no_contact_data(self):
        """Case 4 - profile."""
        body = self.client.get(
            reverse("player_profile", kwargs={"account_id": self.them})
        ).content.decode()

        self.assertIn("Their Name", body)
        for secret in CONTACT_DATA + COORDINATES:
            self.assertNotIn(secret, body)

    def test_an_invitation_carries_no_contact_data_even_after_acceptance(self):
        """Case 5 - invitation. PRD §12.2: nothing becomes visible after acceptance."""
        body = self.client.get(
            reverse("invitation_detail", kwargs={"invitation_id": self.invitation})
        ).content.decode()

        self.assertIn("Accepted", body, "precondition: it was accepted")
        for secret in CONTACT_DATA:
            self.assertNotIn(secret, body)

    def test_a_confirmed_game_carries_no_contact_data(self):
        body = self.client.get(reverse("games")).content.decode()

        self.assertIn("Their Name", body)
        for secret in CONTACT_DATA:
            self.assertNotIn(secret, body)

    def test_notifications_carry_no_contact_data(self):
        """Case 6 - notification."""
        body = self.client.get(reverse("notifications")).content.decode()

        for secret in CONTACT_DATA:
            self.assertNotIn(secret, body)

    def test_the_compare_screen_carries_no_contact_data(self):
        body = self.client.get(
            reverse("compare"), {"player": [str(self.them), str(self.third)]}
        ).content.decode()

        self.assertIn("Their Name", body)
        for secret in CONTACT_DATA + COORDINATES:
            self.assertNotIn(secret, body)


class OtherPlayersDataTests(PrivacyCase):
    """Case 2 - other player. ASR-05: you reach only your own records."""

    def setUp(self):
        self.sign_in(MINE)

    def test_another_players_invitation_is_a_not_found(self):
        response = self.client.get(
            reverse("invitation_detail", kwargs={"invitation_id": self.their_invitation})
        )

        self.assertEqual(response.status_code, 404)

    def test_another_players_saved_search_is_a_not_found(self):
        for name in ("saved_search_edit", "saved_search_run"):
            with self.subTest(route=name):
                response = self.client.get(
                    reverse(name, kwargs={"saved_search_id": self.their_search})
                )
                self.assertEqual(response.status_code, 404)

    def test_another_players_favorites_are_not_on_my_list(self):
        body = self.client.get(reverse("favorites")).content.decode()

        self.assertIn("Their Name", body, "my own favorite is there")
        self.assertNotIn("Third Name", body, "their favorite leaked onto my list")

    def test_another_players_saved_searches_are_not_on_my_list(self):
        body = self.client.get(reverse("saved_searches")).content.decode()

        self.assertIn("Mine", body)
        self.assertNotIn("Theirs", body)

    def test_another_players_notifications_are_not_in_my_inbox(self):
        mine = {item.notification_id for item in notification.list_for_player(self.me)}
        theirs = {item.notification_id for item in notification.list_for_player(self.them)}

        self.assertTrue(theirs, "precondition: they have notifications")
        self.assertEqual(mine & theirs, set())

    def test_i_cannot_mark_another_players_notification_read(self):
        theirs = notification.list_for_player(self.them)[0]

        self.client.post(
            reverse("notification_read", kwargs={"notification_id": theirs.notification_id})
        )

        self.assertFalse(notification.list_for_player(self.them)[0].is_read)

    def test_a_report_can_never_be_read_back(self):
        """PRD §12.5: stored for the administrators, not readable by any player."""
        report_routes = [
            name for name in self.every_route() if "report" in name
        ]

        self.assertEqual(report_routes, ["report_player"])
        self.assertEqual(self.client.get(self.url_for("report_player")).status_code, 200)

    def test_i_am_never_told_who_blocked_me(self):
        safety.block(self.them, self.me)
        self.addCleanup(safety.unblock, self.them, self.me)

        body = self.client.get(reverse("blocked_players")).content.decode()

        self.assertNotIn("Their Name", body)
        self.assertIn("not blocked anyone", body)


class DirectServerRequestTests(PrivacyCase):
    """Case 7 - a direct request, bypassing the pages entirely."""

    def setUp(self):
        self.sign_in(MINE)

    def test_acting_on_another_players_invitation_changes_nothing(self):
        for name in ("invitation_accept", "invitation_decline", "invitation_cancel"):
            with self.subTest(route=name):
                self.client.post(
                    reverse(name, kwargs={"invitation_id": self.their_invitation})
                )

        self.assertEqual(
            invitations.get_for_participant(self.their_invitation, self.them).status,
            "pending",
        )

    def test_deleting_another_players_saved_search_changes_nothing(self):
        self.client.post(
            reverse("saved_search_delete", kwargs={"saved_search_id": self.their_search})
        )

        self.assertIsNotNone(collections.get_search(self.their_search, self.them))

    def test_removing_another_players_favorite_changes_nothing(self):
        before = len(collections.list_favorites(self.them))

        self.client.post(reverse("favorite_remove", kwargs={"account_id": self.third}))

        self.assertEqual(len(collections.list_favorites(self.them)), before)

    def test_guessing_an_id_that_does_not_exist_tells_me_nothing(self):
        """A missing record and somebody else's give the same answer (ASR-05)."""
        missing = self.client.get(
            reverse("invitation_detail", kwargs={"invitation_id": 999999})
        )
        theirs = self.client.get(
            reverse("invitation_detail", kwargs={"invitation_id": self.their_invitation})
        )

        self.assertEqual(missing.status_code, theirs.status_code)

    def test_a_state_change_without_a_csrf_token_is_refused(self):
        from django.test import Client

        strict = Client(enforce_csrf_checks=True)
        strict.post(reverse("sign_in"), {"email": MINE, "password": PASSWORD})

        response = strict.post(reverse("block_player", kwargs={"account_id": self.them}))

        self.assertEqual(response.status_code, 403)
        self.assertFalse(safety.is_blocked_between(self.me, self.them))

    def test_every_authenticated_page_forbids_caching(self):
        """FE-9: nothing a signed-in player sees may be stored by a proxy."""
        for name in self.every_route():
            if name in PUBLIC_URL_NAMES:
                continue
            response = self.client.get(self.url_for(name))
            if response.status_code == 200:
                with self.subTest(page=name):
                    self.assertIn("no-store", response.get("Cache-Control", ""))


class TheLogsTests(PrivacyCase):
    """Rule 6: email and phone appear in no log, on any path."""

    def setUp(self):
        self.sign_in(MINE)

    def test_exercising_the_system_writes_no_address_to_the_log(self):
        with self.assertLogs("rally.operation", level="INFO") as captured:
            self.client.get(
                reverse("search"),
                {"date": local_date(1), "start": "18:00", "end": "20:00", "area_code": "isb-f7"},
            )
            self.client.get(reverse("compare"), {"player": str(self.them)})
            self.client.post(reverse("favorite_add", kwargs={"account_id": self.third}))
            self.client.post(reverse("block_player", kwargs={"account_id": self.third}))
            self.client.post(reverse("report_player", kwargs={"account_id": self.them}),
                             {"category": "harassment", "details": "Private words."})
            self.client.get(
                reverse("saved_search_run", kwargs={"saved_search_id": self.my_search})
            )
            notification.dispatch_due()

        written = "\n".join(captured.output)

        self.assertIn("operation=", written, "precondition: something was logged")
        for secret in CONTACT_DATA + COORDINATES:
            self.assertNotIn(secret, written, f"the log leaked {secret!r}")
        self.assertNotIn("Private words.", written, "a report's free text reached the log")
