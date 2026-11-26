"""M1's credential and registration policy.

These are business rules and they live here, not in a form and not in Platform (rule 14).
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass

from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction

from rally.core import clock
from rally.core.ports.outbox import EVENT_ACCOUNT_VERIFICATION_REQUESTED, RECIPIENT_KEY, append_outbox
from rally.modules.identity.internal.models import Account

PASSWORD_MIN_LENGTH = 8
EMAIL_MAX_LENGTH = 254

EMAIL_INVALID = "Enter a valid email address."
EMAIL_REQUIRED = "Enter your email address."
EMAIL_TAKEN = "An account with this email address already exists."
EMAIL_TOO_LONG = f"An email address may be at most {EMAIL_MAX_LENGTH} characters."
PASSWORD_REQUIRED = "Enter a password."
PASSWORD_TOO_SHORT = f"Use at least {PASSWORD_MIN_LENGTH} characters."

# One generic message for every failed sign-in, so the form never reveals whether an
# address is registered (PRD §12.2, ASR-04).
SIGN_IN_FAILED = "Email address or password is not correct."

# Verification (PRD §12.2, ASR-06). A token is single use; there is no resend.
TOKEN_BYTES = 32
VERIFICATION_UNKNOWN_TOKEN = (
    "This verification link is not valid. It may already have been used, "
    "or it may have been copied incompletely."
)
VERIFICATION_ALREADY_DONE = "This email address is already verified. You can sign in."

# Compared against when no account matches, so a missing address and a wrong password
# cost the same time.
_DUMMY_HASH = make_password("rally-timing-equaliser")


def normalise_email(raw: str) -> str:
    return (raw or "").strip().lower()


def validate_registration(email: str, password: str) -> dict[str, str]:
    """Return a field -> message mapping. Empty means the input is acceptable."""
    errors: dict[str, str] = {}

    if not email:
        errors["email"] = EMAIL_REQUIRED
    elif len(email) > EMAIL_MAX_LENGTH:
        errors["email"] = EMAIL_TOO_LONG
    else:
        try:
            validate_email(email)
        except ValidationError:
            errors["email"] = EMAIL_INVALID

    if not password:
        errors["password"] = PASSWORD_REQUIRED
    elif len(password) < PASSWORD_MIN_LENGTH:
        errors["password"] = PASSWORD_TOO_SHORT

    return errors


@dataclass(frozen=True)
class Registration:
    account_id: int | None
    errors: dict[str, str]

    @property
    def ok(self) -> bool:
        return self.account_id is not None


def register(raw_email: str, raw_password: str) -> Registration:
    email = normalise_email(raw_email)
    password = raw_password or ""

    errors = validate_registration(email, password)
    if errors:
        return Registration(account_id=None, errors=errors)

    if Account.objects.filter(email=email).exists():
        return Registration(account_id=None, errors={"email": EMAIL_TAKEN})

    now = clock.now()
    try:
        # One transaction: the account and the event that will tell the player about it
        # are committed together, or neither is (AC1, ADR-005). No email is sent here -
        # the web request never touches the provider (rule 5, ASR-12).
        with transaction.atomic():
            account = Account.objects.create_account(
                email=email,
                password=password,
                is_verified=False,
                created_at=now,
                verification_token=secrets.token_urlsafe(TOKEN_BYTES),
                verification_requested_at=now,
            )
            append_outbox(
                EVENT_ACCOUNT_VERIFICATION_REQUESTED,
                {RECIPIENT_KEY: account.pk},
            )
    except IntegrityError:
        # Lost a race against a simultaneous registration of the same address.
        return Registration(account_id=None, errors={"email": EMAIL_TAKEN})

    return Registration(account_id=account.pk, errors={})


@dataclass(frozen=True)
class Verification:
    account_id: int | None = None
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.account_id is not None


def token_is_usable(token: str) -> bool:
    """Can this token still verify an account? Reads only - no state changes (FE-9)."""
    if not token:
        return False
    return Account.objects.filter(verification_token=token, is_active=True).exists()


def verify(token: str) -> Verification:
    """Mark the account verified and burn the token. Idempotent by construction: the
    token is cleared, so a second use finds nothing and changes nothing (AC3)."""
    if not token:
        return Verification(reason=VERIFICATION_UNKNOWN_TOKEN)

    with transaction.atomic():
        account = (
            Account.objects.select_for_update()
            .filter(verification_token=token, is_active=True)
            .first()
        )
        if account is None:
            return Verification(reason=VERIFICATION_UNKNOWN_TOKEN)
        if account.is_verified:
            return Verification(reason=VERIFICATION_ALREADY_DONE)

        account.is_verified = True
        account.verified_at = clock.now()  # server UTC, never a client timestamp (rule 8)
        account.verification_token = None
        account.save(update_fields=["is_verified", "verified_at", "verification_token"])

    return Verification(account_id=account.pk)


def verification_token_for(account_id: int) -> str | None:
    return (
        Account.objects.filter(pk=account_id, is_active=True, is_verified=False)
        .values_list("verification_token", flat=True)
        .first()
    )


def authenticate(raw_email: str, raw_password: str) -> int | None:
    """Return the account id when the credentials match, otherwise None."""
    email = normalise_email(raw_email)
    password = raw_password or ""

    account = Account.objects.filter(email=email, is_active=True).first()
    if account is None:
        check_password(password, _DUMMY_HASH)
        return None
    if not account.check_password(password):
        return None
    return account.pk
