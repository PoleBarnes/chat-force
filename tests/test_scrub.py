"""Tests for pipeline/scrub.py — secret scrubbing."""

from __future__ import annotations

import pytest

from pipeline.scrub import scrub_secrets


class TestScrubSecrets:
    """Test that scrub_secrets catches common secret patterns."""

    def test_slack_bot_token(self):
        text = "Error: token xoxb-123-456-abc was rejected"
        assert scrub_secrets(text) == "Error: token [SLACK_BOT_TOKEN] was rejected"

    def test_slack_user_token(self):
        text = "Auth failed with xoxp-111-222-333-deadbeef"
        assert "[SLACK_USER_TOKEN]" in scrub_secrets(text)
        assert "xoxp-" not in scrub_secrets(text)

    def test_slack_app_token(self):
        text = "xapp-1-A0B1C2D3E4-abc123def456"
        assert scrub_secrets(text) == "[SLACK_APP_TOKEN]"

    def test_github_pat(self):
        text = "clone https://ghp_abc123XYZ@github.com/repo.git failed"
        result = scrub_secrets(text)
        assert "ghp_" not in result
        assert "[GITHUB_TOKEN]" in result or "[REDACTED]" in result

    def test_github_fine_grained_pat(self):
        text = "token: github_pat_11AABBC_xyzABC123"
        result = scrub_secrets(text)
        assert "github_pat_" not in result

    def test_anthropic_api_key(self):
        text = "ANTHROPIC_API_KEY=sk-ant-api03-secret-key-here"
        result = scrub_secrets(text)
        assert "sk-ant-" not in result
        assert "[ANTHROPIC_API_KEY]" in result

    def test_bearer_token_in_header(self):
        text = 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig'
        result = scrub_secrets(text)
        assert "eyJ" not in result
        assert "Bearer [REDACTED]" in result

    def test_token_in_url(self):
        text = "https://ghp_secret123@github.com/org/repo.git"
        result = scrub_secrets(text)
        assert "ghp_secret123" not in result

    def test_multiple_secrets_in_one_string(self):
        text = "bot=xoxb-111-222 app=xapp-1-ABC key=sk-ant-api03-xyz"
        result = scrub_secrets(text)
        assert "xoxb-" not in result
        assert "xapp-" not in result
        assert "sk-ant-" not in result

    def test_no_secrets_passes_through(self):
        text = "Normal error message with no secrets"
        assert scrub_secrets(text) == text

    def test_empty_string(self):
        assert scrub_secrets("") == ""

    def test_preserves_non_secret_content(self):
        text = "File /harness/identity/brand.md not found (user U0AG4Q4G1FB)"
        assert scrub_secrets(text) == text

    def test_partial_match_not_scrubbed(self):
        """Strings that look similar but aren't real tokens should pass through."""
        text = "The word 'skeleton' contains 'sk-' but is not a secret"
        result = scrub_secrets(text)
        # 'skeleton' should not be scrubbed — sk-ant pattern requires 'sk-ant-'
        assert "skeleton" in result
