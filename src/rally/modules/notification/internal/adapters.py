"""The email adapter — Rally's one external boundary (architecture section 7, CON-01).

The provider sits behind this interface so it can be substituted without touching M7's
dispatch logic, and so tests and the demo run without a provider (G-14). Only the worker
ever reaches it, never a web request (ASR-12).

Brevo is the chosen provider; it is reached through Django's built-in SMTP backend, so
no new library is added (AGENTS.md section 1). Which backend is live is configuration,
not code.
"""
from __future__ import annotations

from typing import Protocol

from django.core.mail import get_connection
from django.core.mail.message import EmailMessage


class EmailDeliveryFailed(Exception):
    """The provider did not accept the message. The worker retries, then gives up."""


class EmailAdapter(Protocol):
    def send(self, to_address: str, subject: str, body: str) -> str:
        """Hand the message to the provider.

        Returns a short provider response to record. Raises `EmailDeliveryFailed` when
        the provider did not accept it. The address is used and dropped: it is never
        returned, stored or logged (rule 6).
        """


class DjangoEmailAdapter:
    """Sends through whichever backend is configured (console by default, Brevo SMTP
    when the environment supplies credentials)."""

    def __init__(self, from_address: str) -> None:
        self._from_address = from_address

    def send(self, to_address: str, subject: str, body: str) -> str:
        message = EmailMessage(
            subject=subject,
            body=body,
            from_email=self._from_address,
            to=[to_address],
            connection=get_connection(fail_silently=False),
        )
        try:
            accepted = message.send()
        except Exception as error:  # the provider, the network, anything outside us
            raise EmailDeliveryFailed(type(error).__name__) from error
        if not accepted:
            raise EmailDeliveryFailed("provider accepted 0 recipients")
        return f"accepted:{accepted}"


class AlwaysFailingEmailAdapter:
    """Test double for the provider-down case (ADR-005 verification, plan.md S2 AC4)."""

    def __init__(self, reason: str = "provider unavailable") -> None:
        self.reason = reason
        self.calls: list[tuple[str, str]] = []

    def send(self, to_address: str, subject: str, body: str) -> str:
        self.calls.append((subject, body))
        raise EmailDeliveryFailed(self.reason)


class RecordingEmailAdapter:
    """Test double that succeeds and remembers what it was asked to send."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def send(self, to_address: str, subject: str, body: str) -> str:
        self.sent.append({"to": to_address, "subject": subject, "body": body})
        return "accepted:1"


_adapter: EmailAdapter | None = None


def current_adapter() -> EmailAdapter:
    global _adapter
    if _adapter is None:
        from django.conf import settings

        _adapter = DjangoEmailAdapter(from_address=settings.DEFAULT_FROM_EMAIL)
    return _adapter


def set_adapter(adapter: EmailAdapter | None) -> EmailAdapter | None:
    """Install an adapter and return the previous one. For tests and for wiring."""
    global _adapter
    previous, _adapter = _adapter, adapter
    return previous
