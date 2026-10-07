"""Socket.IO real-time events (SQLite-backed)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import socketio
from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.db import DatabaseError

from .auth import cookie_token_from_header, user_from_token

logger = logging.getLogger(__name__)

socket_options: dict[str, Any] = {
    "async_mode": "asgi",
    "logger": False,
    "engineio_logger": False,
}
if settings.SOCKETIO_CORS_ORIGINS:
    socket_options["cors_allowed_origins"] = settings.SOCKETIO_CORS_ORIGINS
sio = socketio.AsyncServer(**socket_options)
_timer_task: asyncio.Task[None] | None = None


@sio.event
async def connect(sid: str, environ: dict[str, Any], auth: Any = None) -> bool:
    del auth
    token = cookie_token_from_header(environ.get("HTTP_COOKIE", ""))
    user = await sync_to_async(user_from_token)(token) if token else None
    if user is None:
        return False
    await sio.save_session(sid, {"role": user.role, "teamId": user.team_id})
    if user.role in {"admin", "volunteer"}:
        await sio.enter_room(sid, "admins")
    else:
        await sio.enter_room(sid, f"team:{user.team_id}")
    await _start_timer_broadcast()
    return True


async def _start_timer_broadcast() -> None:
    global _timer_task
    if _timer_task is None or _timer_task.done():
        _timer_task = asyncio.create_task(_broadcast_timer())


async def _broadcast_timer() -> None:
    from .models import Competition  # avoid circular import

    while True:
        try:
            competition = await sync_to_async(
                Competition.objects.filter(pk="current").first
            )()
            if competition and competition.status == "running":
                now = datetime.now(timezone.utc)
                ends_at = competition.spin_ends_at
                remaining = max(0, int((ends_at - now).total_seconds())) if ends_at else 0
                await sio.emit(
                    "timer_updated",
                    {
                        "spinNumber": competition.current_spin,
                        "spinEndsAt": ends_at.isoformat() if ends_at else None,
                        "remainingSeconds": remaining,
                    },
                )
        except DatabaseError:
            logger.exception("Socket.IO timer broadcast failed.")
        await asyncio.sleep(1)


def emit_event(event: str, data: dict[str, Any], room: str | None = None) -> None:
    async_to_sync(sio.emit)(event, data, room=room)
