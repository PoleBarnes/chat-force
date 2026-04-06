"""Slack socket-mode listener for a chat-force bot.

Connects to Slack, routes messages to the session manager,
and posts the bot's responses back to channels.

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
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from slack_bolt import App, Assistant, SetStatus, SetTitle, SetSuggestedPrompts, Say
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.models.blocks import (
    Block,
    ContextActionsBlock,
    FeedbackButtonObject,
    FeedbackButtonsElement,
)

from pipeline.config import PipelineConfig
from pipeline.harness_loader import HarnessLoader, HarnessValidationError
from pipeline.session_manager import Session, SessionManager

# Thinking-step chunk types -- available in slack_sdk >= 3.41.
# Fall back gracefully if running an older SDK.
try:
    from slack_sdk.models.messages.chunk import (
        PlanUpdateChunk,
        TaskUpdateChunk,
    )

    _HAS_CHUNKS = True
except ImportError:  # pragma: no cover
    _HAS_CHUNKS = False

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
# Feedback buttons
# ---------------------------------------------------------------------------


def _feedback_blocks() -> list[Block]:
    """Return Block Kit feedback buttons (thumbs up / down) for streamed messages."""
    return [
        ContextActionsBlock(
            elements=[
                FeedbackButtonsElement(
                    action_id="feedback",
                    positive_button=FeedbackButtonObject(
                        text="Good Response",
                        accessibility_label="Submit positive feedback on this response",
                        value="good-feedback",
                    ),
                    negative_button=FeedbackButtonObject(
                        text="Bad Response",
                        accessibility_label="Submit negative feedback on this response",
                        value="bad-feedback",
                    ),
                )
            ]
        )
    ]


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


_cached_team_id: str | None = None


def _get_team_id(client) -> str:
    global _cached_team_id
    if _cached_team_id is None:
        resp = client.auth_test()
        _cached_team_id = resp.get("team_id", "")
    return _cached_team_id


def create_app(config: PipelineConfig) -> tuple[App, SessionManager]:
    """Create and configure the Slack Bolt app and session manager."""

    if config.harness is None:
        raise RuntimeError(
            "create_app requires a PipelineConfig with a loaded harness. "
            "Set config.harness via HarnessLoader.load() before calling."
        )
    bot_name = config.harness.bot_name
    thinking_status = f"{bot_name} is thinking..."
    working_status = f"{bot_name} is working..."
    working_request_status = f"{bot_name} is working on your request..."
    finished_status = f"{bot_name} finished"
    error_status = f"{bot_name} encountered an error"
    empty_response_text = f"_{bot_name} didn't produce a response._"
    timeout_new_session_text = (
        f":hourglass: Timed out waiting for {bot_name}. "
        "Try again or start a new session."
    )
    timeout_text = f":hourglass: Timed out waiting for {bot_name}. Try again."

    app = App(token=os.environ[config.harness.bot_token_env])
    session_manager = SessionManager(config)

    # Wire up the session-close callback so Mechanic results reach Slack.
    session_manager.on_session_closed = _make_session_closed_callback(app.client)

    # -- Assistant class (handles DM / assistant-panel threads) --------------

    assistant = Assistant()

    @assistant.thread_started
    def handle_thread_started(say: Say, set_suggested_prompts: SetSuggestedPrompts, logger):
        try:
            say(f"Hey! I'm {bot_name} \u2014 tell me what you need and I'll get to work.")
            set_suggested_prompts(
                prompts=[
                    {
                        "title": "Help me plan a task",
                        "message": (
                            "I have a task I'd like your help planning. "
                            "Ask me questions to understand what I need."
                        ),
                    },
                    {
                        "title": "Draft a short update",
                        "message": "Help me draft a short update I can share with my team.",
                    },
                    {
                        "title": "Ask me what you need",
                        "message": "What information do you need from me to do your best work?",
                    },
                ]
            )
        except Exception as e:
            logger.exception(f"Failed to handle assistant_thread_started event: {e}")
            say(f":warning: Something went wrong! ({e})")

    @assistant.user_message
    def handle_user_message(payload, client, context, say, set_status, set_title, logger):
        """Route assistant-thread messages through the session manager.

        Replaces the old ``@app.event("message")`` handler and the
        ``_handle_user_message`` helper.  Bolt's Assistant class calls
        this for every user message in a DM / assistant thread, with
        deduplication and status lifecycle handled automatically.

        When the SDK supports chunk types, responses include structured
        thinking steps (plan / timeline) so the user sees progress
        checkmarks instead of flat status text.
        """
        try:
            user_id = context.user_id
            channel_id = payload["channel"]
            text = payload.get("text", "")
            thread_ts = payload["thread_ts"]

            if not text.strip():
                return

            set_status(status="Reading your message...", loading_messages=[])

            # -- Check for existing session (fast path) --
            existing = session_manager.get_session(user_id)

            if existing is not None:
                # ── Follow-up message in existing session ──
                set_status(status=thinking_status, loading_messages=[])

                try:
                    response = session_manager.send_message(existing, text)
                except TimeoutError:
                    say(timeout_new_session_text)
                    set_status(status="")
                    return
                except RuntimeError as exc:
                    log.error("send_message failed for user %s: %s", user_id, exc)
                    say(f":warning: Could not deliver message: {exc}")
                    set_status(status="")
                    return

                response_body = response or empty_response_text

                if _HAS_CHUNKS:
                    # Timeline mode: single thinking step then response.
                    streamer = client.chat_stream(
                        channel=channel_id,
                        thread_ts=thread_ts,
                        recipient_team_id=context.team_id,
                        recipient_user_id=context.user_id,
                        task_display_mode="timeline",
                    )
                    streamer.append(chunks=[
                        TaskUpdateChunk(id="think", title=thinking_status, status="in_progress"),
                    ])
                    streamer.append(chunks=[
                        TaskUpdateChunk(id="think", title=thinking_status, status="complete"),
                    ])
                    streamer.append(markdown_text=response_body)
                    streamer.stop(blocks=_feedback_blocks())
                else:
                    streamer = client.chat_stream(
                        channel=channel_id,
                        thread_ts=thread_ts,
                        recipient_team_id=context.team_id,
                        recipient_user_id=context.user_id,
                    )
                    streamer.append(markdown_text=response_body)
                    streamer.stop(blocks=_feedback_blocks())
                return

            # ── New session ──
            set_status(status="Reading channel history...", loading_messages=[])

            history_context = _read_channel_history(client, channel_id, limit=20)
            if history_context:
                enriched_message = f"{history_context}\n\n---\n\nUser's request:\n{text}"
            else:
                enriched_message = text

            # Start the streamer early so we can show thinking steps.
            if _HAS_CHUNKS:
                streamer = client.chat_stream(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    recipient_team_id=context.team_id,
                    recipient_user_id=context.user_id,
                    task_display_mode="plan",
                )
                streamer.append(chunks=[
                    PlanUpdateChunk(id="plan", title="Working on your request"),
                    TaskUpdateChunk(id="sandbox", title="Setting up sandbox...", status="in_progress"),
                    TaskUpdateChunk(id="worker", title=working_status, status="pending"),
                    TaskUpdateChunk(id="response", title="Preparing response", status="pending"),
                ])
            else:
                streamer = None
                set_status(status="Spinning up sandbox...", loading_messages=[])

            try:
                session, is_new = session_manager.get_or_create_session(
                    user_id, channel_id, enriched_message
                )
            except Exception as exc:
                log.error("Failed to create session for user %s: %s", user_id, exc, exc_info=True)
                if streamer is not None:
                    streamer.append(chunks=[
                        TaskUpdateChunk(id="sandbox", title="Setting up sandbox... failed", status="complete"),
                    ])
                    streamer.append(markdown_text=f":x: Could not start a session: {exc}")
                    streamer.stop()
                else:
                    say(f":x: Could not start a session: {exc}")
                    set_status(status="")
                return

            if not is_new:
                # Session was created by another thread -- send as follow-up.
                if streamer is not None:
                    streamer.append(chunks=[
                        TaskUpdateChunk(id="sandbox", title="Using existing session", status="complete"),
                        TaskUpdateChunk(id="worker", title=thinking_status, status="in_progress"),
                    ])

                try:
                    response = session_manager.send_message(session, text)
                except TimeoutError:
                    if streamer is not None:
                        streamer.append(chunks=[
                            TaskUpdateChunk(id="worker", title="Timed out", status="complete"),
                            TaskUpdateChunk(id="response", title="Preparing response", status="complete"),
                        ])
                        streamer.append(markdown_text=timeout_new_session_text)
                        streamer.stop()
                    else:
                        say(timeout_new_session_text)
                        set_status(status="")
                    return
                except RuntimeError as exc:
                    log.error("send_message failed for user %s: %s", user_id, exc)
                    if streamer is not None:
                        streamer.append(chunks=[
                            TaskUpdateChunk(id="worker", title="Error", status="complete"),
                            TaskUpdateChunk(id="response", title="Preparing response", status="complete"),
                        ])
                        streamer.append(markdown_text=f":warning: Could not deliver message: {exc}")
                        streamer.stop()
                    else:
                        say(f":warning: Could not deliver message: {exc}")
                        set_status(status="")
                    return

                response_body = response or empty_response_text

                if streamer is not None:
                    streamer.append(chunks=[
                        TaskUpdateChunk(id="worker", title=finished_status, status="complete"),
                        TaskUpdateChunk(id="response", title="Response ready", status="complete"),
                    ])
                    streamer.append(markdown_text=response_body)
                    streamer.stop(blocks=_feedback_blocks())
                else:
                    streamer = client.chat_stream(
                        channel=channel_id,
                        thread_ts=thread_ts,
                        recipient_team_id=context.team_id,
                        recipient_user_id=context.user_id,
                    )
                    streamer.append(markdown_text=response_body)
                    streamer.stop(blocks=_feedback_blocks())
                return

            version = session.sandbox_version

            # Sandbox ready -- update thinking steps.
            if _HAS_CHUNKS and streamer is not None:
                streamer.append(chunks=[
                    TaskUpdateChunk(
                        id="sandbox",
                        title=f"Setting up sandbox (main@{version})",
                        status="complete",
                    ),
                    TaskUpdateChunk(
                        id="worker",
                        title=working_request_status,
                        status="in_progress",
                    ),
                ])
            else:
                set_status(status=working_status, loading_messages=[])

            # Retrieve first-turn response.
            try:
                response = session.worker.get_response()
            except Exception as exc:
                log.error("Could not get first-turn response: %s", exc, exc_info=True)
                if _HAS_CHUNKS and streamer is not None:
                    streamer.append(chunks=[
                        TaskUpdateChunk(id="worker", title=error_status, status="complete"),
                        TaskUpdateChunk(id="response", title="Preparing response", status="complete"),
                    ])
                    streamer.append(
                        markdown_text=f":warning: Session started (`main@{version}`) but could not read the response: {exc}",
                    )
                    streamer.stop()
                else:
                    say(f":warning: Session started (`main@{version}`) but could not read the response: {exc}")
                    set_status(status="")
                return

            # Worker done -- prepare the response.
            response_text = (
                f":package: `main@{version}`\n\n{response}" if response
                else empty_response_text
            )

            if _HAS_CHUNKS and streamer is not None:
                streamer.append(chunks=[
                    TaskUpdateChunk(id="worker", title=finished_status, status="complete"),
                    TaskUpdateChunk(id="response", title="Preparing response...", status="in_progress"),
                ])
                streamer.append(markdown_text=response_text)
                streamer.append(chunks=[
                    TaskUpdateChunk(id="response", title="Response ready", status="complete"),
                ])
                streamer.stop(blocks=_feedback_blocks())
            else:
                streamer = client.chat_stream(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    recipient_team_id=context.team_id,
                    recipient_user_id=context.user_id,
                )
                streamer.append(markdown_text=response_text)
                streamer.stop(blocks=_feedback_blocks())

            # Set thread title on first message.
            try:
                set_title(title=text[:50])
            except Exception:
                logger.debug("Could not set thread title", exc_info=True)

        except Exception as e:
            logger.exception(f"Failed to handle user message: {e}")
            try:
                say(f":warning: Something went wrong! ({e})")
                set_status(status="")
            except Exception:
                pass

    app.use(assistant)

    # -- Catch-all message handler ------------------------------------------
    # The Assistant class handles DMs/assistant-thread messages.
    # This catches channel messages and thread replies that don't need
    # processing, preventing Bolt warnings about unhandled message events.

    @app.event("message")
    def handle_other_messages(event, say, client, logger):
        # Skip bot messages and subtypes to prevent loops.
        if event.get("bot_id") or event.get("subtype"):
            logger.debug("Ignoring bot/subtype message in channel %s", event.get("channel"))
            return

        thread_ts = event.get("thread_ts")
        ts = event.get("ts")

        # Only process thread replies (thread_ts present and different from ts).
        if not thread_ts or thread_ts == ts:
            logger.debug("Ignoring non-thread message event in channel %s", event.get("channel"))
            return

        user_id = event.get("user")
        text = event.get("text", "")
        channel_id = event.get("channel")

        if not user_id or not text.strip():
            return

        # Check if the user has an active session.
        session = session_manager.get_session(user_id)
        if session is None:
            logger.debug(
                "Thread reply from %s in %s but no active session — ignoring",
                user_id,
                channel_id,
            )
            return

        # Route the thread reply to the session manager.
        logger.info("Routing thread reply from %s to active session", user_id)

        try:
            response = session_manager.send_message(session, text)
        except TimeoutError:
            say(timeout_text, thread_ts=thread_ts)
            return
        except RuntimeError as exc:
            log.error("send_message failed for thread reply from %s: %s", user_id, exc)
            say(f":warning: Could not deliver message: {exc}", thread_ts=thread_ts)
            return

        response_body = response or empty_response_text

        try:
            streamer = client.chat_stream(
                channel=channel_id,
                thread_ts=thread_ts,
                recipient_team_id=_get_team_id(client),
                recipient_user_id=user_id,
            )
            streamer.append(markdown_text=response_body)
            streamer.stop(blocks=_feedback_blocks())
        except Exception:
            # Fallback: post as a plain message if streaming fails.
            log.warning("chat_stream failed for thread reply, falling back to say()", exc_info=True)
            say(response_body, thread_ts=thread_ts)

    # -- event: @bot mention in a channel ------------------------------------
    # The Assistant class does not handle channel @-mentions, so this
    # stays as a separate event handler.

    @app.event("app_mention")
    def handle_mention(event, say, client):
        """Handle @bot mentions in channels.

        Unlike the assistant handler (DMs), channel @mentions do NOT use
        the Slack assistant streaming API (chat_stream). The streaming API
        requires an assistant thread context that regular channel mentions
        don't have, and calling it here produces 'Resource ID was not
        provided' errors. Instead we use plain say() for all responses.
        """
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

        thread_ts = event_ts  # reply in a thread under the mention

        try:
            # Check for existing session (fast path).
            existing = session_manager.get_session(user_id)

            if existing is not None:
                try:
                    response = session_manager.send_message(existing, text)
                except TimeoutError:
                    say(timeout_new_session_text, thread_ts=thread_ts)
                    return
                except RuntimeError as exc:
                    log.error("send_message failed for user %s: %s", user_id, exc)
                    say(f":warning: Could not deliver message: {exc}", thread_ts=thread_ts)
                    return

                say(response or empty_response_text, thread_ts=thread_ts)
                return

            # New session -- enrich with channel history.
            history_context = _read_channel_history(client, channel_id, limit=20)
            if history_context:
                enriched_message = f"{history_context}\n\n---\n\nUser's request:\n{text}"
            else:
                enriched_message = text

            try:
                session, is_new = session_manager.get_or_create_session(
                    user_id, channel_id, enriched_message
                )
            except Exception as exc:
                log.error("Failed to create session for user %s: %s", user_id, exc, exc_info=True)
                say(f":x: Could not start a session: {exc}", thread_ts=thread_ts)
                return

            if not is_new:
                # Session was created by another thread -- send as follow-up.
                try:
                    response = session_manager.send_message(session, text)
                except TimeoutError:
                    say(timeout_new_session_text, thread_ts=thread_ts)
                    return
                except RuntimeError as exc:
                    log.error("send_message failed for user %s: %s", user_id, exc)
                    say(f":warning: Could not deliver message: {exc}", thread_ts=thread_ts)
                    return

                say(response or empty_response_text, thread_ts=thread_ts)
                return

            version = session.sandbox_version

            try:
                response = session.worker.get_response()
            except Exception as exc:
                log.error("Could not get first-turn response: %s", exc, exc_info=True)
                say(
                    f":warning: Session started (`main@{version}`) but could not read the response: {exc}",
                    thread_ts=thread_ts,
                )
                return

            response_text = (
                f":package: `main@{version}`\n\n{response}" if response
                else empty_response_text
            )

            say(response_text, thread_ts=thread_ts)

        except Exception:
            log.error("Unhandled error in mention handler", exc_info=True)
            try:
                say("\u274c Something went wrong. Check the logs for details.", thread_ts=event_ts)
            except Exception:
                pass

    # -- Feedback action handlers ----------------------------------------------

    @app.action("feedback")
    def handle_feedback(ack, body, client, logger):
        """Handle thumbs-up / thumbs-down feedback button clicks."""
        try:
            ack()
            message_ts = body["message"]["ts"]
            channel_id = body["channel"]["id"]
            user_id = body["user"]["id"]
            feedback_value = body["actions"][0].get("value", "unknown")
            is_positive = feedback_value == "good-feedback"

            logger.info(
                "Feedback received: user=%s value=%s message_ts=%s",
                user_id,
                feedback_value,
                message_ts,
            )

            if is_positive:
                client.chat_postEphemeral(
                    channel=channel_id,
                    user=user_id,
                    thread_ts=message_ts,
                    text="Thanks for the feedback!",
                )
            else:
                client.chat_postEphemeral(
                    channel=channel_id,
                    user=user_id,
                    thread_ts=message_ts,
                    text="Sorry that wasn't helpful. Starting a new thread may improve results.",
                )
        except Exception:
            logger.error("Failed to handle feedback action", exc_info=True)

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

    try:
        loaded = HarnessLoader.load(HarnessLoader.resolve_path())
    except HarnessValidationError as exc:
        log.critical("%s", exc)
        sys.exit(1)

    config = PipelineConfig(harness=loaded)
    bot_token = os.environ[config.harness.bot_token_env]
    app_token = os.environ[config.harness.app_token_env]
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

    handler = SocketModeHandler(app, app_token)
    handler.start()  # blocks


if __name__ == "__main__":
    main()
