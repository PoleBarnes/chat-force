"""Lightweight HTTP webhook server for receiving container signals."""

import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

log = logging.getLogger(__name__)


class WebhookServer:
    """Receives webhook callbacks from the Worker container.

    Listens for POST /hooks/after-turn (logged) and POST /hooks/task-complete
    (sets the completion event for the specific container).  Runs in a daemon
    thread so it won't block process shutdown.

    Completions are tracked **per container ID** so that multiple concurrent
    sessions don't interfere with each other.
    """

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._events: dict[str, threading.Event] = {}
        self._payloads: dict[str, dict] = {}
        self._lock = threading.Lock()
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

    def register(self, container_id: str) -> None:
        """Register a container for completion tracking."""
        with self._lock:
            self._events[container_id] = threading.Event()
            self._payloads.pop(container_id, None)

    def wait_for_completion(self, container_id: str | None = None, timeout: int = 300) -> bool:
        """Block until task-complete signal or *timeout* seconds elapse.

        If *container_id* is given, waits for that specific container's
        completion event.  If None (CLI mode / backward compat), waits for
        any registered container.

        Returns True if the signal was received, False on timeout.
        """
        if container_id is not None:
            event = self._events.get(container_id)
            if event is None:
                raise ValueError(f"Container {container_id} not registered")
            return event.wait(timeout=timeout)

        # Backward-compat: wait for any registered event (CLI single-container mode).
        with self._lock:
            events = list(self._events.values())
        if not events:
            # No containers registered — fall back to a bare event that never fires.
            return threading.Event().wait(timeout=timeout)
        # In CLI mode there's only one; wait on it.
        return events[0].wait(timeout=timeout)

    def reset(self, container_id: str | None = None) -> None:
        """Clear completion event(s) so we can wait again (for feedback loops).

        If *container_id* is given, resets only that container's state.
        If None (CLI mode / backward compat), resets ALL containers.
        """
        with self._lock:
            if container_id is not None:
                event = self._events.get(container_id)
                if event:
                    event.clear()
                self._payloads.pop(container_id, None)
            else:
                for event in self._events.values():
                    event.clear()
                self._payloads.clear()

    def unregister(self, container_id: str) -> None:
        """Remove a container from tracking."""
        with self._lock:
            self._events.pop(container_id, None)
            self._payloads.pop(container_id, None)

    def stop(self) -> None:
        """Shut down the HTTP server."""
        if self._server:
            self._server.shutdown()
            log.info("Webhook server stopped")

    def last_payload(self, container_id: str | None = None) -> dict | None:
        """Return the last payload for *container_id*, or any if None."""
        with self._lock:
            if container_id is not None:
                return self._payloads.get(container_id)
            # Backward compat: return the first available payload.
            for payload in self._payloads.values():
                return payload
            return None

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
                    container_id = payload.get("container_id", "")
                    log.info("Received task-complete signal (container: %s)", container_id[:12] or "unknown")

                    with server_ref._lock:
                        event = server_ref._events.get(container_id)
                        if event:
                            server_ref._payloads[container_id] = payload
                            event.set()
                        else:
                            # Try matching by hostname prefix — container IDs are
                            # 64 hex chars but the hostname inside the container
                            # is the first 12, so the payload may send a short ID.
                            matched = False
                            for cid, evt in server_ref._events.items():
                                if cid.startswith(container_id) or container_id.startswith(cid[:12]):
                                    server_ref._payloads[cid] = payload
                                    evt.set()
                                    matched = True
                                    break
                            if not matched:
                                log.warning(
                                    "task-complete for unknown container %s; "
                                    "registered: %s",
                                    container_id[:12],
                                    [c[:12] for c in server_ref._events],
                                )

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
