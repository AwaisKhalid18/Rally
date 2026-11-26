"""The `account` table — the only place in Rally where contact data exists.

`email` and `phone` are **private** (PRD §12.2, rule 6). They appear in no published read
view, no response payload, no notification and no log outside M1.

There is no location field here or anywhere else in the schema (rule 7).
"""
from __future__ import annotations

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models

from rally.core import clock


class AccountManager(BaseUserManager):
    def create_account(self, email: str, password: str, **extra) -> "Account":
        account = self.model(email=email, **extra)
        account.set_password(password)
        account.save(using=self._db)
        return account


class Account(AbstractBaseUser):
    """A registered player's account.

    Rally does not use `django.contrib.auth`'s login(), permissions or groups; the class
    is used for its password hashing and for AUTH_USER_MODEL (AGENTS.md §3.1).
    """

    email = models.EmailField(unique=True)  # PRIVATE
    phone = models.CharField(max_length=32, blank=True, default="")  # PRIVATE, optional
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=clock.now, editable=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = AccountManager()

    class Meta:
        db_table = "account"
        verbose_name = "account"

    def __str__(self) -> str:  # pragma: no cover - never shown to a player
        return f"account:{self.pk}"
