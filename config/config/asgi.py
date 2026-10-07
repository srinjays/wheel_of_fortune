"""ASGI entry point for Django HTTP APIs and Socket.IO."""

import os

from django.core.asgi import get_asgi_application
import socketio

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_application = get_asgi_application()

from game.core.sockets import sio  # noqa: E402

application = socketio.ASGIApp(
    sio,
    other_asgi_app=django_application,
    socketio_path="socket.io",
)
