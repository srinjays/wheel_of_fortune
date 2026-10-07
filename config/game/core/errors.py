"""Standardised API error handling."""
from __future__ import annotations

from functools import wraps
import logging
from typing import Any, Callable, TypeVar

from django.db import DatabaseError
from django.http import HttpRequest, JsonResponse

logger = logging.getLogger(__name__)
View = TypeVar("View", bound=Callable[..., JsonResponse])


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message


def success(data: Any, status: int = 200) -> JsonResponse:
    return JsonResponse({"ok": True, "data": data}, status=status)


def failure(code: str, message: str, status: int) -> JsonResponse:
    return JsonResponse(
        {"ok": False, "error": {"code": code, "message": message}},
        status=status,
    )


def csrf_failure(request: HttpRequest, reason: str = "") -> JsonResponse:
    del request, reason
    return failure("csrf_failed", "CSRF validation failed.", 403)


def api_errors(view: View) -> View:
    @wraps(view)
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        try:
            return view(request, *args, **kwargs)
        except ApiError as exc:
            return failure(exc.code, exc.message, exc.status)
        except DatabaseError:
            logger.exception("Database operation failed while handling %s", request.path)
            return failure("service_unavailable", "The database is temporarily unavailable.", 503)

    return wrapped  # type: ignore[return-value]
