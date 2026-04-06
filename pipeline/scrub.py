"""Scrub secrets from text before surfacing to users or logs.

Any error message, exception text, or status update that reaches Slack
must go through ``scrub_secrets()`` first. This prevents API keys, OAuth
tokens, and other credentials from leaking through error messages.

Usage::

    from pipeline.scrub import scrub_secrets

    safe_text = scrub_secrets(raw_error_message)
    client.chat_postMessage(channel=ch, text=safe_text)
"""

from __future__ import annotations

import re

# Patterns that match common secret formats. Each tuple is
# (compiled_regex, replacement_label).
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Slack tokens
    (re.compile(r"xoxb-[A-Za-z0-9\-]+"), "[SLACK_BOT_TOKEN]"),
    (re.compile(r"xoxp-[A-Za-z0-9\-]+"), "[SLACK_USER_TOKEN]"),
    (re.compile(r"xapp-[A-Za-z0-9\-]+"), "[SLACK_APP_TOKEN]"),
    (re.compile(r"xoxs-[A-Za-z0-9\-]+"), "[SLACK_SESSION_TOKEN]"),
    # GitHub tokens
    (re.compile(r"ghp_[A-Za-z0-9]+"), "[GITHUB_TOKEN]"),
    (re.compile(r"gho_[A-Za-z0-9]+"), "[GITHUB_OAUTH_TOKEN]"),
    (re.compile(r"ghu_[A-Za-z0-9]+"), "[GITHUB_USER_TOKEN]"),
    (re.compile(r"ghs_[A-Za-z0-9]+"), "[GITHUB_SERVER_TOKEN]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]+"), "[GITHUB_PAT]"),
    # Anthropic API keys
    (re.compile(r"sk-ant-[A-Za-z0-9\-]+"), "[ANTHROPIC_API_KEY]"),
    # Generic "Bearer" tokens in URLs or headers
    (re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE), "Bearer [REDACTED]"),
    # Tokens embedded in URLs (https://TOKEN@github.com/...)
    (re.compile(r"(https?://)([A-Za-z0-9\-._~+/]+=*@)"), r"\1[REDACTED]@"),
]


def scrub_secrets(text: str) -> str:
    """Replace any recognized secret patterns in *text* with safe placeholders.

    Intended for error messages, exception text, and status updates that
    will be shown to users in Slack or written to logs. The original text
    is never modified — a new string is returned.

    This is a best-effort defense-in-depth measure. The primary control is
    never putting secrets into error messages in the first place; this
    function catches leaks that slip through.
    """
    result = text
    for pattern, replacement in _SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result
