"""Integration tests for Slack event routing through the Bolt middleware chain.

Simulates real Slack events using BoltRequest + app.dispatch() so we can
catch routing bugs (thread replies silently dropped, assistant handler not
firing, etc.) without needing a live Slack workspace.

Based on the patterns from slack-bolt's own test suite:
  https://github.com/slackapi/bolt-python/blob/main/tests/scenario_tests/test_events_assistant.py
"""

from __future__ import annotations

import json
import logging
import threading
import time
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
from queue import Queue
from unittest.mock import MagicMock, patch

import pytest
from slack_sdk.web import WebClient

from slack_bolt import App, BoltRequest

from pipeline.config import PipelineConfig

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Minimal mock web API server
# ---------------------------------------------------------------------------
# Bolt calls auth.test on startup and various API methods (chat.postMessage,
# conversations.history, etc.) during handler execution.  This mock returns
# {"ok": true} for everything so the middleware chain doesn't abort.

_AUTH_TEST_RESPONSE = json.dumps({
    "ok": True,
    "url": "https://test.slack.com/",
    "team": "Test Workspace",
    "user": "bot",
    "team_id": "T111",
    "user_id": "W111",
    "bot_id": "B111",
})

_OK_RESPONSE = json.dumps({"ok": True, "messages": [], "channel": "D111", "ts": "9999.0000"})


class _MockSlackHandler(SimpleHTTPRequestHandler):
    """Return canned OK responses for every Slack API call."""

    protocol_version = "HTTP/1.1"

    def do_POST(self):
        self._respond()

    def do_GET(self):
        self._respond()

    def _respond(self):
        if self.path.startswith("/auth.test"):
            body = _AUTH_TEST_RESPONSE
        else:
            body = _OK_RESPONSE
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", "application/json;charset=utf-8")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    # Suppress request logging noise in test output.
    def log_message(self, format, *args):
        pass


class _MockServer:
    """Start/stop a mock Slack API HTTP server on a background thread."""

    def __init__(self, port: int = 8899):
        self.port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._started = threading.Event()

    def start(self):
        self._server = HTTPServer(("localhost", self.port), _MockSlackHandler)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._started.wait(timeout=5)

    def _run(self):
        self._started.set()
        self._server.serve_forever(poll_interval=0.05)

    def stop(self):
        if self._server:
            self._server.shutdown()
        if self._thread:
            self._thread.join(timeout=5)


# ---------------------------------------------------------------------------
# Payload factories
# ---------------------------------------------------------------------------

def _build_envelope(event: dict) -> dict:
    """Wrap an event dict in the standard Slack event_callback envelope."""
    return {
        "token": "verification_token",
        "team_id": "T111",
        "enterprise_id": "E111",
        "api_app_id": "A111",
        "event": event,
        "type": "event_callback",
        "event_id": "Ev111",
        "event_time": 1599616881,
        "authorizations": [
            {
                "enterprise_id": "E111",
                "team_id": "T111",
                "user_id": "W111",
                "is_bot": True,
                "is_enterprise_install": False,
            }
        ],
    }


def make_assistant_thread_started(
    user_id: str = "U222",
    channel_id: str = "D111",
    thread_ts: str = "1234.5678",
) -> dict:
    """Simulate opening the assistant panel (DM thread)."""
    return _build_envelope({
        "type": "assistant_thread_started",
        "assistant_thread": {
            "user_id": user_id,
            "context": {"channel_id": "C222", "team_id": "T111", "enterprise_id": "E111"},
            "channel_id": channel_id,
            "thread_ts": thread_ts,
        },
        "event_ts": thread_ts,
    })


def make_dm_message(
    user_id: str = "U222",
    channel_id: str = "D111",
    text: str = "hello",
    thread_ts: str = "1234.5678",
    ts: str | None = None,
) -> dict:
    """Simulate a user DM in an assistant thread."""
    return _build_envelope({
        "user": user_id,
        "type": "message",
        "ts": ts or str(float(thread_ts) + 1),
        "text": text,
        "team": "T111",
        "user_team": "T111",
        "source_team": "T111",
        "user_profile": {},
        "thread_ts": thread_ts,
        "parent_user_id": user_id,
        "channel": channel_id,
        "event_ts": ts or str(float(thread_ts) + 1),
        "channel_type": "im",
    })


def make_channel_mention(
    user_id: str = "U222",
    channel_id: str = "C111",
    text: str = "<@W111> do something",
    ts: str = "1234.5678",
) -> dict:
    """Simulate an @mention of the bot in a channel."""
    return _build_envelope({
        "type": "app_mention",
        "user": user_id,
        "text": text,
        "ts": ts,
        "event_ts": ts,
        "channel": channel_id,
        "team": "T111",
    })


def make_thread_reply(
    user_id: str = "U222",
    channel_id: str = "C111",
    text: str = "follow up",
    thread_ts: str = "1234.5678",
    ts: str = "1234.9999",
) -> dict:
    """Simulate a reply in an existing channel thread (no @mention)."""
    return _build_envelope({
        "user": user_id,
        "type": "message",
        "ts": ts,
        "text": text,
        "team": "T111",
        "thread_ts": thread_ts,
        "parent_user_id": user_id,
        "channel": channel_id,
        "event_ts": ts,
        "channel_type": "channel",
    })


def make_bot_message(
    channel_id: str = "C111",
    text: str = "bot says hi",
    bot_id: str = "B111",
    ts: str = "1234.5678",
) -> dict:
    """Simulate a message from a bot (should be ignored)."""
    return _build_envelope({
        "type": "message",
        "subtype": "bot_message",
        "text": text,
        "ts": ts,
        "event_ts": ts,
        "bot_id": bot_id,
        "channel": channel_id,
        "channel_type": "channel",
    })


def make_channel_root_message(
    user_id: str = "U222",
    channel_id: str = "C111",
    text: str = "just chatting",
    ts: str = "1234.5678",
) -> dict:
    """Simulate a plain channel message -- no thread, no mention."""
    return _build_envelope({
        "user": user_id,
        "type": "message",
        "ts": ts,
        "text": text,
        "team": "T111",
        "channel": channel_id,
        "event_ts": ts,
        "channel_type": "channel",
    })


# ---------------------------------------------------------------------------
# Mock session / session manager factory
# ---------------------------------------------------------------------------

def _make_mock_session(sandbox_version: str = "abc1234") -> MagicMock:
    """Return a MagicMock that behaves like a Session."""
    session = MagicMock()
    session.sandbox_version = sandbox_version
    session.run_id = "test-run-001"
    session.user_id = "U222"
    session.channel_id = "D111"
    session.message_count = 1
    session.worker = MagicMock()
    session.worker.get_response.return_value = "Here is your response"
    session.worker.is_alive.return_value = True
    return session


def _make_mock_session_manager() -> MagicMock:
    """Return a MagicMock that behaves like SessionManager."""
    sm = MagicMock()
    sm.get_session.return_value = None  # no existing session by default
    mock_session = _make_mock_session()
    sm.get_or_create_session.return_value = (mock_session, True)
    sm.send_message.return_value = "Follow-up response"
    sm.on_session_closed = None
    return sm


# ---------------------------------------------------------------------------
# Fixture: module-scoped mock server
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mock_server():
    """Start a mock Slack API server for the entire test module."""
    server = _MockServer(port=8899)
    server.start()
    yield server
    server.stop()


@pytest.fixture()
def web_client(mock_server):
    """Return a WebClient pointed at the mock server."""
    return WebClient(token="xoxb-valid", base_url="http://localhost:8899")


@pytest.fixture()
def mock_session_manager():
    """Return a fresh mock SessionManager for each test."""
    return _make_mock_session_manager()


@pytest.fixture()
def app_and_sm(web_client, mock_session_manager, config_with_harness):
    """Create a Bolt App wired to the mock session manager.

    Instead of calling create_app() against the live Slack API, we replicate
    the handler registration
    using an App(client=web_client) -- the same pattern Bolt's own
    test suite uses.  The mock session_manager is injected directly.
    """
    import pipeline.slack_listener as sl

    # Patch module-level state.
    orig_has_chunks = sl._HAS_CHUNKS
    orig_cached = sl._cached_team_id
    sl._HAS_CHUNKS = False
    sl._cached_team_id = None

    try:
        # Build the App with the test web_client (avoids real auth.test).
        app = App(client=web_client)

        # Replicate create_app()'s handler registration, but with our
        # mock session manager wired in instead of a real one.
        # We monkey-patch the module-level reference that create_app's
        # closures capture by re-importing create_app with patches.
        with patch.object(sl, "SessionManager", return_value=mock_session_manager):
            with patch.dict(
                "os.environ",
                {config_with_harness.harness.bot_token_env: "xoxb-valid"},
            ):
                # We need create_app to register handlers on *our* app,
                # so patch App() to return our pre-built app.
                original_app_init = App.__init__

                def patched_init(self_app, *args, **kwargs):
                    """Intercept App() inside create_app and return our app."""
                    # Copy our pre-configured app's state into self_app.
                    # But it's cleaner to just let it initialize normally
                    # with the client.
                    return original_app_init(self_app, client=web_client)

                with patch.object(App, "__init__", patched_init):
                    app, _ = sl.create_app(config_with_harness)

        yield app, mock_session_manager
    finally:
        sl._HAS_CHUNKS = orig_has_chunks
        sl._cached_team_id = orig_cached


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAssistantThreadStarted:
    """Test 1: assistant_thread_started fires the greeting handler."""

    def test_thread_started_returns_200(self, app_and_sm):
        app, sm = app_and_sm
        payload = make_assistant_thread_started()
        request = BoltRequest(body=payload, mode="socket_mode")
        response = app.dispatch(request)

        assert response.status == 200

    def test_thread_started_fires_handler(self, app_and_sm):
        """The greeting handler should be invoked by the Assistant class."""
        app, sm = app_and_sm
        payload = make_assistant_thread_started()
        request = BoltRequest(body=payload, mode="socket_mode")
        response = app.dispatch(request)

        assert response.status == 200
        # Give the background listener thread time to complete.
        time.sleep(0.3)
        # The handler calls say() with the greeting -- the mock server
        # handles the API call.  We mainly verify no 500 / crash.


class TestDMMessageRouting:
    """Test 2: DM message routes through assistant.user_message."""

    def test_dm_message_calls_session_manager(self, app_and_sm):
        app, sm = app_and_sm
        payload = make_dm_message(text="Build me a REST API")
        request = BoltRequest(body=payload, mode="socket_mode")
        response = app.dispatch(request)

        assert response.status == 200
        # Wait for the background thread to execute the handler.
        time.sleep(0.5)

        # The handler should have called get_session (fast path check)
        # and then get_or_create_session (new session).
        assert sm.get_session.called or sm.get_or_create_session.called

    def test_dm_followup_uses_existing_session(self, app_and_sm):
        """When a session exists, DM should use send_message (not create new)."""
        app, sm = app_and_sm
        existing_session = _make_mock_session()
        sm.get_session.return_value = existing_session

        payload = make_dm_message(text="Now add tests")
        request = BoltRequest(body=payload, mode="socket_mode")
        response = app.dispatch(request)

        assert response.status == 200
        time.sleep(0.5)

        sm.get_session.assert_called()
        # Since an existing session was found, send_message should NOT
        # have been called on the session_manager directly -- the handler
        # calls session_manager.send_message(existing, text).
        sm.send_message.assert_called_once()


class TestChannelMention:
    """Test 3: @mention in channel routes through handle_mention."""

    def test_mention_calls_session_manager(self, app_and_sm):
        app, sm = app_and_sm
        payload = make_channel_mention(text="<@W111> build a scraper")
        request = BoltRequest(body=payload, mode="socket_mode")
        response = app.dispatch(request)

        assert response.status == 200
        time.sleep(0.5)

        # The mention handler should have checked for existing session
        # and then created a new one.
        assert sm.get_session.called or sm.get_or_create_session.called

    def test_empty_mention_sends_help(self, app_and_sm):
        """An @mention with no text after the bot name should reply with help."""
        app, sm = app_and_sm
        payload = make_channel_mention(text="<@W111>")
        request = BoltRequest(body=payload, mode="socket_mode")
        response = app.dispatch(request)

        assert response.status == 200
        time.sleep(0.3)

        # Empty text should NOT create a session.
        sm.get_or_create_session.assert_not_called()


class TestThreadReplyRouting:
    """Test 4: Thread replies without @mention.

    THIS IS THE BUG AREA -- thread replies in channels were being silently
    eaten by the catch-all message handler instead of reaching the session
    manager.

    NOTE: The current implementation has a catch-all `@app.event("message")`
    that intentionally drops channel messages.  Thread replies in channels
    only reach the session manager if the user @mentions the bot again, or
    if the thread is a DM/assistant thread (handled by the Assistant class).

    This test documents the current behavior so we can detect regressions
    and know exactly what changes when we add thread-reply routing.
    """

    def test_channel_thread_reply_is_handled(self, app_and_sm):
        """A channel thread reply (no mention) hits the catch-all handler.

        Currently this means the message is logged and dropped.  This test
        ensures it at least doesn't crash (returns 200).
        """
        app, sm = app_and_sm
        payload = make_thread_reply(
            text="follow up on that",
            thread_ts="1234.5678",
            ts="1234.9999",
        )
        request = BoltRequest(body=payload, mode="socket_mode")
        response = app.dispatch(request)

        assert response.status == 200
        time.sleep(0.3)

        # Document the current (buggy) behavior: the catch-all eats the
        # message, so the session manager is never called.
        # When we fix this, flip this assertion.
        sm.send_message.assert_not_called()

    def test_dm_thread_reply_routes_to_assistant(self, app_and_sm):
        """A DM thread reply (im channel_type) should route through
        the Assistant.user_message handler and reach the session manager.
        """
        app, sm = app_and_sm
        # Set up an existing session so the handler takes the fast path.
        existing_session = _make_mock_session()
        sm.get_session.return_value = existing_session

        # First message in the thread.
        payload1 = make_dm_message(
            text="Build me an API",
            thread_ts="5000.0001",
            ts="5000.0002",
        )
        request1 = BoltRequest(body=payload1, mode="socket_mode")
        response1 = app.dispatch(request1)
        assert response1.status == 200
        time.sleep(0.3)

        # Follow-up message in the same thread.
        payload2 = make_dm_message(
            text="Now add authentication",
            thread_ts="5000.0001",
            ts="5000.0003",
        )
        request2 = BoltRequest(body=payload2, mode="socket_mode")
        response2 = app.dispatch(request2)
        assert response2.status == 200
        time.sleep(0.5)

        # Both messages should have reached the session manager.
        assert sm.send_message.call_count >= 2


class TestBotMessageIgnored:
    """Test 5: Bot messages should be ignored."""

    def test_bot_message_no_session_calls(self, app_and_sm):
        app, sm = app_and_sm
        payload = make_bot_message(text="I am a bot")
        request = BoltRequest(body=payload, mode="socket_mode")
        response = app.dispatch(request)

        # Bolt returns 200 for handled events (catch-all picks it up).
        assert response.status == 200
        time.sleep(0.3)

        sm.get_session.assert_not_called()
        sm.get_or_create_session.assert_not_called()
        sm.send_message.assert_not_called()


class TestChannelRootMessageIgnored:
    """Test 6: Plain channel messages (no thread, no mention) are ignored."""

    def test_root_message_no_session_calls(self, app_and_sm):
        app, sm = app_and_sm
        payload = make_channel_root_message(text="just chatting")
        request = BoltRequest(body=payload, mode="socket_mode")
        response = app.dispatch(request)

        assert response.status == 200
        time.sleep(0.3)

        sm.get_session.assert_not_called()
        sm.get_or_create_session.assert_not_called()
        sm.send_message.assert_not_called()


class TestSessionReuse:
    """Test 7: Multiple messages from the same user reuse the session."""

    def test_second_message_reuses_session(self, app_and_sm):
        app, sm = app_and_sm

        # First call: no existing session -> create.
        sm.get_session.return_value = None
        mock_session = _make_mock_session()
        sm.get_or_create_session.return_value = (mock_session, True)

        payload1 = make_dm_message(text="First message", ts="6000.0001")
        request1 = BoltRequest(body=payload1, mode="socket_mode")
        response1 = app.dispatch(request1)
        assert response1.status == 200
        time.sleep(0.5)

        # After the first message, simulate get_session returning the session.
        sm.get_session.return_value = mock_session
        sm.get_or_create_session.reset_mock()

        payload2 = make_dm_message(text="Second message", ts="6000.0002")
        request2 = BoltRequest(body=payload2, mode="socket_mode")
        response2 = app.dispatch(request2)
        assert response2.status == 200
        time.sleep(0.5)

        # The second message should have used the existing session.
        sm.get_or_create_session.assert_not_called()
        sm.send_message.assert_called()


class TestErrorHandling:
    """Test 8: Handler errors don't crash the listener."""

    def test_session_creation_error_returns_200(self, app_and_sm):
        """If get_or_create_session raises, the handler catches it and
        responds gracefully instead of crashing Bolt."""
        app, sm = app_and_sm
        sm.get_session.return_value = None
        sm.get_or_create_session.side_effect = RuntimeError("Docker exploded")

        payload = make_dm_message(text="This will fail")
        request = BoltRequest(body=payload, mode="socket_mode")
        response = app.dispatch(request)

        # Bolt should still return 200 -- error is handled inside the listener.
        assert response.status == 200
        time.sleep(0.5)

    def test_send_message_timeout_returns_200(self, app_and_sm):
        """If send_message raises TimeoutError, handler catches it."""
        app, sm = app_and_sm
        existing_session = _make_mock_session()
        sm.get_session.return_value = existing_session
        sm.send_message.side_effect = TimeoutError("Worker timed out")

        payload = make_dm_message(text="This will timeout")
        request = BoltRequest(body=payload, mode="socket_mode")
        response = app.dispatch(request)

        assert response.status == 200
        time.sleep(0.5)

    def test_send_message_runtime_error_returns_200(self, app_and_sm):
        """If send_message raises RuntimeError, handler catches it."""
        app, sm = app_and_sm
        existing_session = _make_mock_session()
        sm.get_session.return_value = existing_session
        sm.send_message.side_effect = RuntimeError("Container died")

        payload = make_dm_message(text="This will error")
        request = BoltRequest(body=payload, mode="socket_mode")
        response = app.dispatch(request)

        assert response.status == 200
        time.sleep(0.5)

    def test_mention_handler_error_returns_200(self, app_and_sm):
        """If the mention handler hits an unhandled error, Bolt still returns 200."""
        app, sm = app_and_sm
        sm.get_session.return_value = None
        sm.get_or_create_session.side_effect = Exception("Unexpected failure")

        payload = make_channel_mention(text="<@W111> do something")
        request = BoltRequest(body=payload, mode="socket_mode")
        response = app.dispatch(request)

        assert response.status == 200
        time.sleep(0.5)


class TestMentionWithExistingSession:
    """Channel @mention when a session already exists."""

    def test_mention_with_existing_session_sends_message(self, app_and_sm):
        app, sm = app_and_sm
        existing_session = _make_mock_session()
        sm.get_session.return_value = existing_session

        payload = make_channel_mention(text="<@W111> do more stuff")
        request = BoltRequest(body=payload, mode="socket_mode")
        response = app.dispatch(request)

        assert response.status == 200
        time.sleep(0.5)

        sm.send_message.assert_called_once()
        call_args = sm.send_message.call_args
        assert call_args[0][0] is existing_session
        assert call_args[0][1] == "do more stuff"


class TestEmptyMessageIgnored:
    """DM with empty text should be silently ignored."""

    def test_empty_dm_no_session_created(self, app_and_sm):
        app, sm = app_and_sm
        payload = make_dm_message(text="   ")
        request = BoltRequest(body=payload, mode="socket_mode")
        response = app.dispatch(request)

        assert response.status == 200
        time.sleep(0.3)

        # Empty text should bail out early -- no session creation.
        sm.get_or_create_session.assert_not_called()
