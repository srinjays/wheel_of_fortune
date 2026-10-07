"""HTTP request helpers."""
from __future__ import annotations

import json
from functools import wraps
from typing import Any, Callable, TypeVar

from django.http import HttpRequest

from .errors import ApiError, failure

View = TypeVar("View", bound=Callable[..., Any])


def api_methods(*methods: str) -> Callable[[View], View]:
    def decorate(view: View) -> View:
        @wraps(view)
        def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
            if request.method not in methods:
                return failure(
                    "method_not_allowed",
                    f"Use one of these methods: {', '.join(methods)}.",
                    405,
                )
            return view(request, *args, **kwargs)

        return wrapped  # type: ignore[return-value]

    return decorate


def read_json(request: HttpRequest) -> dict[str, Any]:
    try:
        body = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ApiError(400, "invalid_json", "Request body must be valid JSON.") from exc
    if not isinstance(body, dict):
        raise ApiError(400, "invalid_body", "Request body must be a JSON object.")
    return body


def required_text(
    body: dict[str, Any],
    field: str,
    *,
    minimum: int = 1,
    maximum: int = 500,
) -> str:
    value = body.get(field)
    if not isinstance(value, str):
        raise ApiError(400, "invalid_input", f"{field} must be a string.")
    value = value.strip()
    if not minimum <= len(value) <= maximum:
        raise ApiError(
            400,
            "invalid_input",
            f"{field} must be between {minimum} and {maximum} characters.",
        )
    return value


def required_int(
    body: dict[str, Any], field: str, *, minimum: int, maximum: int
) -> int:
    value = body.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(400, "invalid_input", f"{field} must be an integer.")
    if not minimum <= value <= maximum:
        raise ApiError(
            400,
            "invalid_input",
            f"{field} must be between {minimum} and {maximum}.",
        )
    return value


def iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None
