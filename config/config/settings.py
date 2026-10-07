"""
Django settings for four_spin project.
SQLite-based clone of the 4-SPIN game backend (no MongoDB).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")

DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "development-only-change-this-secret-before-deploying",
)
if not DEBUG and (
    not SECRET_KEY
    or len(SECRET_KEY) < 50
    or SECRET_KEY == "development-only-change-this-secret-before-deploying"
    or SECRET_KEY == "replace-with-a-long-random-secret"
    or SECRET_KEY == "generate-a-private-random-secret"
):
    raise RuntimeError(
        "DJANGO_SECRET_KEY must be a private random value of at least 50 characters "
        "when DEBUG is false."
    )

allowed_hosts = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]
render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if render_hostname:
    allowed_hosts.append(render_hostname)
ALLOWED_HOSTS = list(dict.fromkeys(allowed_hosts))

CSRF_TRUSTED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"


INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "game.core.apps.CoreConfig",
    "game.accounts.apps.AccountsConfig",
    "game.competition.apps.CompetitionConfig",
    "game.assignments.apps.AssignmentsConfig",
    "game.verifications.apps.VerificationsConfig",
    "game.leaderboard.apps.LeaderboardConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# ---------- SQLite database (replaces MongoDB) ----------
# SQLITE_PATH lets you point at a persistent disk in production (e.g. /var/data/db.sqlite3).
SQLITE_PATH = Path(os.environ.get("SQLITE_PATH", str(BASE_DIR / "db.sqlite3")))
SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": SQLITE_PATH,
        "OPTIONS": {
            "timeout": 20,
            # WAL = readers never block the writer; IMMEDIATE = no lock-upgrade deadlocks.
            "init_command": (
                "PRAGMA journal_mode=WAL;"
                "PRAGMA synchronous=NORMAL;"
                "PRAGMA busy_timeout=20000;"
                "PRAGMA foreign_keys=ON;"
            ),
            "transaction_mode": "IMMEDIATE",
        },
        "CONN_MAX_AGE": 60,
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------- JWT / Cookie / Rate limit settings ----------
JWT_COOKIE_NAME = os.environ.get("JWT_COOKIE_NAME", "game_session")
JWT_TTL_SECONDS = int(os.environ.get("JWT_TTL_SECONDS", "43200"))
COOKIE_SECURE = not DEBUG or os.environ.get("COOKIE_SECURE", "false").lower() == "true"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = COOKIE_SECURE
CSRF_COOKIE_SAMESITE = "Lax"
GAME_RATE_LIMIT_WINDOW_SECONDS = int(
    os.environ.get("GAME_RATE_LIMIT_WINDOW_SECONDS", "60")
)
if JWT_TTL_SECONDS < 1 or GAME_RATE_LIMIT_WINDOW_SECONDS < 1:
    raise RuntimeError("JWT_TTL_SECONDS and GAME_RATE_LIMIT_WINDOW_SECONDS must be positive.")
SOCKETIO_CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("SOCKETIO_CORS_ORIGINS", "").split(",")
    if origin.strip()
]

DATA_UPLOAD_MAX_MEMORY_SIZE = 64 * 1024
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
CSRF_FAILURE_VIEW = "game.core.errors.csrf_failure"


LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
