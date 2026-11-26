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

REGISTERED_MESSAGE = "Account created. Sign in to continue."
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
