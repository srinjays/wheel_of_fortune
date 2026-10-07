"""Core views: health check and CSRF token."""
from __future__ import annotations

from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie

from .errors import api_errors, success
from .http import api_methods


@api_errors
@api_methods("GET")
def health(_request: HttpRequest) -> JsonResponse:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return success({"status": "ok", "database": "connected"})


@ensure_csrf_cookie
@api_methods("GET")
def csrf_token(request: HttpRequest) -> JsonResponse:
    return success({"csrfToken": get_token(request)})
