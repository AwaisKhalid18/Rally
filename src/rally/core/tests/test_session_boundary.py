"""AC4 - no route is reachable without a session except the three public ones.

The test walks the URL conf rather than listing routes by hand, so a route added later
without a session is caught here (AGENTS.md section 5 Sessions, ADR-003, FE-3).
"""
from django.test import TestCase
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from rally.core.pipeline.middleware import PUBLIC_URL_NAMES


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
                response = self.client.get(reverse(name))
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
        for name in sorted(PUBLIC_URL_NAMES):
            try:
                url = reverse(name)
            except Exception:
                continue  # verify_email is routed in slice S2
            with self.subTest(route=name):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_the_allowlist_is_exactly_the_three_account_setup_routes(self):
        self.assertEqual(PUBLIC_URL_NAMES, frozenset({"register", "sign_in", "verify_email"}))

    def test_a_static_asset_is_not_pushed_through_the_session_check(self):
        response = self.client.get("/static/css/rally.css")
        self.assertNotEqual(response.status_code, 302)

    def test_the_redirect_carries_the_requested_page(self):
        response = self.client.get(reverse("home"))
        self.assertIn("next=", response.headers["Location"])
