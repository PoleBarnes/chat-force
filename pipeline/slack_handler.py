"""Slack notifications for pipeline events.

Prototype: posts to a hardcoded admin channel.  All methods are no-ops
if SLACK_BOT_TOKEN is not set in the environment (graceful degradation).
"""

import logging
import os

from pipeline.config import PipelineConfig

log = logging.getLogger(__name__)

# Hardcoded for prototype -- move to config or Doppler later.
_ADMIN_CHANNEL = "#openclaw-pipeline"


class SlackHandler:
    """Send pipeline notifications to Slack."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self._token = os.environ.get(config.slack_token_env)
        self._client = None

        if self._token:
            try:
                from slack_sdk import WebClient

                self._client = WebClient(token=self._token)
            except ImportError:
                log.warning(
                    "slack_sdk not installed -- Slack notifications disabled. "
                    "Install with: uv pip install slack_sdk"
                )

    # -- public API -----------------------------------------------------------

    def notify_approved(self, run_id: str, task: str, pr_url: str) -> None:
        """Post an approval notification with the PR link."""
        text = (
            f"*PR Created* -- run `{run_id}`\n"
            f"Task: {task}\n"
            f"PR: {pr_url}"
        )
        self._post(text)

    def notify_rejected(self, run_id: str, task: str, reason: str) -> None:
        """Post a rejection notification with the reason."""
        text = (
            f"*Rejected* -- run `{run_id}`\n"
            f"Task: {task}\n"
            f"Reason: {reason}"
        )
        self._post(text)

    # -- internals ------------------------------------------------------------

    def _post(self, text: str) -> None:
        """Send a message to the admin channel, or log it if Slack is unavailable."""
        if self._client is None:
            log.info("Slack (no-op): %s", text)
            return

        try:
            self._client.chat_postMessage(
                channel=_ADMIN_CHANNEL,
                text=text,
            )
            log.debug("Slack message sent to %s", _ADMIN_CHANNEL)
        except Exception:
            # Never crash the pipeline because of a notification failure.
            log.warning("Failed to send Slack message", exc_info=True)
