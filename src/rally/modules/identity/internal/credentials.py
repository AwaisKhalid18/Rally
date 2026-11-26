"""M1's credential and registration policy.

These are business rules and they live here, not in a form and not in Platform (rule 14).
"""
from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction

from rally.core import clock
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

    try:
        with transaction.atomic():
            account = Account.objects.create_account(
                email=email,
                password=password,
                is_verified=False,
                created_at=clock.now(),
            )
    except IntegrityError:
        # Lost a race against a simultaneous registration of the same address.
        return Registration(account_id=None, errors={"email": EMAIL_TAKEN})

    return Registration(account_id=account.pk, errors={})


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
