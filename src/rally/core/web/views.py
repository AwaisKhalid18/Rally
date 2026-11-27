"""Platform views for the account-setup flows (FR-01, FR-14; ASR-05; ADR-003).

Each view: collect input -> call M1's facade -> shape the result -> render. No business
decision is taken here (rule 14).
"""
from __future__ import annotations

from django.contrib import messages
from django.http import Http404, HttpResponseRedirect
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

    from rally.core.shapers.availability import NO_SLOTS_OTHER, slot_views
    from rally.modules.availability.api import facade as availability_api

    view = public_profile_view(account_id, profiles.get_public_profile(account_id))
    # Availability slots are a public field (PRD §12.2) and are composed here, read-only,
    # from M3's facade (rule 14). Approximate distance joins them when search arrives.
    slots = slot_views(availability_api.list_slots(account_id))
    return render(
        request,
        "player_profile.html",
        {"player": view, "slots": slots, "no_slots_reason": NO_SLOTS_OTHER},
    )


def _slot_form_values(request):
    return {
        "date": request.POST.get("date", ""),
        "start": request.POST.get("start", ""),
        "end": request.POST.get("end", ""),
    }


def _parse_slot(values) -> tuple[object, object, str | None]:
    """Turn the typed local date and times into two UTC instants (AGENTS.md §5)."""
    from rally.core.localtime import LocalTimeInvalid, parse_local

    try:
        starts_at = parse_local(values["date"], values["start"])
        ends_at = parse_local(values["date"], values["end"])
    except LocalTimeInvalid:
        return None, None, "Enter a date as YYYY-MM-DD and times as HH:MM."
    return starts_at, ends_at, None


@require_http_methods(["GET", "POST"])
def availability(request):
    """The owner's availability slots (FR-04, PRD §12.1).

    Individual dates and times. There is no recurring schedule in the MVP, so this page
    offers no way to create one (AGENTS.md §7).
    """
    from rally.core.shapers.availability import slot_views
    from rally.modules.availability.api import facade as availability_api

    account_id = request.viewer.account_id

    def page(values, error=None, status=200):
        return render(
            request,
            "availability.html",
            {
                "slots": slot_views(availability_api.list_slots(account_id)),
                "values": values,
                "error": error,
            },
            status=status,
        )

    if request.method == "GET":
        return page({"date": "", "start": "", "end": ""})

    values = _slot_form_values(request)
    starts_at, ends_at, error = _parse_slot(values)
    if error:
        return page(values, error, status=400)

    result = availability_api.add_slot(account_id, starts_at, ends_at)
    if not result.ok:
        log_operation("availability.add", "rejected", account_id=account_id)
        return page(values, result.error, status=400)

    log_operation("availability.add", "added", account_id=account_id, slot_id=result.slot_id)
    messages.success(request, "Your availability is saved.")
    return redirect("availability")


@require_http_methods(["GET", "POST"])
def availability_edit(request, slot_id: int):
    from rally.core.shapers.availability import slot_view
    from rally.modules.availability.api import facade as availability_api

    account_id = request.viewer.account_id
    # Only the owner's own slot is reachable; another player's id simply is not found.
    slot = availability_api.get_slot(account_id, slot_id)
    if slot is None:
        raise Http404(availability_api.NOT_FOUND)

    def page(values, error=None, status=200):
        return render(
            request,
            "availability_edit.html",
            {"slot_id": slot_id, "values": values, "error": error},
            status=status,
        )

    if request.method == "GET":
        view = slot_view(slot)
        return page({"date": view.date_text, "start": view.start_text, "end": view.end_text})

    values = _slot_form_values(request)
    starts_at, ends_at, error = _parse_slot(values)
    if error:
        return page(values, error, status=400)

    result = availability_api.edit_slot(account_id, slot_id, starts_at, ends_at)
    if not result.ok:
        log_operation("availability.edit", "rejected", account_id=account_id, slot_id=slot_id)
        return page(values, result.error, status=400)

    log_operation("availability.edit", "saved", account_id=account_id, slot_id=slot_id)
    messages.success(request, "Your availability is saved.")
    return redirect("availability")


@require_http_methods(["POST"])
def availability_delete(request, slot_id: int):
    """State changes on POST with CSRF, never on GET (FE-9)."""
    from rally.modules.availability.api import facade as availability_api

    account_id = request.viewer.account_id
    result = availability_api.remove_slot(account_id, slot_id)
    if not result.ok:
        log_operation("availability.remove", "rejected", account_id=account_id, slot_id=slot_id)
        raise Http404(result.error)

    log_operation("availability.remove", "removed", account_id=account_id, slot_id=slot_id)
    messages.success(request, "That playing time is removed.")
    return redirect("availability")


@require_http_methods(["GET"])
def search(request):
    """Find a partner (FR-02, FR-03, FR-05, FR-13; ASR-01, ASR-02, ASR-13).

    A search changes nothing, so it is a GET and its criteria live in the query string
    (FE-9). They are echoed back exactly as submitted — the system never silently alters
    them (FR-13, FE-7).

    M4 may read M2, M3 and M6 only through their published views, and the area list is
    not one of them, so Platform resolves the chosen area's centre through M2's facade
    and passes it in. Platform decides nothing: M4 judges the criteria (rule 14).
    """
    from rally.core.localtime import LocalTimeInvalid, parse_local
    from rally.core.shapers.search import no_results_guidance, result_views
    from rally.modules.profiles.api import facade as profiles
    from rally.modules.search.api import facade as search_api

    values = {
        "date": request.GET.get("date", ""),
        "start": request.GET.get("start", ""),
        "end": request.GET.get("end", ""),
        "area_code": request.GET.get("area_code", ""),
        # Optional (PRD §12.1). An empty level means any level; an empty distance means
        # the 10 km default. M4 decides both — Platform only carries them.
        "playing_level": request.GET.get("playing_level", ""),
        "max_distance_km": request.GET.get("max_distance_km", ""),
    }
    areas = profiles.list_areas()
    submitted = any(values.values())

    def page(results=None, errors=None, searched=False, status=200):
        return render(
            request,
            "search.html",
            {
                "values": values,          # echoed back exactly as submitted (FR-13)
                "areas": areas,
                "levels": profiles.playing_levels(),
                "distance_choices": search_api.DISTANCE_CHOICES_KM,
                "default_distance": search_api.DEFAULT_MAX_DISTANCE_KM,
                "results": results or [],
                "errors": errors or {},
                "searched": searched,
                "no_results_guidance": no_results_guidance(
                    level_used=bool(values["playing_level"]),
                    distance_used=bool(values["max_distance_km"]),
                ),
            },
            status=status,
        )

    if not submitted:
        return page()

    errors: dict[str, str] = {}
    window_start = window_end = None
    if not values["date"]:
        errors["date"] = search_api.DATE_REQUIRED
    else:
        for field, message in (("start", search_api.START_REQUIRED), ("end", search_api.END_REQUIRED)):
            if not values[field]:
                errors[field] = message
        if "start" not in errors and "end" not in errors:
            try:
                window_start = parse_local(values["date"], values["start"])
                window_end = parse_local(values["date"], values["end"])
            except LocalTimeInvalid:
                errors["date"] = "Enter a date as YYYY-MM-DD and times as HH:MM."

    centroid = None
    if values["area_code"]:
        centroid = profiles.area_centroid(values["area_code"])

    if errors:
        # Nothing is sent to M4 until the shape is right; the criteria stay as typed.
        return page(errors=errors, searched=True, status=400)

    outcome = search_api.search(
        searcher_id=request.viewer.account_id,
        window_start=window_start,
        window_end=window_end,
        area_code=values["area_code"],
        area_centroid=centroid,
        playing_level=values["playing_level"],
        max_distance_km=values["max_distance_km"],
    )
    if not outcome.ok:
        log_operation("search.run", "rejected", account_id=request.viewer.account_id)
        return page(errors=outcome.errors, searched=True, status=400)

    log_operation(
        "search.run",
        "done",
        account_id=request.viewer.account_id,
        results=len(outcome.results),
    )
    return page(results=result_views(outcome.results), searched=True)


def _invitation_views(records, viewer_id):
    """Resolve each counterpart's display name through M2, read-only (rule 14)."""
    from rally.core.shapers.invitations import invitation_view
    from rally.modules.profiles.api import facade as profiles

    views = []
    for record in records:
        other_id = record.other_party(viewer_id)
        profile = profiles.get_public_profile(other_id)
        views.append(
            invitation_view(record, viewer_id, profile.display_name if profile else None)
        )
    return views


@require_http_methods(["GET", "POST"])
def invitation_new(request, account_id: int):
    """Send an invitation to one player (FR-08, PRD §12.3).

    Reached from a search result or a player's profile. Every rule about whether the
    invitation may exist belongs to M5; this view collects the fields and reports what
    M5 decided (rule 14).
    """
    from rally.core.localtime import LocalTimeInvalid, parse_local
    from rally.modules.invitations.api import facade as invitations
    from rally.modules.profiles.api import facade as profiles

    sender_id = request.viewer.account_id
    recipient = profiles.get_public_profile(account_id)
    if recipient is None or account_id == sender_id:
        raise Http404(invitations.RECIPIENT_UNKNOWN)

    def page(values, errors=None, status=200):
        return render(
            request,
            "invitation_new.html",
            {"recipient": recipient, "values": values, "errors": errors or {}},
            status=status,
        )

    if request.method == "GET":
        return page({"date": "", "start": "", "end": "", "venue": ""})

    values = {
        "date": request.POST.get("date", ""),
        "start": request.POST.get("start", ""),
        "end": request.POST.get("end", ""),
        "venue": request.POST.get("venue", ""),
    }

    starts_at = ends_at = None
    errors: dict[str, str] = {}
    if not values["date"] or not values["start"] or not values["end"]:
        errors["date"] = "Enter the date and both times."
    else:
        try:
            starts_at = parse_local(values["date"], values["start"])
            ends_at = parse_local(values["date"], values["end"])
        except LocalTimeInvalid:
            errors["date"] = "Enter a date as YYYY-MM-DD and times as HH:MM."

    if errors:
        return page(values, errors, status=400)

    result = invitations.send(
        sender_account_id=sender_id,
        recipient_account_id=account_id,
        starts_at=starts_at,
        ends_at=ends_at,
        venue=values["venue"],
    )
    if not result.ok:
        log_operation("invitation.send", "rejected", account_id=sender_id)
        return page(values, result.errors, status=400)

    # Only now, after M5's transaction committed, is success reported (FR-08, AC4).
    log_operation(
        "invitation.send", "sent", account_id=sender_id, invitation_id=result.invitation_id
    )
    messages.success(request, "Your invitation is sent.")
    return redirect("invitations")


@require_http_methods(["GET"])
def invitations_list(request):
    """Sent and received invitations with their status (FR-10, ASR-05)."""
    from rally.modules.invitations.api import facade as invitations

    viewer_id = request.viewer.account_id
    sent, received = invitations.list_for_player(viewer_id)
    return render(
        request,
        "invitations.html",
        {
            "sent": _invitation_views(sent, viewer_id),
            "received": _invitation_views(received, viewer_id),
        },
    )


@require_http_methods(["GET"])
def invitation_detail(request, invitation_id: int):
    """One invitation — for a participant only.

    A non-participant gets a not-found, never a "forbidden": that would itself confirm
    the invitation exists (AC5, ASR-05).
    """
    from rally.modules.invitations.api import facade as invitations

    viewer_id = request.viewer.account_id
    record = invitations.get_for_participant(invitation_id, viewer_id)
    if record is None:
        raise Http404("No such invitation.")

    (view,) = _invitation_views([record], viewer_id)
    game = invitations.get_game_for_invitation(invitation_id, viewer_id)
    return render(request, "invitation_detail.html", {"invitation": view, "game": game})


@require_http_methods(["POST"])
def invitation_accept(request, invitation_id: int):
    """Accept, creating the confirmed game in one M5 transaction (FR-09, FR-15).

    POST with CSRF: this changes state, so it is never a GET (FE-9). Platform decides
    nothing — it reports the domain reason M5 gave, never a database error.
    """
    from rally.modules.invitations.api import facade as invitations

    viewer_id = request.viewer.account_id
    result = invitations.accept(invitation_id, viewer_id)
    if not result.ok:
        log_operation("invitation.accept", "rejected", account_id=viewer_id, invitation_id=invitation_id)
        messages.error(request, result.error)
        return redirect("invitation_detail", invitation_id=invitation_id)

    log_operation(
        "invitation.accept", "accepted", account_id=viewer_id,
        invitation_id=invitation_id, game_id=result.game_id,
    )
    messages.success(request, "Accepted. The game is confirmed.")
    return redirect("invitation_detail", invitation_id=invitation_id)


@require_http_methods(["POST"])
def invitation_decline(request, invitation_id: int):
    """Decline. No reason is asked for (PRD §12.3)."""
    from rally.modules.invitations.api import facade as invitations

    viewer_id = request.viewer.account_id
    result = invitations.decline(invitation_id, viewer_id)
    if not result.ok:
        log_operation("invitation.decline", "rejected", account_id=viewer_id, invitation_id=invitation_id)
        messages.error(request, result.error)
        return redirect("invitation_detail", invitation_id=invitation_id)

    log_operation("invitation.decline", "declined", account_id=viewer_id, invitation_id=invitation_id)
    messages.success(request, "Declined.")
    return redirect("invitation_detail", invitation_id=invitation_id)
