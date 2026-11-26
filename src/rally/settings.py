"""Django settings for Rally.

Platform concern only (AGENTS.md §3, P): no business rule lives here.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # repository root
SRC_DIR = BASE_DIR / "src"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _flag(name: str, default: str = "0") -> bool:
    return _env(name, default).strip().lower() in {"1", "true", "yes", "on"}


# --- Core -------------------------------------------------------------------

SECRET_KEY = _env("RALLY_SECRET_KEY", "dev-only-not-a-secret-change-me")
DEBUG = _flag("RALLY_DEBUG", "1")
ALLOWED_HOSTS = [h.strip() for h in _env("RALLY_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h.strip()]

ROOT_URLCONF = "rally.urls"
WSGI_APPLICATION = "rally.wsgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

INSTALLED_APPS = [
    # Django infrastructure. `django.contrib.auth` is present only for the custom
    # AUTH_USER_MODEL and the password hashers; Rally does not use its login()/logout()
    # or its permission model. `django.contrib.sessions` provides M1's `session` store
    # (AGENTS.md §3.1: infrastructure, not hand-written). There is no admin (AGENTS.md §7).
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # P Platform
    "rally.core",
    # Capability modules — one line per module, added by the slice that first needs it.
    "rally.modules.identity",  # M1
    "rally.modules.profiles",  # M2
    "rally.modules.availability",  # M3
    "rally.modules.safety",  # M6
    # M4 Search is NOT a Django app: it owns no tables, so it has nothing to migrate.
    "rally.modules.notification",  # M7
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Platform pipeline: who is viewing, then is a session required, then no-store.
    "rally.core.pipeline.middleware.ViewerMiddleware",
    "rally.core.pipeline.middleware.SessionRequiredMiddleware",
    "rally.core.pipeline.middleware.NoStoreMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [SRC_DIR / "rally" / "core" / "web" / "templates"],
        "APP_DIRS": False,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
                "rally.core.web.context.viewer",
            ],
        },
    },
]

# --- Database ---------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _env("RALLY_DB_NAME", "rally"),
        "USER": _env("RALLY_DB_USER", "rally"),
        "PASSWORD": _env("RALLY_DB_PASSWORD", "rally"),
        "HOST": _env("RALLY_DB_HOST", "127.0.0.1"),
        "PORT": _env("RALLY_DB_PORT", "5432"),
    }
}

# M1 Identity owns the account table and the credential policy.
AUTH_USER_MODEL = "identity.Account"

# --- Time -------------------------------------------------------------------
# One configured display time zone; every timestamp is stored as UTC (AGENTS.md §5, G-11).
# State transitions use the injectable Clock in rally.core.clock, never a client timestamp
# (rule 8).

TIME_ZONE = _env("RALLY_TIME_ZONE", "Asia/Karachi")
USE_TZ = True
USE_I18N = True
LANGUAGE_CODE = "en-gb"

# --- Sessions and CSRF (ADR-008 S-05) ---------------------------------------

_SECURE_COOKIES = _flag("RALLY_SECURE_COOKIES", "0")
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = _SECURE_COOKIES
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
CSRF_COOKIE_HTTPONLY = False  # the template reads it only via the {% csrf_token %} tag
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = _SECURE_COOKIES
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# --- Static (same-origin only, ADR-008 S-07) --------------------------------

STATIC_URL = "/static/"
STATICFILES_DIRS = [SRC_DIR / "rally" / "core" / "web" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

# --- Email: the one external service (CON-01, ADR-008 S-08) ------------------
# Only the worker reaches it, through the adapter M7 owns. The default backend writes to
# the console so the demo never depends on a live provider (G-14); Brevo SMTP is switched
# on by configuration alone, and its credentials are injected, never committed.

RALLY_SITE_URL = _env("RALLY_SITE_URL", "http://127.0.0.1:8000")
DEFAULT_FROM_EMAIL = _env("RALLY_FROM_EMAIL", "rally@example.com")

if _flag("RALLY_EMAIL_LIVE", "0"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = _env("RALLY_SMTP_HOST", "smtp-relay.brevo.com")
    EMAIL_PORT = int(_env("RALLY_SMTP_PORT", "587"))
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = _env("RALLY_SMTP_USER")
    EMAIL_HOST_PASSWORD = _env("RALLY_SMTP_PASSWORD")
    EMAIL_TIMEOUT = int(_env("RALLY_SMTP_TIMEOUT", "10"))
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# --- Logging ----------------------------------------------------------------
# Structured, operation-level records for the NFR-04 measurement (ASR-12).
# No contact data may ever be logged (rule 6) — see rally.core.logging.

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "operation": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "operation"},
    },
    "loggers": {
        "rally": {"handlers": ["console"], "level": _env("RALLY_LOG_LEVEL", "INFO"), "propagate": False},
    },
}
