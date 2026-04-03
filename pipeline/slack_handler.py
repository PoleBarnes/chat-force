"""Slack notifications for pipeline events.

Notifications are sent to the channel that triggered the pipeline.
When triggered from CLI (no channel), Slack is skipped entirely.
"""

import logging
import os

from pipeline.config import PipelineConfig

log = logging.getLogger(__name__)


class SlackHandler:
    """Send pipeline notifications to Slack."""

    def __init__(self, config: PipelineConfig, reply_channel: str | None = None):
        self._channel = reply_channel
        self._client = None

        if not reply_channel:
            return

        token = os.environ.get(config.slack_token_env)
        if not token:
            return

        try:
            from slack_sdk import WebClient

            self._client = WebClient(token=token)
        except ImportError:
            log.warning(
                "slack_sdk not installed — Slack notifications disabled. "
                "Install with: uv pip install slack_sdk"
            )

    # -- public API -----------------------------------------------------------

    def notify_approved(self, run_id: str, task: str, pr_url: str) -> None:
        """PR was created."""
        text = (
            f"*PR Created* — run `{run_id}`\n"
            f"Task: {task}\n"
            f"PR: {pr_url}"
        )
        self._post(text)

    def notify_rejected(self, run_id: str, task: str, reason: str) -> None:
        """Changes discarded."""
        text = (
            f"*Changes Discarded* — run `{run_id}`\n"
            f"Task: {task}\n"
            f"Reason: {reason}"
        )
        self._post(text)

    def notify_linear_proposal(self, run_id: str, task: str, verdict: dict) -> None:
        """Propose creating a Linear issue for architectural findings."""
        reason = verdict.get("disposition_reason", verdict.get("summary", ""))
        text = (
            f"*Findings Worth Tracking* — run `{run_id}`\n"
            f"Task: {task}\n"
            f"\n{reason}\n"
            f"\nWould you like me to create a Linear issue with these findings?\n"
            f"React with :white_check_mark: to create, or :x: to skip."
        )
        self._post(text)

    # -- internals ------------------------------------------------------------

    def _post(self, text: str) -> None:
        """Send a message to the reply channel, or log it if Slack is unavailable."""
        if self._client is None:
            log.info("Slack (skipped): %s", text)
            return

        try:
            self._client.chat_postMessage(
                channel=self._channel,
                text=text,
            )
            log.debug("Slack message sent to %s", self._channel)
        except Exception:
            log.warning("Failed to send Slack message", exc_info=True)
