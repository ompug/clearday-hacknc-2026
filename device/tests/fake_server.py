"""A tiny in-process stand-in for the Clearday API: Socket.IO plus three HTTP routes.

Runs python-socketio's threading server under the stdlib WSGI server
(long-polling transport only), so tests need no extra dependencies.
"""

from __future__ import annotations

import json
import threading
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

import socketio

TOKEN = "test-device-token"  # noqa: S105 - test fixture


class _ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


class FakeApi:
    def __init__(self) -> None:
        self.status: dict = {
            "weather": "clear",
            "open_bills": 1,
            "due_soon_bills": 1,
            "shares_paid": 2,
            "shares_total": 3,
        }
        self.http_up = True
        self.socket_up = True
        self.requests: list[tuple[str, str | None]] = []
        self.connected = threading.Event()
        # Short ping interval so long-poll requests return quickly after a rejected connect.
        self.sio = socketio.Server(
            async_mode="threading", allow_upgrades=False, ping_interval=1, ping_timeout=2
        )
        self.sio.on("connect", self._on_connect)
        self.app = socketio.WSGIApp(self.sio, self._http)
        self._server = make_server("127.0.0.1", 0, self.app, _ThreadingWSGIServer, _QuietHandler)
        self.url = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def _on_connect(self, sid, environ, auth):
        if not self.socket_up or not isinstance(auth, dict) or auth.get("token") != TOKEN:
            raise socketio.exceptions.ConnectionRefusedError("unauthorized")
        self.sio.enter_room(sid, "household:1")
        self.connected.set()

    def _http(self, environ, start_response):
        path = environ["PATH_INFO"]
        self.requests.append((path, environ.get("HTTP_AUTHORIZATION")))
        if not self.http_up:
            start_response("503 Service Unavailable", [("Content-Type", "text/plain")])
            return [b"down"]
        if environ.get("HTTP_AUTHORIZATION") != f"Bearer {TOKEN}":
            start_response("401 Unauthorized", [("Content-Type", "text/plain")])
            return [b"no"]
        if path == "/api/household/status":
            start_response("200 OK", [("Content-Type", "application/json")])
            return [json.dumps(self.status).encode()]
        if path.startswith("/api/device/"):
            start_response("200 OK", [("Content-Type", "audio/wav")])
            return [b"RIFF0000WAVE"]
        start_response("404 Not Found", [("Content-Type", "text/plain")])
        return [b"not found"]

    def emit(self, event: str, payload: dict) -> None:
        self.sio.emit(event, payload, room="household:1")

    def start(self) -> FakeApi:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
