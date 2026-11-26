"""Platform views for the account-setup flows (FR-01, FR-14; ASR-05; ADR-003).

Each view: collect input -> call M1's facade -> shape the result -> render. No business
decision is taken here (rule 14).
"""
from __future__ import annotations

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from rally.core.logging import log_operation
from rally.core.pipeline.session import end_session, start_session
from rally.modules.identity.api import facade as identity

# "queued", not "sent" and never "delivered": at this point the outbox record is
# committed and nothing has reached the provider yet (AGENTS.md §5 Honest feedback, FE-5).
REGISTERED_MESSAGE = (
    "Account created and a verification email is queued. "
    "Open the link in it to verify your address, then sign in."
)
SIGNED_OUT_MESSAGE = "You are signed out."


def _safe_next(request) -> str:
    candidate = request.POST.get("next") or request.GET.get("next") or ""
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return reverse("home")


@require_http_methods(["GET"])
def home(request):
    """The signed-in landing page. Reachable only with a session."""
    return render(request, "home.html")


@require_http_methods(["GET", "POST"])
def register(request):
    from rally.core.web.forms import RegisterForm

    if request.viewer is not None:
        return redirect("home")

    if request.method == "GET":
        return render(request, "register.html", {"form": RegisterForm()})

    form = RegisterForm(request.POST)
    form.is_valid()  # bind the data so the entered email is kept on re-display (AC2)
    result = identity.register(
        email=request.POST.get("email", ""),
        password=request.POST.get("password", ""),
    )
    if not result.ok:
        form.apply_errors(result.errors)
        log_operation("identity.register", "rejected", reasons=",".join(sorted(result.errors)))
        return render(request, "register.html", {"form": form}, status=400)

    # Success is reported only after the account is committed (FR-08 honesty rule).
    log_operation("identity.register", "created", account_id=result.account_id)
    messages.success(request, REGISTERED_MESSAGE)
    return redirect("sign_in")


@require_http_methods(["GET", "POST"])
def sign_in(request):
    from rally.core.web.forms import SignInForm

    if request.viewer is not None:
        return redirect("home")

    next_url = request.GET.get("next", "")
    if request.method == "GET":
        return render(request, "sign_in.html", {"form": SignInForm(), "next": next_url})

    form = SignInForm(request.POST)
    form.is_valid()
    result = identity.authenticate(
        email=request.POST.get("email", ""),
        password=request.POST.get("password", ""),
    )
    if not result.ok:
        form.add_error(None, result.reason)
        log_operation("identity.sign_in", "rejected")
        return render(
            request,
            "sign_in.html",
            {"form": form, "next": request.POST.get("next", "")},
            status=400,
        )

    start_session(request, result.account_id)
    log_operation("identity.sign_in", "started", account_id=result.account_id)
    return HttpResponseRedirect(_safe_next(request))


@require_http_methods(["POST"])
def sign_out(request):
    """State changes on POST with CSRF, never on GET (FE-9)."""
    account_id = request.viewer.account_id if request.viewer else None
    end_session(request)
    log_operation("identity.sign_out", "ended", account_id=account_id)
    messages.success(request, SIGNED_OUT_MESSAGE)
    return redirect("sign_in")


@require_http_methods(["GET", "POST"])
def verify_email(request, token: str):
    """The third and last route reachable without a session (AGENTS.md §5 Sessions).

    The emailed link is a GET and only *shows* a confirmation page; the state change
    happens on the POST with CSRF from that page (FE-9, AGENTS.md §5 [v5]).
    """
    if request.method == "GET":
        if identity.can_verify(token):
            return render(request, "verify_email.html", {"outcome": "confirm"})
        log_operation("identity.verify_email", "rejected", stage="show")
        return render(
            request,
            "verify_email.html",
            {"outcome": "rejected", "reason": identity.VERIFICATION_UNKNOWN_TOKEN},
            status=404,
        )

    result = identity.verify_email(token)
    if not result.ok:
        log_operation("identity.verify_email", "rejected", stage="confirm")
        return render(
            request,
            "verify_email.html",
            {"outcome": "rejected", "reason": result.reason},
            status=400,
        )

    log_operation("identity.verify_email", "verified", account_id=result.account_id)
    return render(request, "verify_email.html", {"outcome": "verified"})


@require_http_methods(["GET", "POST"])
def profile(request):
    """The owner's own profile (FR-01, FR-06, FR-14).

    Display name, playing level and general area belong to M2. The optional phone number
    belongs to M1 and never travels through M2 (rule 6). Both facades are called here;
    neither rule is decided here (rule 14).
    """
    from rally.modules.profiles.api import facade as profiles

    account_id = request.viewer.account_id
    areas = profiles.list_areas()
    levels = profiles.playing_levels()

    def page(values, errors, status=200):
        return render(
            request,
            "profile.html",
            {
                "values": values,
                "errors": errors,
                "areas": areas,
                "levels": levels,
                "has_phone": identity.has_phone(account_id),
                "is_complete": profiles.is_complete(account_id),
            },
            status=status,
        )

    if request.method == "GET":
        own = profiles.get_own_profile(account_id)
        return page(
            {
                "display_name": own.display_name,
                "playing_level": own.playing_level,
                "area_code": own.area_code,
            },
            {},
        )

    submitted = {
        "display_name": request.POST.get("display_name", ""),
        "playing_level": request.POST.get("playing_level", ""),
        "area_code": request.POST.get("area_code", ""),
    }
    # The account acted on is always the session's own. There is no route, parameter or
    # hidden field by which one player could edit another's profile (ADR-003, AC2).
    result = profiles.save_profile(account_id=account_id, **submitted)
    errors = dict(result.errors or {})

    if "remove_phone" in request.POST:
        errors.update(identity.set_phone(account_id, ""))
    elif request.POST.get("phone", "").strip():
        errors.update(identity.set_phone(account_id, request.POST["phone"]))

    if errors:
        log_operation("profile.save", "rejected", account_id=account_id, fields=",".join(sorted(errors)))
        return page(submitted, errors, status=400)

    log_operation("profile.save", "saved", account_id=account_id)
    messages.success(request, "Your profile is saved.")
    return redirect("profile")


@require_http_methods(["GET"])
def player_profile(request, account_id: int):
    """Another player's public profile (FR-14, ASR-04).

    Built from a public view model, so there is no path by which an email address, a
    phone number or a location could appear on this page.
    """
    from rally.core.shapers.profiles import public_profile_view
    from rally.modules.profiles.api import facade as profiles

    if account_id == request.viewer.account_id:
        return redirect("profile")

    view = public_profile_view(account_id, profiles.get_public_profile(account_id))
    return render(request, "player_profile.html", {"player": view})
