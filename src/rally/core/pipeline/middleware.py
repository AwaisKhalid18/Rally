"""Platform middleware.

`ViewerMiddleware`          — resolves the session into a public viewer view model.
`SessionRequiredMiddleware` — no handler is reachable without a session, except the three
                              public account-setup routes (AGENTS.md §5 Sessions, ADR-003).
`NoStoreMiddleware`         — authenticated responses are never cached (FE-9).

None of these contains a business rule (rule 14).
"""
from __future__ import annotations

from django.conf import settings
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.http import urlencode

from rally.core.shapers.identity import ViewerView, viewer_view
from rally.modules.identity.api import facade as identity

# The only routes reachable without a session. Adding a fourth needs an ADR
# (AGENTS.md §5 Sessions, §8). `verify_email` is routed in slice S2; naming it here now
# keeps the allowlist in one place.
PUBLIC_URL_NAMES = frozenset({"register", "sign_in", "verify_email"})

SIGN_IN_URL_NAME = "sign_in"


def _is_static(path: str) -> bool:
    static_url = settings.STATIC_URL or "/static/"
    return path.startswith(static_url)


class ViewerMiddleware:
    """Attach `request.viewer`: a public view model, never a domain entity (FE-1)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from rally.core.pipeline.session import current_account_id

        account_id = current_account_id(request)
        viewer: ViewerView | None = None
        if account_id is not None:
            summary = identity.account_summary(account_id)
            if summary is None:
                # The account is gone or disabled: the session is no longer valid.
                request.session.flush()
            else:
                viewer = viewer_view(summary)
        request.viewer = viewer
        return self.get_response(request)


class SessionRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if getattr(request, "viewer", None) is not None:
            return None
        if _is_static(request.path):
            return None
        match = getattr(request, "resolver_match", None)
        url_name = getattr(match, "url_name", None) if match else None
        if url_name in PUBLIC_URL_NAMES:
            return None
        destination = reverse(SIGN_IN_URL_NAME)
        if request.method == "GET" and request.path != destination:
            destination = f"{destination}?{urlencode({'next': request.get_full_path()})}"
        return HttpResponseRedirect(destination)


class NoStoreMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if getattr(request, "viewer", None) is not None:
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response["Pragma"] = "no-cache"
        return response
