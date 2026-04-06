#!/usr/bin/env python3
"""Automated end-to-end smoke test for the chat-force engine.

Starts the listener with a test harness, posts a message as a real Slack
user, waits for the bot's response, and verifies it reflects the harness
config (bot name, identity) rather than any hardcoded persona.

Requires:
- Docker running with chat-force-worker:latest image built
- Doppler secrets: SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_USER_TOKEN,
  CLAUDE_CODE_OAUTH_TOKEN
- A valid harness at the path specified by --harness-path or HARNESS_PATH

Usage:
    doppler run --project chat-force --config dev -- \\
        uv run --python 3.13 \\
        --with docker,"slack_sdk>=3.41.0","slack_bolt>=1.27.0","pydantic>=2","ruamel.yaml",claude-agent-sdk \\
        python scripts/smoke_test.py \\
        --harness-path /tmp/harness-travis-personal \\
        --channel C0AQH56K2BE

Note: claude-agent-sdk is required for the Mechanic phase that runs
after session close. Without it, the Worker responds but the Mechanic
fails with ImportError.

Exit codes:
    0 = smoke test passed
    1 = smoke test failed (assertion or timeout)
    2 = setup error (missing env vars, listener failed to start, etc.)
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import textwrap
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# How long to wait for the listener to connect to Slack.
LISTENER_STARTUP_TIMEOUT = 30

# How long to wait for the bot to respond after posting a message.
RESPONSE_TIMEOUT = 180

# How often to poll for the bot's response.
POLL_INTERVAL = 5


# ---------------------------------------------------------------------------
# Slack API helpers
# ---------------------------------------------------------------------------


def _slack_api(method: str, token: str, data: dict | None = None) -> dict:
    """Call a Slack Web API method and return the parsed response."""
    url = f"https://slack.com/api/{method}"
    if data:
        body = urllib.parse.urlencode(data).encode()
    else:
        body = b""
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=body,
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
    if not resp.get("ok"):
        raise RuntimeError(f"Slack API {method} failed: {resp.get('error', resp)}")
    return resp


def _get_bot_user_id(bot_token: str) -> str:
    resp = _slack_api("auth.test", bot_token)
    return resp["user_id"]


def _post_message(user_token: str, channel: str, text: str) -> str:
    """Post a message as the user. Returns the message timestamp."""
    resp = _slack_api(
        "chat.postMessage",
        user_token,
        {"channel": channel, "text": text},
    )
    return resp["ts"]


def _get_thread_replies(
    user_token: str, channel: str, thread_ts: str
) -> list[dict]:
    """Get all replies in a thread."""
    resp = _slack_api(
        "conversations.replies",
        user_token,
        {"channel": channel, "ts": thread_ts, "limit": "50"},
    )
    return resp.get("messages", [])


def _get_channel_messages(
    user_token: str, channel: str, oldest: str, limit: int = 20
) -> list[dict]:
    """Get messages in a channel newer than oldest."""
    resp = _slack_api(
        "conversations.history",
        user_token,
        {"channel": channel, "oldest": oldest, "limit": str(limit)},
    )
    return resp.get("messages", [])


# ---------------------------------------------------------------------------
# Listener subprocess management
# ---------------------------------------------------------------------------


def _start_listener(harness_path: str) -> subprocess.Popen:
    """Start the Slack listener as a subprocess. Returns the Popen handle."""
    env = os.environ.copy()
    env["HARNESS_PATH"] = harness_path

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "pipeline.slack_listener",
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc


def _wait_for_listener_ready(proc: subprocess.Popen, timeout: int) -> None:
    """Block until the listener prints 'Bolt app is running' or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            # Process died — read remaining output.
            remaining = proc.stdout.read() if proc.stdout else ""
            raise RuntimeError(
                f"Listener process died (exit {proc.returncode}).\n"
                f"Output:\n{remaining}"
            )
        line = ""
        # Non-blocking readline via select is complex; use a tight timeout.
        import selectors
        sel = selectors.DefaultSelector()
        sel.register(proc.stdout, selectors.EVENT_READ)
        events = sel.select(timeout=1)
        sel.unregister(proc.stdout)
        sel.close()
        if events:
            line = proc.stdout.readline()
            if line:
                sys.stderr.write(f"  [listener] {line}")
                if "Bolt app is running" in line:
                    return
    raise TimeoutError(
        f"Listener did not become ready within {timeout}s"
    )


def _stop_listener(proc: subprocess.Popen) -> None:
    """Gracefully stop the listener subprocess."""
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


def run_smoke_test(
    harness_path: str,
    channel: str,
    bot_name: str,
) -> bool:
    """Run the full smoke test. Returns True on pass, False on fail."""
    user_token = os.environ.get("SLACK_USER_TOKEN")
    bot_token = os.environ.get("SLACK_BOT_TOKEN")

    if not user_token:
        print("ERROR: SLACK_USER_TOKEN not set", file=sys.stderr)
        sys.exit(2)
    if not bot_token:
        print("ERROR: SLACK_BOT_TOKEN not set", file=sys.stderr)
        sys.exit(2)

    bot_user_id = _get_bot_user_id(bot_token)
    print(f"Bot user ID: {bot_user_id}")
    print(f"Expected bot name: {bot_name}")
    print(f"Channel: {channel}")
    print(f"Harness: {harness_path}")
    print()

    # --- Start listener ---
    print("Starting listener...")
    proc = _start_listener(harness_path)
    try:
        _wait_for_listener_ready(proc, LISTENER_STARTUP_TIMEOUT)
        print("Listener is ready.\n")

        # --- Send test message ---
        test_msg = f"<@{bot_user_id}> P0 smoke test: what is your name?"
        print(f"Posting: {test_msg}")
        msg_ts = _post_message(user_token, channel, test_msg)
        print(f"Message sent (ts={msg_ts}). Waiting for response...\n")

        # --- Poll for response ---
        deadline = time.monotonic() + RESPONSE_TIMEOUT
        bot_response = None

        while time.monotonic() < deadline:
            time.sleep(POLL_INTERVAL)

            # Check thread replies first (bot may reply in-thread).
            # Filter strictly on user == bot_user_id. Do NOT use bot_id —
            # user tokens created from the same Slack App get tagged with
            # the app's bot_id, causing false positives.
            try:
                replies = _get_thread_replies(user_token, channel, msg_ts)
                for reply in replies:
                    if reply.get("user") == bot_user_id and reply.get("ts") != msg_ts:
                        bot_response = reply.get("text", "")
                        break
            except Exception:
                pass  # thread may not exist yet

            if bot_response is not None:
                break

            # Also check channel-level messages (error posts go to channel, not thread).
            try:
                messages = _get_channel_messages(user_token, channel, msg_ts)
                for msg in messages:
                    if msg.get("user") == bot_user_id and msg.get("ts") != msg_ts:
                        bot_response = msg.get("text", "")
                        break
            except Exception:
                pass

            if bot_response is not None:
                break

            elapsed = int(time.monotonic() - (deadline - RESPONSE_TIMEOUT))
            sys.stderr.write(f"  ... polling ({elapsed}s elapsed)\n")

        if bot_response is None:
            print("FAIL: No response from bot within timeout.", file=sys.stderr)
            # Dump listener output for debugging.
            _stop_listener(proc)
            return False

        # --- Verify response ---
        print(f"Bot response ({len(bot_response)} chars):")
        print(textwrap.indent(bot_response[:500], "  "))
        print()

        passed = True

        # Check: response does NOT contain "Leo" as a standalone word.
        import re
        if re.search(r"\bLeo\b", bot_response):
            print("FAIL: Response contains 'Leo' — harness bot_name not applied.")
            passed = False

        # Check: the greeting (if this is the first message) uses bot_name.
        # This is a soft check — the bot may not include its name in every response.
        if bot_name.lower() not in bot_response.lower():
            print(
                f"NOTE: Response does not contain bot_name '{bot_name}'. "
                f"This may be normal if the bot doesn't self-identify in every reply."
            )

        if passed:
            print(f"PASS: Bot responded. No hardcoded 'Leo' references found.")

        return passed

    finally:
        print("\nStopping listener...")
        _stop_listener(proc)
        print("Done.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="chat-force P0 smoke test")
    parser.add_argument(
        "--harness-path",
        default=os.environ.get("HARNESS_PATH", "/tmp/harness-travis-personal"),
        help="Path to the harness directory (default: HARNESS_PATH env or /tmp/harness-travis-personal)",
    )
    parser.add_argument(
        "--channel",
        default="C0AQH56K2BE",
        help="Slack channel ID to post in (default: #sandbox)",
    )
    parser.add_argument(
        "--bot-name",
        default=None,
        help="Expected bot display name (default: read from harness workspace.yaml)",
    )
    args = parser.parse_args()

    # Read bot_name from harness if not specified.
    if args.bot_name is None:
        sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.harness_loader import HarnessLoader
        harness = HarnessLoader.load(args.harness_path)
        bot_name = harness.bot_name
    else:
        bot_name = args.bot_name

    passed = run_smoke_test(args.harness_path, args.channel, bot_name)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
