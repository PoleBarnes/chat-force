"""Slack socket-mode listener for Leo.

Connects to Slack, routes messages to the session manager,
and posts Leo's responses back to channels.

Usage::

    doppler run -p chat-force -c dev -- \\
        uv run --python 3.13 --with docker,slack_sdk,slack_bolt \\
        python -m pipeline.slack_listener
"""

from __future__ import annotations

import logging
import os
import re
import signal
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from pipeline.config import PipelineConfig
from pipeline.session_manager import Session, SessionManager

if TYPE_CHECKING:
    from slack_sdk import WebClient

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Channel history helper
# ---------------------------------------------------------------------------


def _read_channel_history(client: WebClient, channel_id: str, limit: int = 20) -> str:
    """Read recent messages from a Slack channel for session context.

    Returns a formatted string of recent conversation, or an empty string
    if nothing useful is available.
    """
    try:
        result = client.conversations_history(channel=channel_id, limit=limit)
    except Exception:
        log.warning("Could not read channel history for %s", channel_id, exc_info=True)
        return ""

    messages = result.get("messages", [])
    if not messages:
        return ""

    # Messages arrive newest-first; reverse to chronological order.
    messages = list(reversed(messages))

    lines: list[str] = []
    for msg in messages:
        # Skip bot status messages (our own session announcements, etc.)
        if msg.get("bot_id") or msg.get("subtype"):
            continue

        user = msg.get("user", "unknown")
        text = msg.get("text", "")
        ts = msg.get("ts", "")

        # Convert Slack epoch timestamp to human-readable form.
        try:
            dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
            formatted_ts = dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError, OSError):
            formatted_ts = ts

        lines.append(f"[{formatted_ts}] {user}: {text}")

    if not lines:
        return ""

    return "Recent conversation history (for context):\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Session-closed callback (Mechanic results -> Slack)
# ---------------------------------------------------------------------------


def _make_session_closed_callback(client: WebClient):
    """Return a callback that posts Mechanic results back to Slack.

    The returned function is meant to be called by the session manager's
    idle-checker when a session is closed and the Mechanic phase completes.
    """

    def on_session_closed(session: Session, result: dict | None) -> None:
        if result is None:
            return

        channel = session.channel_id
        status = result.get("status")

        try:
            if status == "approved":
                pr_url = result.get("pr_url", "")
                client.chat_postMessage(
                    channel=channel,
                    text=f"\u2705 Changes approved \u2014 PR created: {pr_url}",
                )

            elif status == "linear_proposed":
                proposal = result.get("linear_proposal", {})
                reason = proposal.get("reason", "")
                client.chat_postMessage(
                    channel=channel,
                    text=(
                        f"\U0001f4a1 Findings worth tracking:\n{reason}\n\n"
                        "React \u2705 to create a Linear issue, or \u274c to skip."
                    ),
                )

            elif status == "rejected":
                verdict = result.get("verdict") or {}
                reason = verdict.get("reason", "Unknown")
                client.chat_postMessage(
                    channel=channel,
                    text=f"\U0001f50d Session analyzed \u2014 no changes kept. {reason[:200]}",
                )

            elif status == "error":
                error = result.get("error", "Unknown error")
                client.chat_postMessage(
                    channel=channel,
                    text=f"\u26a0\ufe0f Session closed with error: {error[:300]}",
                )

            # "no_changes" -- say nothing

        except Exception:
            log.warning(
                "Could not post session-close notification to %s",
                channel,
                exc_info=True,
            )

    return on_session_closed


# ---------------------------------------------------------------------------
# Live status helpers
# ---------------------------------------------------------------------------


def _set_presence(client: WebClient, presence: str) -> None:
    """Set bot presence to 'auto' (online/idle) or 'away'."""
    try:
        client.users_setPresence(presence=presence)
    except Exception:
        log.debug("Could not set presence to %s", presence, exc_info=True)


def _has_streaming(client: WebClient) -> bool:
    """Check if the Slack client supports the modern streaming APIs."""
    return hasattr(client, "chat_startStream")


def _has_assistant_threads(client: WebClient) -> bool:
    """Check if the Slack client supports assistant.threads.setStatus."""
    return hasattr(client, "assistant_threads_setStatus")


# -- Fallback helpers (classic chat.postMessage + chat.update) --------------


def _post_status(
    client: WebClient, channel: str, text: str, *, thread_ts: str | None = None,
) -> str:
    """Post a new status message. Returns its ts for later updates."""
    resp = client.chat_postMessage(channel=channel, text=text, thread_ts=thread_ts)
    return resp["ts"]


def _update_status(client: WebClient, channel: str, ts: str, text: str) -> None:
    """Update an existing message in-place (live progress effect)."""
    try:
        client.chat_update(channel=channel, ts=ts, text=text)
    except Exception:
        log.debug("Could not update status message", exc_info=True)


# -- Streaming helpers (modern chat.startStream / appendStream / stopStream) -


def _set_thread_status(
    client: WebClient,
    channel: str,
    thread_ts: str,
    status: str,
    *,
    loading_messages: list[str] | None = None,
) -> None:
    """Set the assistant thread typing indicator / status text.

    Uses assistant.threads.setStatus when available, otherwise no-op.

    Pass *loading_messages* to override Slack's default rotating status
    strings (e.g. "evaluating", "searching").  An empty list disables
    the rotation entirely so only *status* is shown.
    """
    if _has_assistant_threads(client):
        try:
            kwargs: dict = {
                "channel_id": channel,
                "thread_ts": thread_ts,
                "status": status,
            }
            if loading_messages is not None:
                kwargs["loading_messages"] = loading_messages
            client.assistant_threads_setStatus(**kwargs)
        except Exception:
            log.debug("assistant_threads_setStatus failed", exc_info=True)


def _stream_response(
    client: WebClient, channel: str, text: str, *, thread_ts: str | None = None,
) -> None:
    """Stream a response using chat.startStream / appendStream / stopStream.

    Falls back to a plain chat.postMessage if streaming APIs are unavailable.
    """
    if not _has_streaming(client):
        client.chat_postMessage(channel=channel, text=text, thread_ts=thread_ts)
        return

    try:
        stream_result = client.chat_startStream(
            channel=channel,
            thread_ts=thread_ts,
        )
        stream_channel = stream_result["channel"]
        stream_ts = stream_result["ts"]

        client.chat_appendStream(
            channel=stream_channel,
            ts=stream_ts,
            markdown_text=text,
        )

        client.chat_stopStream(
            channel=stream_channel,
            ts=stream_ts,
        )
    except Exception:
        # If streaming fails mid-flight, fall back to a regular message.
        log.warning("Streaming failed, falling back to chat.postMessage", exc_info=True)
        client.chat_postMessage(channel=channel, text=text, thread_ts=thread_ts)


# ---------------------------------------------------------------------------
# Event deduplication (app_mention + message double-fire)
# ---------------------------------------------------------------------------

# Slack fires both `message` and `app_mention` for @-mentions.  We track
# recently-handled event timestamps so only the first handler runs.
_seen_events: dict[str, float] = {}   # event_ts -> wall-clock time
_seen_events_lock = threading.Lock()
_SEEN_EVENT_TTL = 60  # seconds to remember an event


def _is_duplicate_event(event_ts: str) -> bool:
    """Return True if this event_ts was already processed recently."""
    now = time.monotonic()

    with _seen_events_lock:
        # Periodic purge of stale entries.
        stale = [ts for ts, t in _seen_events.items() if now - t > _SEEN_EVENT_TTL]
        for ts in stale:
            del _seen_events[ts]

        if event_ts in _seen_events:
            return True
        _seen_events[event_ts] = now
        return False


# ---------------------------------------------------------------------------
# Core message routing
# ---------------------------------------------------------------------------


def _handle_user_message(
    user_id: str,
    channel_id: str,
    text: str,
    say,
    client: WebClient,
    session_manager: SessionManager,
    *,
    event_ts: str | None = None,
) -> None:
    """Route an incoming user message through the session manager."""

    # De-duplicate: Slack sends both `message` and `app_mention` for
    # @-mentions.  Whichever handler fires first wins; the second is a no-op.
    if event_ts is not None and _is_duplicate_event(event_ts):
        log.debug("Skipping duplicate event %s", event_ts)
        return

    # The event's ts is the message timestamp — use it as thread_ts so all
    # responses are posted as threaded replies to the user's message.
    thread_ts = event_ts

    # Check for an existing session first (fast path, no blocking).
    existing = session_manager.get_session(user_id)

    _set_presence(client, "auto")  # mark active

    use_streaming = _has_streaming(client)

    if existing is not None:
        # ── Follow-up message in existing session ──
        if use_streaming:
            _set_thread_status(
                client, channel_id, thread_ts or "",
                "Reading your message...",
                loading_messages=[],
            )
            try:
                response = session_manager.send_message(existing, text)
                _set_thread_status(
                    client, channel_id, thread_ts or "",
                    "Preparing response...",
                    loading_messages=[],
                )
                _stream_response(
                    client, channel_id,
                    response or "_Leo didn't produce a response._",
                    thread_ts=thread_ts,
                )
                _set_thread_status(client, channel_id, thread_ts or "", "")
            except TimeoutError:
                _stream_response(
                    client, channel_id,
                    ":hourglass: Timed out waiting for Leo. Try again or start a new session.",
                    thread_ts=thread_ts,
                )
                _set_thread_status(client, channel_id, thread_ts or "", "")
            except RuntimeError as exc:
                log.error("send_message failed for user %s: %s", user_id, exc)
                _stream_response(
                    client, channel_id,
                    f":warning: Could not deliver message: {exc}",
                    thread_ts=thread_ts,
                )
                _set_thread_status(client, channel_id, thread_ts or "", "")
        else:
            # Fallback: classic postMessage + update pattern.
            status_ts = _post_status(
                client, channel_id,
                ":hourglass_flowing_sand: _Leo is thinking..._",
                thread_ts=thread_ts,
            )
            try:
                response = session_manager.send_message(existing, text)
                _update_status(client, channel_id, status_ts, response or "_Leo didn't produce a response._")
            except TimeoutError:
                _update_status(client, channel_id, status_ts, ":hourglass: Timed out waiting for Leo. Try again or start a new session.")
            except RuntimeError as exc:
                log.error("send_message failed for user %s: %s", user_id, exc)
                _update_status(client, channel_id, status_ts, f":warning: Could not deliver message: {exc}")
        return

    # ── New session ──
    if use_streaming:
        _set_thread_status(
            client, channel_id, thread_ts or "",
            "Setting up sandbox...",
            loading_messages=[],
        )

        # Read channel history for context.
        history_context = _read_channel_history(client, channel_id, limit=20)
        if history_context:
            enriched_message = f"{history_context}\n\n---\n\nUser's request:\n{text}"
        else:
            enriched_message = text

        _set_thread_status(
            client, channel_id, thread_ts or "",
            "Spinning up sandbox...",
            loading_messages=[],
        )

        try:
            session, _is_new = session_manager.get_or_create_session(
                user_id, channel_id, enriched_message
            )
        except Exception as exc:
            log.error("Failed to create session for user %s: %s", user_id, exc, exc_info=True)
            _stream_response(
                client, channel_id,
                f":x: Could not start a session: {exc}",
                thread_ts=thread_ts,
            )
            _set_thread_status(client, channel_id, thread_ts or "", "")
            return

        version = session.sandbox_version
        _set_thread_status(
            client, channel_id, thread_ts or "",
            "Leo is working...",
            loading_messages=[],
        )

        # Retrieve the first-turn response and stream it.
        try:
            response = session.worker.get_response()
            _set_thread_status(
                client, channel_id, thread_ts or "",
                "Preparing response...",
                loading_messages=[],
            )
            _stream_response(
                client, channel_id,
                f":package: `main@{version}`\n\n{response}" if response
                else "_Leo didn't produce a response._",
                thread_ts=thread_ts,
            )
            _set_thread_status(client, channel_id, thread_ts or "", "")
        except Exception as exc:
            log.error("Could not get first-turn response: %s", exc, exc_info=True)
            _stream_response(
                client, channel_id,
                f":warning: Session started (`main@{version}`) but could not read the response: {exc}",
                thread_ts=thread_ts,
            )
            _set_thread_status(client, channel_id, thread_ts or "", "")
    else:
        # Fallback: classic postMessage + update pattern.
        status_ts = _post_status(
            client, channel_id,
            ":package: *New session* -- reading channel history...",
            thread_ts=thread_ts,
        )

        # Read channel history for context.
        history_context = _read_channel_history(client, channel_id, limit=20)
        if history_context:
            enriched_message = f"{history_context}\n\n---\n\nUser's request:\n{text}"
        else:
            enriched_message = text

        _update_status(
            client, channel_id, status_ts,
            ":package: *New session* -- spinning up sandbox..."
        )

        try:
            session, _is_new = session_manager.get_or_create_session(
                user_id, channel_id, enriched_message
            )
        except Exception as exc:
            log.error("Failed to create session for user %s: %s", user_id, exc, exc_info=True)
            _update_status(client, channel_id, status_ts, f":x: Could not start a session: {exc}")
            return

        version = session.sandbox_version
        _update_status(
            client, channel_id, status_ts,
            f":package: *New session* -- sandbox `main@{version}` -- _Leo is working..._"
        )

        # Retrieve the first-turn response and replace the status message.
        try:
            response = session.worker.get_response()
            _update_status(
                client, channel_id, status_ts,
                f":package: `main@{version}`\n\n{response}" if response
                else "_Leo didn't produce a response._"
            )
        except Exception as exc:
            log.error("Could not get first-turn response: %s", exc, exc_info=True)
            _update_status(
                client, channel_id, status_ts,
                f":warning: Session started (`main@{version}`) but could not read the response: {exc}"
            )


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(config: PipelineConfig) -> tuple[App, SessionManager]:
    """Create and configure the Slack Bolt app and session manager."""

    app = App(token=os.environ["SLACK_BOT_TOKEN"])
    session_manager = SessionManager(config)

    # Wire up the session-close callback so Mechanic results reach Slack.
    session_manager.on_session_closed = _make_session_closed_callback(app.client)

    # Log streaming API availability at startup.
    if _has_streaming(app.client):
        log.info("Slack streaming APIs (chat.startStream) detected -- using streaming mode")
    else:
        log.info(
            "Slack streaming APIs not available in this slack_sdk version -- "
            "using classic chat.postMessage + chat.update fallback"
        )

    # -- event: direct message or channel message ----------------------------

    @app.event("message")
    def handle_message(event, say, client):
        user_id = event.get("user")
        channel_id = event.get("channel")
        text = event.get("text", "")
        event_ts = event.get("event_ts") or event.get("ts")

        # Skip bot messages to prevent infinite loops.
        if event.get("bot_id") or event.get("subtype") or not user_id:
            return

        # Only process DMs — channel messages require an @mention, which
        # is handled by the app_mention event handler.
        if event.get("channel_type") != "im":
            return

        if not text.strip():
            return

        try:
            _handle_user_message(user_id, channel_id, text, say, client, session_manager, event_ts=event_ts)
        except Exception:
            log.error("Unhandled error in message handler:\n%s", traceback.format_exc())
            try:
                say("\u274c Something went wrong. Check the logs for details.", thread_ts=event_ts)
            except Exception:
                pass

    # -- event: @Leo mention in a channel ------------------------------------

    @app.event("app_mention")
    def handle_mention(event, say, client):
        user_id = event.get("user")
        channel_id = event.get("channel")
        raw_text = event.get("text", "")
        event_ts = event.get("event_ts") or event.get("ts")

        if not user_id:
            return

        # Strip the @mention prefix (e.g. "<@U1234ABC> do something")
        text = re.sub(r"<@[A-Z0-9]+>\s*", "", raw_text).strip()
        if not text:
            say("Hey! Send me a message and I'll get to work.", thread_ts=event_ts)
            return

        try:
            _handle_user_message(user_id, channel_id, text, say, client, session_manager, event_ts=event_ts)
        except Exception:
            log.error("Unhandled error in mention handler:\n%s", traceback.format_exc())
            try:
                say("\u274c Something went wrong. Check the logs for details.", thread_ts=event_ts)
            except Exception:
                pass

    return app, session_manager


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the Slack listener (blocks forever)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Validate required env vars early.
    for var in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"):
        if not os.environ.get(var):
            log.critical("Missing required environment variable: %s", var)
            sys.exit(1)

    config = PipelineConfig()
    app, session_manager = create_app(config)

    # -- graceful shutdown ---------------------------------------------------

    def shutdown(signum, _frame):
        sig_name = signal.Signals(signum).name
        log.info("Received %s -- shutting down", sig_name)
        session_manager.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # -- start ---------------------------------------------------------------

    session_manager.start()
    log.info("Slack listener starting in socket mode")

    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    handler.start()  # blocks


if __name__ == "__main__":
    main()
