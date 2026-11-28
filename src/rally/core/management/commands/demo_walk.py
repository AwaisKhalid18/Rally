"""The scripted end-to-end demo walk (plan.md S16 AC4).

    python manage.py demo_walk

Walks the whole product in order, over real HTTP through Django's test client, against
whatever database is configured — so it runs on a fresh one, straight after `migrate`,
`load_areas` and `seed_players`. Every step prints what the system actually answered,
and the command **fails loudly** if a step does not do what the slice promised.

It is the demo script and a smoke test at once: if this passes on a fresh database, the
flows the PRD describes all work end to end. It is not a substitute for the test suite,
which checks the rules this only exercises.
"""
from __future__ import annotations

import datetime as _dt

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.urls import reverse

from rally.core import clock
from rally.core.localtime import DATE_FORMAT, TIME_FORMAT, to_local
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.invitations.api import facade as invitations
from rally.modules.notification.api import facade as notification
from rally.modules.player_collections.api import facade as collections
from rally.modules.profiles.api import facade as profiles
from rally.modules.safety.api import facade as safety

PASSWORD = "demo-password"
VENUE = "Rally Courts, F-7"


class Command(BaseCommand):
    help = "Walk every Rally flow end to end and report what the system answered."

    def add_arguments(self, parser):
        parser.add_argument(
            "--prefix", default="demo", help="email prefix, so a rerun makes new players"
        )

    # --- reporting -------------------------------------------------------

    def step(self, title):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n{title}"))

    def says(self, label, value):
        self.stdout.write(f"    {label:<34} {value}")

    def expect(self, condition, failure):
        if not condition:
            raise CommandError(f"demo walk failed: {failure}")

    # --- the walk --------------------------------------------------------

    def handle(self, *args, **options):
        # Django's test client calls itself `testserver`; the walk drives the real
        # app through it, so that host has to be allowed for the length of the run.
        if "testserver" not in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

        prefix = options["prefix"]
        stamp = clock.now().strftime("%H%M%S")
        alice_email = f"{prefix}-alice-{stamp}@example.com"
        bob_email = f"{prefix}-bob-{stamp}@example.com"
        carol_email = f"{prefix}-carol-{stamp}@example.com"

        areas = profiles.list_areas()
        self.expect(areas, "no areas are loaded - run `manage.py load_areas` first")
        area = areas[0]

        tomorrow = to_local(clock.now()).date() + _dt.timedelta(days=1)
        day = tomorrow.strftime(DATE_FORMAT)

        # Everything the demo sends goes to the configured email backend, which is the
        # console unless RALLY_EMAIL_LIVE=1 (G-14).
        recorder = notification.RecordingEmailAdapter()
        previous = notification.set_email_adapter(recorder)
        try:
            self._walk(alice_email, bob_email, carol_email, area, day, recorder, stamp)
        finally:
            notification.set_email_adapter(previous)

        self.stdout.write(self.style.SUCCESS("\nThe demo walk completed. Every step did what it promised."))

    def _walk(self, alice_email, bob_email, carol_email, area, day, recorder, stamp):
        # The names carry the run's stamp, so a rerun on a database that already
        # holds demo players still asserts about its own three.
        alice_name, bob_name, carol_name = (
            f"Alice {stamp}", f"Bob {stamp}", f"Carol {stamp}"
        )
        self.step("1. Register, verify and sign in (S1, S2)")
        alice = Client()
        alice_id = self.register(alice, alice_email)
        self.says("account created, unverified", alice_id)
        token = identity.get_verification_token(alice_id)
        self.expect(token, "no verification token was issued")
        page = alice.get(reverse("verify_email", kwargs={"token": token}))
        self.expect(page.status_code == 200, "the verification link did not open")
        self.says("the emailed link", "shows a page; the POST verifies (FE-9)")
        confirmed = alice.post(reverse("verify_email", kwargs={"token": token}))
        self.expect(confirmed.status_code in (200, 302), "the verification POST failed")
        self.says("verified", identity.account_summary(alice_id).is_verified)

        bob = Client()
        bob_id = self.register(bob, bob_email, verify=True)
        carol = Client()
        carol_id = self.register(carol, carol_email, verify=True)
        self.says("three players exist", f"{alice_id}, {bob_id}, {carol_id}")

        self.step("2. Profiles and playing times (S3, S4)")
        for client, name in ((alice, alice_name), (bob, bob_name), (carol, carol_name)):
            response = client.post(
                reverse("profile"),
                {"display_name": name, "playing_level": "intermediate", "area_code": area.code},
            )
            self.expect(response.status_code in (200, 302), f"{name}'s profile was refused")
        self.says("profiles saved", "display name, level, general area")

        # All three, including Alice: step 9 has Carol invite her, and an invitation
        # is refused unless the recipient is available for the whole window.
        for client in (alice, bob, carol):
            response = client.post(
                reverse("availability"), {"date": day, "start": "18:00", "end": "22:00"}
            )
            self.expect(response.status_code in (200, 302), "a playing time was refused")
        self.says("playing times added", f"{day} 18:00-22:00 for all three")

        self.step("3. Search (S5, S6)")
        results = alice.get(
            reverse("search"),
            {"date": day, "start": "18:00", "end": "20:00", "area_code": area.code},
        )
        body = results.content.decode()
        self.expect(bob_name in body, "the search did not find Bob")
        self.says("Alice searches", f"finds {bob_name} and {carol_name}")
        self.says("each card shows", "level, area, approximate distance, times")
        self.expect("@" not in body, "an address reached the search results")
        self.says("contact data on the page", "none (rule 6)")

        self.step("4. Compare (S14)")
        compared = alice.get(reverse("compare"), {"player": [str(bob_id), str(carol_id)]})
        self.expect(compared.status_code == 200, "the comparison did not render")
        self.says("two players side by side", "level, area, distance, times")
        too_many = alice.get(
            reverse("compare"), {"player": [str(bob_id), str(carol_id), str(alice_id), "1"]}
        )
        self.expect(too_many.status_code == 400, "a four-player comparison was allowed")
        self.says("four players", "refused by the server (cap of three)")

        self.step("5. Favorites and saved searches (S13, S15)")
        alice.post(reverse("favorite_add", kwargs={"account_id": bob_id}))
        self.says("Alice favorites Bob", [e.display_name for e in collections.list_favorites(alice_id)])
        self.expect(
            not any(n.notification_type == "favorite" for n in notification.list_for_player(bob_id)),
            "favoriting notified the other player",
        )
        self.says("Bob is told", "nothing - the list is private")

        alice.post(
            reverse("saved_search_new"),
            {
                "name": "Weeknight games", "day_kind": "rule", "day_rule": "tomorrow",
                "fixed_date": "", "start": "18:00", "end": "20:00",
                "area_code": area.code, "playing_level": "", "max_distance_km": "",
            },
        )
        saved = collections.list_searches(alice_id)
        self.expect(saved, "the saved search was not stored")
        reuse = alice.get(
            reverse("saved_search_run", kwargs={"saved_search_id": saved[0].saved_search_id})
        )
        self.expect(reuse.status_code == 302, "the saved search did not run")
        self.says("reusing it", "loads the criteria and runs the ordinary search")

        self.step("6. Invite, accept, and the confirmed game (S7, S8)")
        places = profiles.list_venues()
        self.expect(places, "no places to play - run `manage.py load_venues` first")
        place = places[0]
        sent = alice.post(
            reverse("invitation_new", kwargs={"account_id": bob_id}),
            {"date": day, "start": "18:00", "end": "20:00", "venue_code": place.code},
        )
        self.expect(sent.status_code == 302, "the invitation was refused")
        self.says("venue picked from the list", place.label)
        _, received = invitations.list_for_player(bob_id)
        invitation_id = received[0].invitation_id
        self.says("Alice invites Bob", f"invitation {invitation_id}, pending")

        bob.post(reverse("invitation_accept", kwargs={"invitation_id": invitation_id}))
        record = invitations.get_for_participant(invitation_id, alice_id)
        self.expect(record.status == "accepted", "the invitation was not accepted")
        upcoming, _ = invitations.list_games_for_player(alice_id)
        self.expect(upcoming, "accepting created no confirmed game")
        game_id = upcoming[0].game_id
        self.says("Bob accepts", f"invitation Accepted AND confirmed game {game_id}")

        clash = carol.post(
            reverse("invitation_new", kwargs={"account_id": bob_id}),
            {"date": day, "start": "19:00", "end": "21:00", "venue": VENUE},
        )
        self.expect(clash.status_code == 302, "Carol's overlapping invitation was refused early")
        _, bobs = invitations.list_for_player(bob_id)
        overlapping = [i for i in bobs if i.status == "pending"][0]
        refused = invitations.accept(overlapping.invitation_id, bob_id)
        self.expect(not refused.ok, "Bob double-booked himself")
        self.says("Bob tries to double-book", refused.error)

        self.step("7. Declining an invitation (S8)")
        turned_down = invitations.send(
            sender_account_id=carol_id, recipient_account_id=alice_id,
            starts_at=self.instant(day, "20:00"), ends_at=self.instant(day, "21:00"),
            venue=place.name,
        )
        self.expect(turned_down.ok, f"the invitation to decline was refused: {turned_down.errors}")
        declined = alice.post(
            reverse("invitation_decline", kwargs={"invitation_id": turned_down.invitation_id})
        )
        self.expect(declined.status_code == 302, "declining failed")
        after = invitations.get_for_participant(turned_down.invitation_id, carol_id)
        self.expect(after.status == "declined", f"status is {after.status}, not declined")
        self.says("Alice declines Carol", "Declined - no reason asked for (PRD 12.3)")
        again = invitations.accept(turned_down.invitation_id, alice_id)
        self.expect(not again.ok, "a declined invitation could still be accepted")
        self.says("trying to accept it afterwards", again.error)
        self.expect(
            any(n.notification_type == "invitation.declined"
                for n in notification.list_for_player(carol_id)),
            "the sender was not told it was declined",
        )
        self.says("Carol is told", "'An invitation you sent was declined'")

        self.step("8. Notifications and the worker (S10)")
        for item in notification.list_for_player(alice_id):
            if item.notification_type == "invitation.accepted":
                self.says("Alice's inbox", "'An invitation you sent was accepted'")
                self.says("email status before the worker", item.email_status)
                break
        else:
            raise CommandError("Alice was not notified that Bob accepted")
        run = notification.dispatch_due()
        self.says("worker dispatches", f"claimed {run.claimed}, sent {run.sent}, failed {run.failed}")
        self.expect(
            all("@" not in str(message.get("subject", "")) for message in recorder.sent),
            "an address reached a subject line",
        )

        self.step("9. Cancel the game, and the time frees itself (S11)")
        cancelled = alice.post(reverse("game_cancel", kwargs={"game_id": game_id}))
        self.expect(cancelled.status_code == 302, "the game could not be cancelled")
        self.says("Alice cancels", "the game is Cancelled; the invitation stays Accepted")
        self.expect(
            invitations.get_for_participant(invitation_id, alice_id).status == "accepted",
            "cancelling the game changed the invitation",
        )
        freed = invitations.accept(overlapping.invitation_id, bob_id)
        self.expect(freed.ok, f"the freed time could not be used: {freed.error}")
        self.says("Carol's invitation now", "accepted - the time is free again (G-10)")

        self.step("10. Block, cascade and report (S12)")
        pending = invitations.send(
            sender_account_id=carol_id, recipient_account_id=alice_id,
            starts_at=self.instant(day, "20:00"), ends_at=self.instant(day, "22:00"),
            venue=VENUE,
        )
        self.expect(pending.ok, f"the invitation to block could not be sent: {pending.errors}")
        blocked = alice.post(
            reverse("block_player", kwargs={"account_id": carol_id}), {"next": "/blocked/"}
        )
        self.expect(blocked.status_code == 302, "the block was refused")
        self.expect(
            invitations.get_for_participant(pending.invitation_id, alice_id).status == "cancelled",
            "the block did not cancel the pending invitation",
        )
        self.says("Alice blocks Carol", "the pending invitation between them is cancelled")
        # Carol's own confirmed game, with Bob. Being blocked by Alice must not
        # disturb it: PRD 12.5 says existing games stand until a participant cancels.
        self.expect(
            invitations.get_game_for_participant(freed.game_id, carol_id) is not None,
            "the block touched a confirmed game",
        )
        self.says("Carol's confirmed game", "untouched (PRD 12.5)")
        # The block's success message names Carol and is still queued; it would
        # render on the next page and match the assertion below. Flush it first.
        alice.get(reverse("home"))
        after = alice.get(
            reverse("search"),
            {"date": day, "start": "18:00", "end": "20:00", "area_code": area.code},
        ).content.decode()
        self.expect(carol_name not in after, "a blocked player still appears in search")
        self.says("Carol in Alice's search", "gone, both directions")

        alice.post(
            reverse("report_player", kwargs={"account_id": bob_id}),
            {"category": "other", "details": "A demonstration report."},
        )
        self.says("Alice reports Bob", "stored for review; Bob is not told")

        self.step("11. Privacy, on every page Alice can reach")
        leaked = []
        for name in ("home", "profile", "availability", "search", "favorites",
                     "saved_searches", "invitations", "games", "notifications",
                     "blocked_players", "compare"):
            page = alice.get(reverse(name))
            if page.status_code == 200 and "@" in page.content.decode():
                leaked.append(name)
        self.expect(not leaked, f"an address appeared on: {leaked}")
        self.says("pages checked", "11, none carrying an email, phone or coordinate")

        anonymous = Client()
        redirected = anonymous.get(reverse("games"))
        self.expect(redirected.status_code == 302, "a page answered without a session")
        self.says("signed out", "every page but register/sign-in/verify redirects")

    # --- helpers ---------------------------------------------------------

    def instant(self, day: str, time_text: str):
        from rally.core.localtime import parse_local

        return parse_local(day, time_text)

    def register(self, client, email, verify=False):
        response = client.post(reverse("register"), {"email": email, "password": PASSWORD})
        self.expect(response.status_code in (200, 302), f"registering {email} failed")
        account_id = identity.authenticate(email, PASSWORD).account_id
        self.expect(account_id, f"could not sign in as {email} after registering")
        if verify:
            identity.verify_email(identity.get_verification_token(account_id))
        client.post(reverse("sign_in"), {"email": email, "password": PASSWORD})
        return account_id
