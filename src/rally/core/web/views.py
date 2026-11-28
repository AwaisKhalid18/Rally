"""Platform views for the account-setup flows (FR-01, FR-14; ASR-05; ADR-003).

Each view: collect input -> call M1's facade -> shape the result -> render. No business
decision is taken here (rule 14).
"""
from __future__ import annotations

from django.contrib import messages
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
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
    from rally.modules.player_collections.api import facade as collections

    return render(
        request,
        "player_profile.html",
        {
            "player": view,
            "slots": slots,
            "no_slots_reason": NO_SLOTS_OTHER,
            "is_favorited": collections.is_favorite(request.viewer.account_id, account_id),
        },
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
    # One lookup for the whole page, not one per result (ASR-13). Platform composes
    # M4 and M8 here; neither reads the other (rule 12).
    favorited = _favorited_ids(request.viewer.account_id)
    return page(results=result_views(outcome.results, favorited), searched=True)


def _favorited_ids(viewer_id) -> set:
    """The accounts this viewer has favorited, as one set (ASR-13).

    Read-only composition in Platform: M8 does not call M4 and M4 does not read M8
    (rule 12), so the page is where the two meet.
    """
    from rally.modules.player_collections.api import facade as collections

    if viewer_id is None:
        return set()
    return {entry.favorited_account_id for entry in collections.list_favorites(viewer_id)}


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

    # Places to play, M2's reference data beside the areas (PRD §12.3). The ones in
    # the recipient's own area come first, because that is where they are likely to
    # play. This list reserves nothing: court booking is excluded (PRD §12.5), and M5
    # still stores the venue as free text, so a player may name somewhere else.
    near = profiles.list_venues(recipient.area_code)
    elsewhere = [v for v in profiles.list_venues() if v.area_code != recipient.area_code]
    venues = near + elsewhere

    def page(values, errors=None, status=200):
        return render(
            request,
            "invitation_new.html",
            {
                "recipient": recipient,
                "values": values,
                "errors": errors or {},
                "venues": venues,
            },
            status=status,
        )

    if request.method == "GET":
        return page({"date": "", "start": "", "end": "", "venue": "", "venue_code": ""})

    values = {
        "date": request.POST.get("date", ""),
        "start": request.POST.get("start", ""),
        "end": request.POST.get("end", ""),
        "venue": request.POST.get("venue", ""),
        "venue_code": request.POST.get("venue_code", ""),
    }

    # A chosen venue becomes the invitation's venue text. M5 never learns the list
    # exists: it still receives, validates and stores a plain string (PRD §12.3).
    if values["venue_code"]:
        chosen = profiles.get_venue(values["venue_code"])
        if chosen is None:
            errors_venue = "That place is no longer listed. Pick another, or type one."
            return page(values, {"venue": errors_venue}, status=400)
        values["venue"] = chosen.name

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


@require_http_methods(["POST"])
def invitation_cancel(request, invitation_id: int):
    """The sender withdraws a pending invitation (FR-11, PRD §12.3).

    POST with CSRF; a GET changes nothing (FE-9). Cancelling an *invitation* is not the
    same action as cancelling a *confirmed game*, which arrives in S11.
    """
    from rally.modules.invitations.api import facade as invitations

    viewer_id = request.viewer.account_id
    result = invitations.cancel_invitation(invitation_id, viewer_id)
    if not result.ok:
        log_operation("invitation.cancel", "rejected", account_id=viewer_id, invitation_id=invitation_id)
        messages.error(request, result.error)
        return redirect("invitation_detail", invitation_id=invitation_id)

    log_operation("invitation.cancel", "cancelled", account_id=viewer_id, invitation_id=invitation_id)
    messages.success(request, "Invitation cancelled.")
    return redirect("invitation_detail", invitation_id=invitation_id)


# --- Notifications (S10) -----------------------------------------------------


@require_http_methods(["GET"])
def notifications(request):
    """A player's own inbox (FR-12, ASR-11).

    The notifications are already there: the appender committed each one with the
    accept, decline or cancellation that caused it, so this page is complete whether or
    not the worker has run and whether or not the provider is up (ASR-12). Only the
    email status beside each line reflects that.
    """
    from rally.modules.notification.api import facade as notification

    from rally.core.shapers.notifications import notification_views

    viewer_id = request.viewer.account_id
    records = notification.list_for_player(viewer_id)
    return render(
        request,
        "notifications.html",
        {
            "notifications": notification_views(records),
            "unread_count": notification.unread_count(viewer_id),
        },
    )


@require_http_methods(["POST"])
def notification_read(request, notification_id: int):
    """Mark one notification read. POST with CSRF (FE-9).

    A notification that is not this player's is simply not marked, and the player is
    told nothing about it — the same answer as for one that does not exist (ASR-05).
    """
    from rally.modules.notification.api import facade as notification

    viewer_id = request.viewer.account_id
    notification.mark_read(notification_id, viewer_id)
    return redirect("notifications")


@require_http_methods(["POST"])
def notifications_read_all(request):
    from rally.modules.notification.api import facade as notification

    marked = notification.mark_all_read(request.viewer.account_id)
    if marked:
        messages.success(request, f"Marked {marked} notification(s) as read.")
    return redirect("notifications")


# --- Confirmed games (S11) ---------------------------------------------------


def _game_views(details, _viewer_id):
    """Resolve each counterpart's display name through M2, read-only (rule 14)."""
    from rally.core.shapers.games import game_view
    from rally.modules.profiles.api import facade as profiles

    views = []
    for detail in details:
        profile = profiles.get_public_profile(detail.other_party_account_id)
        views.append(game_view(detail, profile.display_name if profile else None))
    return views


@require_http_methods(["GET"])
def games(request):
    """A player's confirmed games (FR-15, PRD §12.4).

    Both participants see the same game. Whether it can still be cancelled is M5's
    decision, already made on the server clock — this page only shows it (FE-4).
    """
    from rally.modules.invitations.api import facade as invitations

    viewer_id = request.viewer.account_id
    upcoming, finished = invitations.list_games_for_player(viewer_id)
    return render(
        request,
        "games.html",
        {
            "upcoming": _game_views(upcoming, viewer_id),
            "finished": _game_views(finished, viewer_id),
        },
    )


@require_http_methods(["GET", "POST"])
def game_cancel(request, game_id: int):
    """Cancel a confirmed game — GET asks, POST does it.

    PRD §12.4 requires an **explicit confirmation step** and no reason, so the GET
    renders a confirmation page and changes nothing; only the POST, with its CSRF
    token, cancels (FE-9). A non-participant gets a not-found either way (ASR-05).
    """
    from rally.modules.invitations.api import facade as invitations

    viewer_id = request.viewer.account_id
    detail = invitations.get_game_for_participant(game_id, viewer_id)
    if detail is None:
        raise Http404("No such game.")

    (view,) = _game_views([detail], viewer_id)
    if request.method == "GET":
        return render(request, "game_cancel.html", {"game": view})

    result = invitations.cancel_game(game_id, viewer_id)
    if not result.ok:
        log_operation("game.cancel", "rejected", account_id=viewer_id, game_id=game_id)
        messages.error(request, result.error)
        return redirect("games")

    # Only after M5's transaction committed (FE-5).
    messages.success(
        request,
        "The game is cancelled and the other player has been told. That time is free "
        "again, so you can look for another partner.",
    )
    return redirect("games")


# --- Safety: block, unblock, report (S12) ------------------------------------
#
# Every rule lives in M6. These views resolve the player, pass the request on and
# report what M6 decided (rule 14). The one thing they must not do is tell anybody
# that a block exists: see `blocked_players` below.


def _player_or_404(account_id: int, viewer_id: int):
    """The target of a block or a report, as a public view model.

    A player who does not exist, and the viewer themselves, are both a not-found.
    """
    from rally.modules.profiles.api import facade as profiles

    if account_id == viewer_id:
        raise Http404("No such player.")
    profile = profiles.get_public_profile(account_id)
    if profile is None:
        raise Http404("No such player.")
    return profile


@require_http_methods(["POST"])
def block_player(request, account_id: int):
    """Block a player from their profile, a search result or an invitation (AC1).

    POST with CSRF; blocking changes state and cancels invitations, so it is never a
    GET (FE-9). The cascade is M6's, inside M6's transaction.
    """
    from rally.modules.safety.api import facade as safety

    viewer_id = request.viewer.account_id
    profile = _player_or_404(account_id, viewer_id)

    result = safety.block(viewer_id, account_id)
    if not result.ok:
        messages.error(request, result.error)
        return redirect(_safe_next(request))

    cancelled = len(result.cancelled_invitation_ids)
    # Said plainly, and only after the transaction committed (FE-5). The count is the
    # player's own invitations with this player, so naming it tells them nothing new.
    note = f"You have blocked {profile.display_name}."
    if cancelled:
        note += (
            f" {cancelled} pending invitation(s) between you were cancelled."
            " Any confirmed game is unaffected until one of you cancels it."
        )
    messages.success(request, note)
    return redirect("blocked_players")


@require_http_methods(["POST"])
def unblock_player(request, account_id: int):
    """Unblock from the blocked-players list (AC3).

    Visibility returns at once. The cancelled invitations stay cancelled — nothing
    leaves a terminal status (PRD §12.5).
    """
    from rally.modules.safety.api import facade as safety

    viewer_id = request.viewer.account_id
    result = safety.unblock(viewer_id, account_id)
    if not result.ok:
        messages.error(request, result.error)
    else:
        messages.success(
            request,
            "Unblocked. You can see each other again, and either of you can send a new "
            "invitation. The invitations that were cancelled stay cancelled.",
        )
    return redirect("blocked_players")


@require_http_methods(["GET"])
def blocked_players(request):
    """The players you have blocked (AC3).

    **Your own blocks only.** M6 publishes no way to learn that somebody blocked you,
    and this page must never grow one: being told would defeat the point of blocking.
    """
    from rally.modules.profiles.api import facade as profiles
    from rally.modules.safety.api import facade as safety

    from rally.core.shapers.safety import blocked_player_views

    rows = safety.list_blocked(request.viewer.account_id)
    names = {
        row.blocked_account_id: profiles.get_public_profile(row.blocked_account_id)
        for row in rows
    }
    return render(
        request,
        "blocked_players.html",
        {"blocked": blocked_player_views(rows, names)},
    )


@require_http_methods(["GET", "POST"])
def report_player(request, account_id: int):
    """Report a player from their profile or from an invitation (AC4).

    A category and optional free text. Nothing is sent to anyone and the reported
    player is not told. The categories offered are the ones M6 accepts, read from M6,
    so the form and the rule cannot drift apart.
    """
    from rally.modules.safety.api import facade as safety

    viewer_id = request.viewer.account_id
    profile = _player_or_404(account_id, viewer_id)
    invitation_id = request.POST.get("invitation_id") or request.GET.get("invitation_id")
    invitation_id = int(invitation_id) if (invitation_id or "").isdigit() else None

    def page(values, errors=None, status=200):
        return render(
            request,
            "report_player.html",
            {
                "player": profile,
                "categories": safety.REPORT_CATEGORIES,
                "details_max_length": safety.REPORT_DETAILS_MAX_LENGTH,
                "invitation_id": invitation_id,
                "values": values,
                "errors": errors or {},
            },
            status=status,
        )

    if request.method == "GET":
        return page({"category": "", "details": ""})

    values = {
        "category": request.POST.get("category", ""),
        "details": request.POST.get("details", ""),
    }
    result = safety.report(
        reporter_account_id=viewer_id,
        reported_account_id=account_id,
        category=values["category"],
        details=values["details"],
        invitation_id=invitation_id,
    )
    if not result.ok:
        return page(values, result.errors, status=400)

    messages.success(
        request,
        "Thank you. Your report has been recorded and will be reviewed. You will not "
        "hear about it again here, and the other player is not told you reported them.",
    )
    return redirect("player_profile", account_id=account_id)


# --- Favorites (S13) ---------------------------------------------------------
#
# FR-16, which is **not** part of the Validated PRD (architecture §16.1, plan.md A-00).
#
# Every rule is M8's: the cap, the ownership check, what happens to an entry whose
# account is gone, and which pairs are omitted. These views pass the request on and
# print what M8 returned (rule 14).


@require_http_methods(["GET"])
def favorites(request):
    """A player's own favorites (FR-16).

    A favorite with no future playing times is **shown** with its reason, not hidden:
    the player curated this list, and dropping an entry silently is the behaviour
    FR-13 forbids for search criteria (architecture §16.8). Blocked pairs are the one
    exception and M8 omits them.
    """
    from rally.modules.player_collections.api import facade as collections

    from rally.core.shapers.collections import favorite_views

    viewer_id = request.viewer.account_id
    entries = collections.list_favorites(viewer_id)
    return render(
        request,
        "favorites.html",
        {
            "favorites": favorite_views(entries),
            "count": len(entries),
            "maximum": collections.max_favorites(),
        },
    )


@require_http_methods(["POST"])
def favorite_add(request, account_id: int):
    """Add a player from their profile or a search result.

    POST with CSRF (FE-9). Favoriting notifies nobody and writes no outbox record: the
    list is private (§16.8).
    """
    from rally.modules.player_collections.api import facade as collections

    viewer_id = request.viewer.account_id
    profile = _player_or_404(account_id, viewer_id)

    result = collections.add_favorite(viewer_id, account_id)
    if not result.ok:
        messages.error(request, result.error)
    else:
        messages.success(request, f"{profile.display_name} is in your favorites.")
    return redirect(_safe_next(request))


@require_http_methods(["POST"])
def favorite_remove(request, account_id: int):
    """Remove a player from your own list.

    No `_player_or_404` here: an entry whose account can no longer be resolved shows
    "No longer available" and must still be removable (AC2), so the profile is not
    looked up first.
    """
    from rally.modules.player_collections.api import facade as collections

    viewer_id = request.viewer.account_id
    result = collections.remove_favorite(viewer_id, account_id)
    if not result.ok:
        messages.error(request, result.error)
    else:
        messages.success(request, "Removed from your favorites.")
    return redirect(_safe_next(request))


# --- Compare (S14) -----------------------------------------------------------
#
# FR-17, which is **not** part of the Validated PRD (architecture §16.1, plan.md A-00).


@require_http_methods(["GET"])
def compare(request):
    """Compare up to three players side by side (FR-17, architecture §16.5).

    A GET, because it stores nothing and changes nothing: the selection travels in the
    query string, so removing or replacing a player is simply a different URL (§16.5).
    That is also why this is one of the few pages where a GET is right — it is a read.

    The cap of three is M4's and is enforced there; this view only reports what M4 said.
    """
    from rally.core.shapers.comparison import compared_player_views
    from rally.modules.profiles.api import facade as profiles
    from rally.modules.search.api import facade as search_api

    viewer_id = request.viewer.account_id
    raw = request.GET.getlist("player")
    selected = [int(value) for value in raw if value.isdigit()]

    if not selected:
        return render(
            request,
            "compare.html",
            {"players": [], "selected": [], "errors": {}, "maximum": search_api.MAX_COMPARED},
        )

    # §12.1's reference point: the centre of the viewer's own general area. Platform
    # resolves it, because the area list is not a published view (the same path
    # `search` already takes). Without a profile there is no point, and every distance
    # comes back absent with its reason rather than invented.
    own = profiles.get_own_profile(viewer_id)
    centroid = profiles.area_centroid(own.area_code) if own and own.area_code else None

    outcome = search_api.compare(viewer_id, selected, centroid)
    if not outcome.ok:
        log_operation("search.compare", "rejected", account_id=viewer_id, selected=len(selected))
        return render(
            request,
            "compare.html",
            {
                "players": [],
                "selected": selected,
                "errors": outcome.errors,
                "maximum": search_api.MAX_COMPARED,
            },
            status=400,
        )

    log_operation("search.compare", "done", account_id=viewer_id, compared=len(outcome.players))
    return render(
        request,
        "compare.html",
        {
            "players": compared_player_views(outcome.players),
            "selected": selected,
            "errors": {},
            "maximum": search_api.MAX_COMPARED,
        },
    )


# --- Saved searches (S15) ----------------------------------------------------
#
# FR-18, which is **not** part of the Validated PRD (architecture §16.1, plan.md A-00).
#
# Reuse is the one composition this slice adds: criteria from M8, then M4.search().
# M8 never calls M4 and M4 never reads M8 (rule 12); Platform is where they meet.


def _saved_search_form_values(request):
    return {
        "name": request.POST.get("name", ""),
        "day_kind": request.POST.get("day_kind", "rule"),
        "fixed_date": request.POST.get("fixed_date", ""),
        "day_rule": request.POST.get("day_rule", ""),
        "start": request.POST.get("start", ""),
        "end": request.POST.get("end", ""),
        "area_code": request.POST.get("area_code", ""),
        "playing_level": request.POST.get("playing_level", ""),
        "max_distance_km": request.POST.get("max_distance_km", ""),
    }


def _parse_saved_search(values):
    """Turn the typed strings into the types M8 takes. Returns (fields, errors)."""
    import datetime as _dt

    from rally.core.localtime import DATE_FORMAT, TIME_FORMAT

    errors: dict[str, str] = {}
    fields: dict = {}

    # Exactly one of the two says which day (G-05). The radio decides which the player
    # meant, so a leftover value in the other box cannot make the request ambiguous.
    if values["day_kind"] == "date":
        fields["day_rule"] = ""
        try:
            fields["fixed_date"] = _dt.datetime.strptime(values["fixed_date"], DATE_FORMAT).date()
        except ValueError:
            fields["fixed_date"] = None
            errors["day"] = "Enter a date as YYYY-MM-DD."
    else:
        fields["fixed_date"] = None
        fields["day_rule"] = values["day_rule"]

    for key, field in (("start", "start_time"), ("end", "end_time")):
        try:
            fields[field] = _dt.datetime.strptime(values[key], TIME_FORMAT).time()
        except ValueError:
            fields[field] = None

    fields["area_code"] = values["area_code"]
    fields["playing_level"] = values["playing_level"]
    distance = values["max_distance_km"]
    fields["max_distance_km"] = int(distance) if distance.isdigit() else None
    return fields, errors


@require_http_methods(["GET"])
def saved_searches(request):
    """A player's own saved searches (FR-18)."""
    from rally.modules.player_collections.api import facade as collections
    from rally.modules.profiles.api import facade as profiles

    from rally.core.shapers.collections import saved_search_views

    viewer_id = request.viewer.account_id
    records = collections.list_searches(viewer_id)
    areas = {area.code: area.name for area in profiles.list_areas()}
    return render(
        request,
        "saved_searches.html",
        {
            "searches": saved_search_views(records, areas),
            "count": len(records),
            "maximum": collections.max_saved_searches(),
        },
    )


@require_http_methods(["GET", "POST"])
def saved_search_edit(request, saved_search_id: int = 0):
    """Create or edit a saved search. Editing never runs one (§16.8)."""
    from rally.modules.player_collections.api import facade as collections
    from rally.modules.profiles.api import facade as profiles
    from rally.modules.search.api import facade as search_api

    viewer_id = request.viewer.account_id
    existing = (
        collections.get_search(saved_search_id, viewer_id) if saved_search_id else None
    )
    if saved_search_id and existing is None:
        raise Http404(collections.SEARCH_NOT_FOUND)

    def page(values, errors=None, status=200):
        return render(
            request,
            "saved_search_edit.html",
            {
                "values": values,
                "errors": errors or {},
                "existing": existing,
                "areas": profiles.list_areas(),
                "levels": profiles.playing_levels(),
                "day_rules": collections.DAY_RULE_CHOICES,
                "distance_choices": search_api.DISTANCE_CHOICES_KM,
            },
            status=status,
        )

    if request.method == "GET":
        from rally.core.localtime import DATE_FORMAT, TIME_FORMAT

        if existing is None:
            return page(
                {
                    "name": "", "day_kind": "rule", "fixed_date": "", "day_rule": "",
                    "start": "", "end": "", "area_code": "", "playing_level": "",
                    "max_distance_km": "",
                }
            )
        return page(
            {
                "name": existing.name,
                "day_kind": "date" if existing.fixed_date else "rule",
                "fixed_date": (
                    existing.fixed_date.strftime(DATE_FORMAT) if existing.fixed_date else ""
                ),
                "day_rule": existing.day_rule,
                "start": existing.start_time.strftime(TIME_FORMAT),
                "end": existing.end_time.strftime(TIME_FORMAT),
                "area_code": existing.area_code,
                "playing_level": existing.playing_level,
                "max_distance_km": str(existing.max_distance_km or ""),
            }
        )

    values = _saved_search_form_values(request)
    fields, errors = _parse_saved_search(values)
    if errors:
        return page(values, errors, status=400)

    if existing:
        result = collections.update_search(
            saved_search_id, viewer_id, name=values["name"], **fields
        )
    else:
        result = collections.save_search(viewer_id, name=values["name"], **fields)
    if not result.ok:
        return page(values, result.errors, status=400)

    messages.success(request, "Saved.")
    return redirect("saved_searches")


@require_http_methods(["POST"])
def saved_search_delete(request, saved_search_id: int):
    """Delete your own (FE-9: a POST, never a GET)."""
    from rally.modules.player_collections.api import facade as collections

    if collections.delete_search(saved_search_id, request.viewer.account_id):
        messages.success(request, "Deleted.")
    else:
        messages.error(request, collections.SEARCH_NOT_FOUND)
    return redirect("saved_searches")


@require_http_methods(["GET"])
def saved_search_run(request, saved_search_id: int):
    """Reuse a saved search (FR-18, architecture §16.8).

    **The composition this slice exists for.** Platform fetches the criteria from M8
    and calls `M4.search()` — the same entry point a typed search uses, so ASR-02 and
    ASR-10 apply identically. M8 does not run searches and M4 does not read M8.

    A fixed date that has passed is **not** run: the player is told it needs a new
    date (G-05). Silently shifting it to today would run a search they never asked for.
    """
    from rally.modules.player_collections.api import facade as collections

    viewer_id = request.viewer.account_id
    record = collections.get_search(saved_search_id, viewer_id)
    if record is None:
        raise Http404(collections.SEARCH_NOT_FOUND)

    if not record.can_run:
        messages.error(request, record.cannot_run_reason)
        return redirect("saved_search_edit", saved_search_id=saved_search_id)

    from rally.core.localtime import DATE_FORMAT, TIME_FORMAT

    # The criteria are handed to the ordinary search screen exactly as a player would
    # have typed them, so the results page echoes them back unchanged (FR-13, FE-7).
    query = {
        "date": record.resolved_date.strftime(DATE_FORMAT),
        "start": record.start_time.strftime(TIME_FORMAT),
        "end": record.end_time.strftime(TIME_FORMAT),
        "area_code": record.area_code,
        "playing_level": record.playing_level,
        "max_distance_km": str(record.max_distance_km or ""),
    }
    log_operation("saved_search.run", "reused", account_id=viewer_id)
    return redirect(f"{reverse('search')}?{urlencode(query)}")


# --- Messages (M9) -----------------------------------------------------------
#
# In-app chat. **Not in the Final Validated PRD**: PRD §12.5 records it as formally
# excluded, and it was added on an explicit instruction from the project lead. The PRD
# and an ADR still need to record that decision.
#
# Every rule is M9's: who may talk to whom, what a block does, and what a message may
# not contain. These views collect the words and report what M9 decided (rule 14).


def _conversation_views(records, viewer_id):
    """Resolve each counterpart's display name through M2, read-only (rule 14)."""
    from rally.core.shapers.messaging import conversation_views
    from rally.modules.profiles.api import facade as profiles

    names = {
        record.other_party_account_id: profiles.get_public_profile(
            record.other_party_account_id
        )
        for record in records
    }
    return conversation_views(records, names)


@require_http_methods(["GET"])
def conversations(request):
    """A player's own conversations (M9).

    Blocked pairs are omitted by M9, the same way they vanish from search and the
    favorites list (ASR-10).
    """
    from rally.modules.messaging.api import facade as messaging

    viewer_id = request.viewer.account_id
    records = messaging.list_conversations(viewer_id)
    return render(
        request,
        "conversations.html",
        {"conversations": _conversation_views(records, viewer_id)},
    )


@require_http_methods(["GET", "POST"])
def conversation(request, conversation_id: int):
    """One thread: read it, and say something.

    The GET marks what the other player sent as read — that is this page's own
    bookkeeping about the viewer, not a change to anybody else's data, so it does not
    need to be a POST. Posting a message does (FE-9).
    """
    from rally.core.shapers.messaging import message_views
    from rally.modules.messaging.api import facade as messaging
    from rally.modules.profiles.api import facade as profiles

    viewer_id = request.viewer.account_id
    other_id = messaging.other_party(conversation_id, viewer_id)
    if other_id is None:
        # Somebody else's thread is a not-found, never a "forbidden" (ASR-05).
        raise Http404(messaging.NOT_FOUND)

    other = profiles.get_public_profile(other_id)
    error = ""

    if request.method == "POST":
        result = messaging.post_message(
            conversation_id, viewer_id, request.POST.get("body", "")
        )
        if result.ok:
            return redirect("conversation", conversation_id=conversation_id)
        # The typed words come back with the reason, so nothing is lost.
        error = result.error

    messaging.mark_read(conversation_id, viewer_id)
    records = messaging.list_messages(conversation_id, viewer_id)
    return render(
        request,
        "conversation.html",
        {
            "conversation_id": conversation_id,
            "other_name": other.display_name if other else "A player who is no longer available",
            "other_id": other_id,
            # NOT "messages": that name is Django's flash-message context, and
            # base.html renders it as notices at the top of every page.
            "thread": message_views(records or [], viewer_id),
            "body": request.POST.get("body", "") if error else "",
            "error": error,
            "maximum": messaging.MESSAGE_MAX_LENGTH,
        },
        status=400 if error else 200,
    )


@require_http_methods(["POST"])
def conversation_open(request, account_id: int):
    """Start, or return to, the thread with one player.

    A POST because it may create a conversation (FE-9). M9 is idempotent, so pressing
    "Message" twice lands in the same place.
    """
    from rally.modules.messaging.api import facade as messaging

    viewer_id = request.viewer.account_id
    _player_or_404(account_id, viewer_id)

    result = messaging.open_conversation(viewer_id, account_id)
    if not result.ok:
        messages.error(request, result.error)
        return redirect(_safe_next(request))
    return redirect("conversation", conversation_id=result.conversation_id)
