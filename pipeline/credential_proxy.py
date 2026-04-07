"""Host-side reverse proxy that injects API credentials into outbound requests.

The Worker container runs with ``--network none`` (future) or with
``ANTHROPIC_BASE_URL`` pointed at this proxy. The container never holds
real API keys — it sends requests with a placeholder key, and this proxy
replaces it with the real credential before forwarding to the upstream API.

This is the foundational security primitive for the chat-force engine.
All future API service integrations (Firecrawl, Serper, etc.) will route
through this proxy, which holds the keys and enforces the domain allowlist.

Usage::

    from pipeline.credential_proxy import CredentialProxy

    proxy = CredentialProxy(
        port=8082,
        credentials={
            "api.anthropic.com": os.environ["CLAUDE_CODE_OAUTH_TOKEN"],
        },
    )
    proxy.start()   # background thread
    # ... Worker containers use ANTHROPIC_BASE_URL=http://host.docker.internal:8082
    proxy.stop()

Architecture::

    Worker container
        ↓ HTTP request (Authorization: Bearer sk-proxy-placeholder)
    CredentialProxy (host, port 8082)
        ↓ replaces Authorization header with real key
    api.anthropic.com
"""

from __future__ import annotations

import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import URLError

log = logging.getLogger(__name__)

# Placeholder key that the Worker container uses. The proxy recognizes
# and replaces it. If the Worker somehow sends a request with this key
# directly to the real API, it will be rejected (it's not a real key).
PROXY_PLACEHOLDER_KEY = "sk-proxy-placeholder-do-not-use-directly"

# Default upstream for Claude API requests.
_DEFAULT_UPSTREAM = "https://api.anthropic.com"


class _ProxyHandler(BaseHTTPRequestHandler):
    """HTTP handler that forwards requests with injected credentials."""

    # Set by the server instance at startup.
    upstream_url: str = _DEFAULT_UPSTREAM
    real_credential: str = ""

    def do_POST(self):
        """Forward POST requests (the only method the Claude API uses)."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b""

            # Build the upstream URL.
            upstream = f"{self.upstream_url}{self.path}"

            # Forward all headers except Host (which we rewrite) and
            # Authorization (which we replace).
            headers = {}
            for key, value in self.headers.items():
                lower = key.lower()
                if lower in ("host", "authorization"):
                    continue
                headers[key] = value

            # Inject the real credential.
            if self.real_credential:
                headers["Authorization"] = f"Bearer {self.real_credential}"
                headers["x-api-key"] = self.real_credential

            req = Request(
                upstream,
                data=body,
                headers=headers,
                method="POST",
            )

            with urlopen(req, timeout=120) as resp:
                resp_body = resp.read()
                self.send_response(resp.status)
                for key, value in resp.getheaders():
                    if key.lower() not in ("transfer-encoding", "connection"):
                        self.send_header(key, value)
                self.end_headers()
                self.wfile.write(resp_body)

        except URLError as exc:
            log.warning("Proxy upstream error: %s", exc)
            self.send_error(502, f"Upstream error: {exc}")
        except Exception as exc:
            log.error("Proxy handler error: %s", exc, exc_info=True)
            self.send_error(500, "Internal proxy error")

    def do_GET(self):
        """Health check endpoint."""
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_error(405, "Only POST and /health GET are supported")

    def log_message(self, format, *args):
        """Route HTTP server logs through the standard logger."""
        log.debug("Proxy: %s", format % args)


class CredentialProxy:
    """Host-side reverse proxy that injects API credentials.

    Runs in a background daemon thread. Start with ``start()``, stop
    with ``stop()``.
    """

    def __init__(
        self,
        port: int = 8082,
        credential: str = "",
        upstream_url: str = _DEFAULT_UPSTREAM,
    ):
        self.port = port
        self.credential = credential
        self.upstream_url = upstream_url
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the proxy in a background thread."""
        handler = type(
            "_ConfiguredHandler",
            (_ProxyHandler,),
            {
                "upstream_url": self.upstream_url,
                "real_credential": self.credential,
            },
        )

        self._server = HTTPServer(("0.0.0.0", self.port), handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="credential-proxy",
        )
        self._thread.start()
        log.info(
            "Credential proxy started on port %d (upstream: %s)",
            self.port,
            self.upstream_url,
        )

    def stop(self) -> None:
        """Stop the proxy."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        log.info("Credential proxy stopped")

    @property
    def base_url(self) -> str:
        """The URL that Worker containers should use as ANTHROPIC_BASE_URL."""
        return f"http://host.docker.internal:{self.port}"
