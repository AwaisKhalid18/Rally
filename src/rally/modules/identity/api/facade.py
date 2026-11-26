"""M1 Identity — facade.

Published (AGENTS.md §3): `register`, `authenticate`, `is_verified`,
`get_delivery_address`, `account_summary`, and the read view `v_verified_account`.

Nothing here returns a model instance, an email address or a phone number to a caller
that is not M1 — with one documented exception, `get_delivery_address`, which M7 calls at
send time and must never store or log (rule 6, architecture §6.1 recorded refinement).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rally.modules.identity.internal import credentials
from rally.modules.identity.internal.models import Account

PASSWORD_MIN_LENGTH = credentials.PASSWORD_MIN_LENGTH

# The messages M1 puts in `RegistrationResult.errors` and `AuthenticationResult.reason`.
# They are part of the published contract: Platform renders them, and a caller outside M1
# must read them from here rather than from `internal` (rule 2).
SIGN_IN_FAILED = credentials.SIGN_IN_FAILED
EMAIL_REQUIRED = credentials.EMAIL_REQUIRED
EMAIL_INVALID = credentials.EMAIL_INVALID
EMAIL_TAKEN = credentials.EMAIL_TAKEN
PASSWORD_REQUIRED = credentials.PASSWORD_REQUIRED
PASSWORD_TOO_SHORT = credentials.PASSWORD_TOO_SHORT
VERIFICATION_UNKNOWN_TOKEN = credentials.VERIFICATION_UNKNOWN_TOKEN
VERIFICATION_ALREADY_DONE = credentials.VERIFICATION_ALREADY_DONE

VERIFIED_ACCOUNT_VIEW = "v_verified_account"


@dataclass(frozen=True)
class RegistrationResult:
    account_id: int | None = None
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.account_id is not None


@dataclass(frozen=True)
class AuthenticationResult:
    account_id: int | None = None
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.account_id is not None


@dataclass(frozen=True)
class AccountSummary:
    """The non-private facts about an account. No contact data (rule 6)."""

    account_id: int
    is_verified: bool


def register(email: str, password: str) -> RegistrationResult:
    """Create an unverified account. FR-01, PRD §12.2, ASR-06."""
    result = credentials.register(email, password)
    return RegistrationResult(account_id=result.account_id, errors=dict(result.errors))


def authenticate(email: str, password: str) -> AuthenticationResult:
    """Verify credentials. One generic reason on failure (PRD §12.2)."""
    account_id = credentials.authenticate(email, password)
    if account_id is None:
        return AuthenticationResult(reason=SIGN_IN_FAILED)
    return AuthenticationResult(account_id=account_id)


def account_summary(account_id: int) -> AccountSummary | None:
    """What Platform may know about the signed-in account. None when it cannot be used."""
    row = (
        Account.objects.filter(pk=account_id, is_active=True)
        .values("pk", "is_verified")
        .first()
    )
    if row is None:
        return None
    return AccountSummary(account_id=row["pk"], is_verified=row["is_verified"])


def is_verified(account_id: int) -> bool:
    """Verification gate for searchability (M2) and invitation eligibility (M5). ASR-06."""
    return Account.objects.filter(pk=account_id, is_active=True, is_verified=True).exists()


@dataclass(frozen=True)
class VerificationResult:
    account_id: int | None = None
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.account_id is not None


def can_verify(token: str) -> bool:
    """Whether this token would verify something. A read: the confirmation page uses it
    to show a clear message without changing any state (FE-9, AC3)."""
    return credentials.token_is_usable(token)


def verify_email(token: str) -> VerificationResult:
    """Burn a single-use token and mark the account verified. FR-01, PRD §12.2, ASR-06."""
    result = credentials.verify(token)
    return VerificationResult(account_id=result.account_id, reason=result.reason)


def get_verification_token(account_id: int) -> str | None:
    """The token to put in the verification email, read by M7 at send time only.

    Like `get_delivery_address`, it is used transiently: it is never written to `outbox`,
    to `notification` or to any log (architecture §6.1, rule 6). Returns None once the
    account is verified.
    """
    return credentials.verification_token_for(account_id)


def get_delivery_address(account_id: int) -> str | None:
    """The email address to send to, read by M7 at send time only.

    The caller must use it transiently: it is never written to `outbox`, to `notification`
    or to any log (architecture §6.1, rule 6).
    """
    return (
        Account.objects.filter(pk=account_id, is_active=True)
        .values_list("email", flat=True)
        .first()
    )


PHONE_MAX_LENGTH = credentials.PHONE_MAX_LENGTH
PHONE_TOO_LONG = credentials.PHONE_TOO_LONG


def set_phone(account_id: int, phone: str) -> dict[str, str]:
    """Store or clear the owner's own phone number. Returns field errors, empty on success.

    The caller may only pass the account it is acting as: M1 authorises its own records
    (ADR-003). Pass an empty string to remove the number.
    """
    return credentials.set_phone(account_id, phone)


def has_phone(account_id: int) -> bool:
    """Whether a number is on file — **not** the number itself.

    Rule 6 keeps email and phone out of every view and payload. The owner's screen needs
    to know that something is saved so it can offer to replace or remove it; it does not
    need the value, so the value never leaves M1.
    """
    return credentials.has_phone(account_id)
