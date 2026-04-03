"""Lightweight HTTP webhook server for receiving container signals."""

import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

log = logging.getLogger(__name__)


class WebhookServer:
    """Receives webhook callbacks from the Worker container.

    Listens for POST /hooks/after-turn (logged) and POST /hooks/task-complete
    (sets the completion event).  Runs in a daemon thread so it won't block
    process shutdown.
    """

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._completion_event = threading.Event()
        self._last_payload: dict | None = None
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    # -- public API -----------------------------------------------------------

    def start(self) -> None:
        """Start the webhook server in a background daemon thread."""
        handler = self._make_handler()
        self._server = HTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="webhook-server",
        )
        self._thread.start()
        log.info("Webhook server listening on %s:%s", self.host, self.port)

    def wait_for_completion(self, timeout: int) -> bool:
        """Block until task-complete signal or *timeout* seconds elapse.

        Returns True if the signal was received, False on timeout.
        """
        return self._completion_event.wait(timeout=timeout)

    def reset(self) -> None:
        """Clear the completion event so we can wait again (for feedback loops)."""
        self._completion_event.clear()
        self._last_payload = None

    def stop(self) -> None:
        """Shut down the HTTP server."""
        if self._server:
            self._server.shutdown()
            log.info("Webhook server stopped")

    @property
    def last_payload(self) -> dict | None:
        return self._last_payload

    # -- internals ------------------------------------------------------------

    def _make_handler(self):
        """Build a request handler class that closes over *self*."""
        server_ref = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length) if content_length else b"{}"
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError:
                    payload = {}

                if self.path == "/hooks/task-complete":
                    log.info("Received task-complete signal")
                    server_ref._last_payload = payload
                    server_ref._completion_event.set()
                    self._respond(200, {"status": "accepted"})

                elif self.path == "/hooks/after-turn":
                    log.debug("Received after-turn signal: %s", payload)
                    self._respond(200, {"status": "acknowledged"})

                else:
                    log.warning("Unknown webhook path: %s", self.path)
                    self._respond(404, {"error": "not found"})

            def _respond(self, code: int, body: dict):
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())

            def log_message(self, format, *args):  # noqa: A002
                """Route stdlib HTTP logs through our logger."""
                log.debug(format, *args)

        return _Handler
