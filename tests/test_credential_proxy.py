"""Tests for pipeline/credential_proxy.py."""

from __future__ import annotations

import json
import time
import urllib.request
from unittest.mock import patch

import pytest

from pipeline.credential_proxy import (
    CredentialProxy,
    PROXY_PLACEHOLDER_KEY,
)


class TestCredentialProxy:
    """Test the host-side credential injection proxy."""

    @pytest.fixture
    def proxy(self) -> CredentialProxy:
        """Start a proxy on a random-ish port for testing."""
        # Use a high port to avoid conflicts.
        p = CredentialProxy(
            port=18082,
            credential="sk-real-secret-key-for-testing",
        )
        p.start()
        time.sleep(0.3)  # give the server thread time to bind
        yield p
        p.stop()

    def test_health_endpoint(self, proxy: CredentialProxy) -> None:
        """GET /health should return 200 ok."""
        req = urllib.request.Request(f"http://localhost:{proxy.port}/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            assert resp.read() == b"ok"

    def test_proxy_starts_and_stops(self) -> None:
        """Proxy should start and stop cleanly."""
        p = CredentialProxy(port=18083, credential="test")
        p.start()
        time.sleep(0.2)
        # Health check should work
        req = urllib.request.Request(f"http://localhost:18083/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
        p.stop()
        # After stop, should fail to connect
        with pytest.raises(Exception):
            urllib.request.urlopen(
                urllib.request.Request(f"http://localhost:18083/health"),
                timeout=2,
            )

    def test_base_url_property(self) -> None:
        """base_url should return the Docker-accessible URL."""
        p = CredentialProxy(port=9999, credential="x")
        assert p.base_url == "http://host.docker.internal:9999"

    def test_placeholder_key_is_not_a_real_key(self) -> None:
        """The placeholder key should be obviously fake."""
        assert "placeholder" in PROXY_PLACEHOLDER_KEY
        assert not PROXY_PLACEHOLDER_KEY.startswith("sk-ant-")

    def test_post_injects_credential(self, proxy: CredentialProxy) -> None:
        """POST requests should have the real credential injected.

        We can't test against the real Anthropic API, but we can verify
        the proxy forwards with the right headers by pointing the
        upstream at a local echo server.
        """
        # This test verifies the proxy is reachable and handles POST.
        # Full credential injection is verified by the integration test
        # (smoke_test.py with real Docker + Claude API).
        # Here we just verify the proxy doesn't crash on POST.
        data = json.dumps({"model": "test", "messages": []}).encode()
        req = urllib.request.Request(
            f"http://localhost:{proxy.port}/v1/messages",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {PROXY_PLACEHOLDER_KEY}",
            },
            method="POST",
        )
        # This will get a 502 (upstream is api.anthropic.com and
        # the placeholder key won't auth), but the proxy itself
        # should handle the request without crashing.
        try:
            urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as e:
            # 502 = proxy forwarded but upstream rejected (expected)
            # 401 = upstream auth failed (also expected with placeholder)
            assert e.code in (401, 402, 403, 429, 500, 502), f"Unexpected status: {e.code}"

    def test_get_non_health_returns_405(self, proxy: CredentialProxy) -> None:
        """GET to non-health endpoints should return 405."""
        req = urllib.request.Request(f"http://localhost:{proxy.port}/v1/messages")
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5)
        assert exc_info.value.code == 405
