"""IP-based rate limiting using SQLite."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import wraps
import hashlib
import json
from typing import Any, Callable, TypeVar

from django.conf import settings
from django.db import IntegrityError
from django.db.models import F
from django.http import HttpRequest, JsonResponse

from .errors import failure
from .models import RateLimit

View = TypeVar("View", bound=Callable[..., JsonResponse])


def _cleanup_expired() -> None:
    """Remove expired rate-limit rows (replaces MongoDB TTL index)."""
    RateLimit.objects.filter(expire_at__lt=datetime.now(timezone.utc)).delete()


def _client_ip(request: HttpRequest) -> str:
    # Behind Render/NGINX the real client is the first X-Forwarded-For hop.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _login_identifier(request: HttpRequest) -> str:
    """Account being targeted, so teams sharing one venue IP don't throttle each other."""
    try:
        body = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return ""
    if not isinstance(body, dict):
        return ""
    value = body.get("code") or body.get("username") or ""
    return str(value).strip().lower()[:80]


def rate_limit(*, limit: int, window_seconds: int) -> Callable[[View], View]:
    def decorate(view: View) -> View:
        @wraps(view)
        def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
            ip = _client_ip(request)
            identifier = _login_identifier(request)
            window_start = int(datetime.now(timezone.utc).timestamp()) // window_seconds
            key = hashlib.sha256(
                f"{view.__module__}.{view.__name__}:{ip}:{identifier}:{window_start}".encode()
            ).hexdigest()
            expiry = datetime.fromtimestamp(
                (window_start + 1) * window_seconds, tz=timezone.utc
            ) + timedelta(seconds=2)

            _cleanup_expired()

            # Atomic increment (no lost updates under concurrency).
            updated = RateLimit.objects.filter(key=key).update(count=F("count") + 1)
            if not updated:
                try:
                    RateLimit.objects.create(key=key, count=1, expire_at=expiry)
                except IntegrityError:
                    RateLimit.objects.filter(key=key).update(count=F("count") + 1)
            row = RateLimit.objects.filter(key=key).only("count").first()

            if row is not None and row.count > limit:
                return failure(
                    "rate_limited",
                    "Too many requests. Please wait before trying again.",
                    429,
                )
            return view(request, *args, **kwargs)

        return wrapped  # type: ignore[return-value]

    return decorate


LOGIN_RATE_LIMIT = rate_limit(
    limit=5,
    window_seconds=settings.GAME_RATE_LIMIT_WINDOW_SECONDS,
)
