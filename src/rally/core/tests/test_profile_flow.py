"""The S3 vertical slice end to end - plan.md S3 AC1 to AC4."""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from rally.modules.identity.api import facade as identity
from rally.modules.notification.api import facade as notification
from rally.modules.profiles.api import facade as profiles

PASSWORD = "longenough"
OWNER = "owner@example.com"
OTHER = "other@example.com"
AREAS = [
    {"code": "isb-f7", "name": "Islamabad F-7", "centroid_lat": "33.7211", "centroid_lon": "73.0551"},
    {"code": "isb-g9", "name": "Islamabad G-9", "centroid_lat": "33.6900", "centroid_lon": "73.0300"},
]


class ProfileFlowCase(TestCase):
    def setUp(self):
        previous = notification.set_email_adapter(notification.RecordingEmailAdapter())
        self.addCleanup(notification.set_email_adapter, previous)
        profiles.replace_areas(AREAS)
        self.owner_id = identity.register(OWNER, PASSWORD).account_id
        self.client.post(reverse("sign_in"), {"email": OWNER, "password": PASSWORD})

    def sign_in_as_other(self):
        self.other_id = identity.register(OTHER, PASSWORD).account_id
        profiles.save_profile(self.other_id, "Other Player", "beginner", "isb-g9")
        return self.other_id


class ProfilePageTests(ProfileFlowCase):
    def test_the_page_needs_a_session(self):
        self.client.post(reverse("sign_out"))
        self.assertEqual(self.client.get(reverse("profile")).status_code, 302)

    def test_an_owner_saves_a_profile(self):
        """AC1."""
        response = self.client.post(
            reverse("profile"),
            {"display_name": "Maaiz", "playing_level": "intermediate", "area_code": "isb-f7"},
        )

        self.assertRedirects(response, reverse("profile"))
        own = profiles.get_own_profile(self.owner_id)
        self.assertEqual((own.display_name, own.playing_level, own.area_code), ("Maaiz", "intermediate", "isb-f7"))

    def test_the_form_offers_the_fixed_area_list_and_the_three_levels(self):
        body = self.client.get(reverse("profile")).content.decode()

        self.assertIn("Islamabad F-7", body)
        self.assertIn("Islamabad G-9", body)
        for level in ("Beginner", "Intermediate", "Advanced"):
            self.assertIn(level, body)

    def test_the_page_offers_no_free_text_location_field(self):
        """Rule 7 - there is no field anywhere that accepts an exact location."""
        body = self.client.get(reverse("profile")).content.decode().lower()
        for forbidden in ('name="latitude"', 'name="longitude"', 'name="address"', 'name="postcode"'):
            self.assertNotIn(forbidden, body)

    def test_a_rejected_save_keeps_what_was_typed_and_names_the_field(self):
        """AC4."""
        response = self.client.post(
            reverse("profile"),
            {"display_name": "M", "playing_level": "professional", "area_code": "atlantis"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, profiles.NAME_TOO_SHORT, status_code=400)
        self.assertContains(response, profiles.LEVEL_INVALID, status_code=400)
        self.assertContains(response, profiles.AREA_INVALID, status_code=400)
        self.assertFalse(profiles.get_own_profile(self.owner_id).exists)

    def test_the_page_says_why_the_profile_is_not_complete_yet(self):
        self.client.post(
            reverse("profile"),
            {"display_name": "Maaiz", "playing_level": "beginner", "area_code": "isb-f7"},
        )

        body = self.client.get(reverse("profile")).content.decode()

        self.assertIn("not complete", body)
        self.assertIn("verified email", body)

    def test_verifying_the_email_completes_the_profile(self):
        self.client.post(
            reverse("profile"),
            {"display_name": "Maaiz", "playing_level": "beginner", "area_code": "isb-f7"},
        )
        identity.verify_email(identity.get_verification_token(self.owner_id))

        self.assertContains(self.client.get(reverse("profile")), "complete")
        self.assertTrue(profiles.is_complete(self.owner_id))


class PhoneIsPrivateTests(ProfileFlowCase):
    """AC1 - phone is optional and private. It lives in M1 and is never displayed back."""

    def _save(self, **extra):
        payload = {"display_name": "Maaiz", "playing_level": "beginner", "area_code": "isb-f7"}
        payload.update(extra)
        return self.client.post(reverse("profile"), payload)

    def test_a_phone_number_can_be_saved_and_removed(self):
        self._save(phone="03001234567")
        self.assertTrue(identity.has_phone(self.owner_id))

        self._save(remove_phone="1")
        self.assertFalse(identity.has_phone(self.owner_id))

    def test_the_saved_number_is_never_rendered_back(self):
        """Rule 6 - the value never leaves M1, so the page reports only that one is on
        file. Not even the owner's own page echoes it."""
        self._save(phone="03001234567")

        body = self.client.get(reverse("profile")).content.decode()

        self.assertNotIn("03001234567", body)
        self.assertIn("A phone number is saved", body)

    def test_a_too_long_number_is_rejected(self):
        response = self._save(phone="0" * 40)

        self.assertContains(response, identity.PHONE_TOO_LONG, status_code=400)
        self.assertFalse(identity.has_phone(self.owner_id))


class OnlyTheOwnerEditsTests(ProfileFlowCase):
    """AC2 - a direct request to edit another player's profile is rejected."""

    def test_a_posted_account_id_is_ignored(self):
        other_id = self.sign_in_as_other()

        self.client.post(
            reverse("profile"),
            {
                "display_name": "Hijacked",
                "playing_level": "advanced",
                "area_code": "isb-f7",
                "account_id": other_id,
            },
        )

        self.assertEqual(profiles.get_own_profile(other_id).display_name, "Other Player")
        self.assertEqual(profiles.get_own_profile(self.owner_id).display_name, "Hijacked")

    def test_there_is_no_route_to_another_players_edit_page(self):
        other_id = self.sign_in_as_other()

        response = self.client.get(reverse("player_profile", kwargs={"account_id": other_id}))

        # The page carries the layout's sign-out form and nothing else that writes:
        # no profile field, and no action pointing at the edit route.
        for editable in ('name="display_name"', 'name="playing_level"', 'name="area_code"'):
            self.assertNotContains(response, editable)
        self.assertNotContains(response, f'action="{reverse("profile")}"')


class PublicProfilePageTests(ProfileFlowCase):
    """AC3 - what another player's page shows, and what it can never show."""

    def test_it_shows_the_public_fields(self):
        other_id = self.sign_in_as_other()

        response = self.client.get(reverse("player_profile", kwargs={"account_id": other_id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Other Player")
        self.assertContains(response, "Beginner")
        self.assertContains(response, "Islamabad G-9")

    def test_it_shows_no_contact_address_or_location(self):
        other_id = self.sign_in_as_other()
        identity.set_phone(other_id, "03009999999")

        body = self.client.get(
            reverse("player_profile", kwargs={"account_id": other_id})
        ).content.decode()

        self.assertNotIn(OTHER, body)
        self.assertNotIn("@", body)
        self.assertNotIn("03009999999", body)
        self.assertNotIn("33.69", body)  # no centroid, no coordinates of any kind

    def test_it_needs_a_session(self):
        other_id = self.sign_in_as_other()
        self.client.post(reverse("sign_out"))

        response = self.client.get(reverse("player_profile", kwargs={"account_id": other_id}))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("sign_in"), response.headers["Location"])

    def test_a_player_without_a_profile_is_reported_with_a_reason(self):
        """Rule 13 - absent, with a reason, never a blank card."""
        stranger = identity.register("stranger@example.com", PASSWORD).account_id

        response = self.client.get(reverse("player_profile", kwargs={"account_id": stranger}))

        self.assertContains(response, "has not set up their profile")

    def test_viewing_your_own_page_sends_you_to_your_editable_one(self):
        response = self.client.get(reverse("player_profile", kwargs={"account_id": self.owner_id}))
        self.assertRedirects(response, reverse("profile"))

    def test_no_contact_address_reaches_a_log_line(self):
        other_id = self.sign_in_as_other()

        with self.assertLogs("rally.operation", level="INFO") as captured:
            self.client.post(
                reverse("profile"),
                {"display_name": "Maaiz", "playing_level": "beginner", "area_code": "isb-f7", "phone": "0300111"},
            )
            self.client.get(reverse("player_profile", kwargs={"account_id": other_id}))

        written = "\n".join(captured.output)
        self.assertIn("operation=profile.save outcome=saved", written)
        self.assertNotIn("@", written)
        self.assertNotIn("0300111", written)


class LoadAreasCommandTests(TestCase):
    def test_the_command_loads_the_shipped_list(self):
        from io import StringIO

        out = StringIO()
        call_command("load_areas", stdout=out)

        self.assertIn("loaded", out.getvalue())
        codes = {area.code for area in profiles.list_areas()}
        self.assertIn("isb-f7", codes)
        self.assertGreater(len(codes), 10)
