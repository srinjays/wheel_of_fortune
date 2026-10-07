"""JWT authentication and cookie management (SQLite-backed)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import wraps
from http.cookies import CookieError, SimpleCookie
from typing import Any, Callable, TypeVar

import jwt
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie

from .errors import failure
from .models import GameUser

View = TypeVar("View", bound=Callable[..., JsonResponse])


def issue_token(user: GameUser | dict[str, Any]) -> str:
    """Issue a JWT for the given user (model instance or dict)."""
    now = datetime.now(timezone.utc)
    if isinstance(user, dict):
        user_id = str(user["id"])
        role = user["role"]
        team_id = user.get("team_id") or user.get("teamId")
    else:
        user_id = str(user.id)
        role = user.role
        team_id = user.team_id
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=settings.JWT_TTL_SECONDS),
    }
    if team_id:
        payload["teamId"] = team_id
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("sub"), str):
        return None
    return payload


def cookie_token_from_header(cookie_header: str) -> str | None:
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header)
    except (CookieError, ValueError):
        return None
    morsel = cookie.get(settings.JWT_COOKIE_NAME)
    return morsel.value if morsel is not None else None


def user_from_token(token: str) -> GameUser | None:
    """Validate token and return the active user from SQLite."""
    payload = decode_token(token)
    if payload is None:
        return None
    user_id = payload["sub"]
    try:
        user = GameUser.objects.filter(id=user_id, is_active=True).first()
    except (ValueError, Exception):
        return None
    if user is None or user.role != payload.get("role"):
        return None
    return user


def authenticated(
    *, role: str | tuple[str, ...] | None = None
) -> Callable[[View], View]:
    def decorate(view: View) -> View:
        @wraps(view)
        def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
            token = request.COOKIES.get(settings.JWT_COOKIE_NAME)
            if not token:
                return failure("authentication_required", "Please log in.", 401)
            user = user_from_token(token)
            if user is None:
                return failure("authentication_required", "Please log in again.", 401)
            allowed_roles = (role,) if isinstance(role, str) else role
            if allowed_roles is not None and user.role not in allowed_roles:
                return failure(
                    "forbidden",
                    "You do not have permission for this action.",
                    403,
                )
            request.game_user = user  # type: ignore[attr-defined]
            return view(request, *args, **kwargs)

        return ensure_csrf_cookie(wrapped)  # type: ignore[return-value]

    return decorate


def set_auth_cookie(response: JsonResponse, token: str) -> None:
    response.set_cookie(
        settings.JWT_COOKIE_NAME,
        token,
        max_age=settings.JWT_TTL_SECONDS,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="Lax",
        path="/",
    )
