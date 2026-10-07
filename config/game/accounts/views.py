"""Account views: login, logout, current user, volunteer creation."""
from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import IntegrityError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie

from game.core.auth import authenticated, issue_token, set_auth_cookie
from game.core.errors import ApiError, api_errors, failure, success
from game.core.http import api_methods, read_json, required_text
from game.core.limits import LOGIN_RATE_LIMIT
from game.core.models import GameUser, Team

_dummy_password_hash = make_password("not-a-real-account-password")


def _login(request: HttpRequest, *, role: str) -> JsonResponse:
    body = read_json(request)
    identifier_field = "code" if role == "team" else "username"
    identifier = required_text(body, identifier_field, maximum=80)
    if role == "team":
        identifier = identifier.upper()
    elif role in {"admin", "volunteer"}:
        identifier = identifier.lower()
    password = body.get("password")
    if not isinstance(password, str) or not password or len(password) > 1024:
        raise ApiError(400, "invalid_input", "password must be a non-empty string.")

    team = None
    if role == "team":
        team = Team.objects.filter(code=identifier, is_active=True).first()
        if team:
            user = GameUser.objects.filter(role="team", team_id=team.id, is_active=True).first()
        else:
            user = None
    else:
        user = GameUser.objects.filter(username=identifier, role=role, is_active=True).first()

    valid_password = check_password(
        password,
        user.password_hash if user else _dummy_password_hash,
    )
    if user is None or not valid_password:
        return failure("invalid_credentials", "Invalid username or password.", 401)

    payload: dict[str, Any] = {
        "id": str(user.id),
        "role": user.role,
        "username": user.username,
    }
    if role == "team" and team is not None:
        payload["team"] = {
            "id": team.id,
            "name": team.name,
            "code": team.code,
        }
    response = success(payload)
    set_auth_cookie(response, issue_token(user))
    return response


@api_errors
@ensure_csrf_cookie
@LOGIN_RATE_LIMIT
@api_methods("POST")
def team_login(request: HttpRequest) -> JsonResponse:
    return _login(request, role="team")


@api_errors
@ensure_csrf_cookie
@LOGIN_RATE_LIMIT
@api_methods("POST")
def admin_login(request: HttpRequest) -> JsonResponse:
    return _login(request, role="admin")


@api_errors
@ensure_csrf_cookie
@LOGIN_RATE_LIMIT
@api_methods("POST")
def volunteer_login(request: HttpRequest) -> JsonResponse:
    return _login(request, role="volunteer")


@api_errors
@authenticated(role="admin")
@api_methods("POST")
def create_volunteer(request: HttpRequest) -> JsonResponse:
    body = read_json(request)
    username = required_text(body, "username", maximum=80).lower()
    password = body.get("password")
    if not isinstance(password, str) or len(password) < 12 or len(password) > 1024:
        raise ApiError(
            400,
            "invalid_input",
            "password must be between 12 and 1024 characters.",
        )
    try:
        user = GameUser.objects.create(
            username=username,
            role="volunteer",
            password_hash=make_password(password),
            is_active=True,
        )
    except IntegrityError as exc:
        raise ApiError(
            409, "username_exists", "That username is already in use."
        ) from exc
    return success(
        {"id": str(user.id), "username": username, "role": "volunteer"},
        status=201,
    )


@api_errors
@ensure_csrf_cookie
@api_methods("POST")
def logout(request: HttpRequest) -> JsonResponse:
    response = success({"loggedOut": True})
    response.delete_cookie(settings.JWT_COOKIE_NAME, path="/", samesite="Lax")
    return response


@api_errors
@authenticated()
@api_methods("GET")
def current_user(request: HttpRequest) -> JsonResponse:
    user = request.game_user  # type: ignore[attr-defined]
    result: dict[str, Any] = {
        "id": str(user.id),
        "username": user.username,
        "role": user.role,
    }
    if user.role == "team":
        team = Team.objects.filter(id=user.team_id).first()
        if team is None:
            return failure("team_not_found", "The linked team no longer exists.", 404)
        result["team"] = {
            "id": team.id,
            "name": team.name,
            "code": team.code,
        }
    return success(result)
