"""AC4 - no route is reachable without a session except the three public ones.

The test walks the URL conf rather than listing routes by hand, so a route added later
without a session is caught here (AGENTS.md section 5 Sessions, ADR-003, FE-3).
"""
from django.test import TestCase
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from rally.core.pipeline.middleware import PUBLIC_URL_NAMES


# Routes that take a parameter need a sample value before they can be reversed. A new
# route with parameters must be added here, which is deliberate: it forces whoever adds
# it to say how it is reached, and keeps it inside the session check.
SAMPLE_ARGS = {
    "verify_email": {"token": "no-such-token"},
    "player_profile": {"account_id": 999999},
    "availability_edit": {"slot_id": 999999},
    "availability_delete": {"slot_id": 999999},
    "invitation_new": {"account_id": 999999},
    "invitation_detail": {"invitation_id": 999999},
    "invitation_accept": {"invitation_id": 999999},
    "invitation_decline": {"invitation_id": 999999},
    "invitation_cancel": {"invitation_id": 999999},
}


def named_routes() -> list[str]:
    """Every named route in the project, flattened."""
    names: list[str] = []

    def walk(patterns) -> None:
        for entry in patterns:
            if isinstance(entry, URLResolver):
                walk(entry.url_patterns)
            elif isinstance(entry, URLPattern) and entry.name:
                names.append(entry.name)

    walk(get_resolver().url_patterns)
    return sorted(set(names))


class SessionBoundaryTests(TestCase):
    def test_the_url_conf_has_routes_to_walk(self):
        self.assertIn("home", named_routes())

    def test_every_protected_route_redirects_an_anonymous_visitor_to_sign_in(self):
        sign_in = reverse("sign_in")
        checked = []

        for name in named_routes():
            if name in PUBLIC_URL_NAMES:
                continue
            with self.subTest(route=name):
                response = self.client.get(reverse(name, kwargs=SAMPLE_ARGS.get(name, {})))
                self.assertEqual(
                    response.status_code, 302, "{} answered an anonymous request".format(name)
                )
                self.assertTrue(
                    response.headers["Location"].startswith(sign_in),
                    "{} redirected to {}, not to sign-in".format(name, response.headers["Location"]),
                )
                checked.append(name)

        self.assertTrue(checked, "no protected route was checked")

    def test_the_public_routes_answer_without_a_session(self):
        sign_in = reverse("sign_in")
        urls = {
            "register": reverse("register"),
            "sign_in": sign_in,
            # Any token answers; an unknown one answers 404, which is still an answer and
            # not a redirect to sign-in.
            "verify_email": reverse("verify_email", kwargs=SAMPLE_ARGS["verify_email"]),
        }
        self.assertEqual(set(urls), set(PUBLIC_URL_NAMES))

        for name, url in sorted(urls.items()):
            with self.subTest(route=name):
                response = self.client.get(url)
                self.assertIn(response.status_code, (200, 404))
                self.assertNotEqual(response.status_code, 302)

    def test_the_allowlist_is_exactly_the_three_account_setup_routes(self):
        self.assertEqual(PUBLIC_URL_NAMES, frozenset({"register", "sign_in", "verify_email"}))

    def test_a_static_asset_is_not_pushed_through_the_session_check(self):
        response = self.client.get("/static/css/rally.css")
        self.assertNotEqual(response.status_code, 302)

    def test_the_redirect_carries_the_requested_page(self):
        response = self.client.get(reverse("home"))
        self.assertIn("next=", response.headers["Location"])
