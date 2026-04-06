"""Adversarial security tests for the chat-force engine.

These tests verify that the security controls actually block the attacks
they're designed to prevent. Each test targets a specific REQUIREMENTS.md
Part 1 Security item.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.config import PipelineConfig
from pipeline.changeset_extractor import ChangesetExtractor, SELF_MODIFICATION_DENY_LIST
from pipeline.pr_creator import PRCreator
from pipeline.scrub import scrub_secrets


# =========================================================================
# Self-modification deny-list (REQUIREMENTS: Worker cannot modify engine)
# =========================================================================


class TestSelfModificationAdversarial:
    """Adversarial tests: Worker cannot modify engine files."""

    @pytest.mark.parametrize(
        "path",
        [
            ".github/workflows/ci.yml",
            "pipeline/config.py",
            "pipeline/slack_listener.py",
            "worker/Dockerfile",
            "worker/entrypoint.py",
            "mechanic/config/SOUL.md",
            "tests/test_pipeline.py",
        ],
    )
    def test_each_denied_prefix_is_caught(self, path: str) -> None:
        """Every denied prefix in the deny-list must be caught."""
        git_changes = {"new_files": [path], "modified_files": [], "deleted_files": []}
        denied = ChangesetExtractor._check_self_modification(git_changes)
        assert path in denied, f"{path} should be denied but was allowed"

    @pytest.mark.parametrize(
        "path",
        [
            "skills/new-skill.md",
            "identity/brand.md",
            "eval/criteria.yaml",
            "vault/index.md",
            "landing-page.html",
            "README.md",
        ],
    )
    def test_harness_files_are_allowed(self, path: str) -> None:
        """Legitimate harness files must NOT be denied."""
        git_changes = {"new_files": [path], "modified_files": [], "deleted_files": []}
        denied = ChangesetExtractor._check_self_modification(git_changes)
        assert path not in denied, f"{path} should be allowed but was denied"

    def test_leading_slash_stripped(self) -> None:
        """Paths starting with / should still be caught."""
        git_changes = {"new_files": ["/pipeline/evil.py"], "modified_files": [], "deleted_files": []}
        denied = ChangesetExtractor._check_self_modification(git_changes)
        assert "/pipeline/evil.py" in denied

    def test_deny_list_completeness(self) -> None:
        """The deny-list must include all engine-critical paths."""
        required = {".github/", "worker/", "pipeline/", "mechanic/", "tests/"}
        actual = set(SELF_MODIFICATION_DENY_LIST)
        assert required == actual, f"Missing from deny-list: {required - actual}"


# =========================================================================
# Path traversal (REQUIREMENTS: PRCreator cannot write outside checkout)
# =========================================================================


class TestPathTraversalAdversarial:
    """Adversarial tests: PRCreator cannot write outside the checkout root."""

    def test_dot_dot_slash_attack(self, tmp_path: Path) -> None:
        pr = PRCreator(PipelineConfig(output_base=str(tmp_path)), "run")
        checkout = str(tmp_path / "checkout")
        os.makedirs(checkout)
        with pytest.raises(ValueError, match="Path traversal rejected"):
            pr._write_file(checkout, "../../../etc/shadow", {"../../../etc/shadow": "x"}, None)

    def test_encoded_traversal(self, tmp_path: Path) -> None:
        """Paths with encoded components should still be caught."""
        pr = PRCreator(PipelineConfig(output_base=str(tmp_path)), "run")
        checkout = str(tmp_path / "checkout")
        os.makedirs(checkout)
        # Even if the path looks weird, realpath resolves it
        with pytest.raises(ValueError, match="Path traversal rejected"):
            pr._write_file(checkout, "foo/../../../../../../tmp/evil", {"foo/../../../../../../tmp/evil": "x"}, None)

    def test_symlink_escape(self, tmp_path: Path) -> None:
        """Symlinks that escape the checkout should be caught by realpath."""
        pr = PRCreator(PipelineConfig(output_base=str(tmp_path)), "run")
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        # Create a symlink inside checkout that points outside
        link = checkout / "escape"
        link.symlink_to("/tmp")
        with pytest.raises(ValueError, match="Path traversal rejected"):
            pr._write_file(str(checkout), "escape/evil.txt", {"escape/evil.txt": "x"}, None)


# =========================================================================
# Secret scrubbing (REQUIREMENTS: tokens never in Slack messages)
# =========================================================================


class TestSecretScrubAdversarial:
    """Adversarial tests: secrets must never leak through error messages."""

    def test_real_world_traceback_with_token(self) -> None:
        """A traceback containing a real token must be scrubbed."""
        traceback_text = (
            'Traceback (most recent call last):\n'
            '  File "pipeline/pr_creator.py", line 92, in create\n'
            '    _run(["git", "clone", "https://ghp_realtoken123@github.com/org/repo.git"])\n'
            'RuntimeError: Command failed (128): git clone\n'
            'stderr: fatal: Authentication failed for '
            "'https://ghp_realtoken123@github.com/org/repo.git'"
        )
        scrubbed = scrub_secrets(traceback_text)
        assert "ghp_realtoken123" not in scrubbed
        assert "Traceback" in scrubbed  # structure preserved

    def test_slack_error_with_bot_token(self) -> None:
        """Slack API errors sometimes echo the token."""
        error = "invalid_auth: token xoxb-1234567890-1234567890123-abcdefghij is revoked"
        scrubbed = scrub_secrets(error)
        assert "xoxb-" not in scrubbed
        assert "[SLACK_BOT_TOKEN]" in scrubbed

    def test_anthropic_key_in_env_dump(self) -> None:
        """If someone accidentally dumps env vars, the API key must be scrubbed."""
        env_dump = "ANTHROPIC_API_KEY=sk-ant-api03-really-long-secret-key-here\nPATH=/usr/bin"
        scrubbed = scrub_secrets(env_dump)
        assert "sk-ant-" not in scrubbed
        assert "PATH=/usr/bin" in scrubbed

    def test_multiple_different_token_types(self) -> None:
        """Multiple different token types in one string must all be scrubbed."""
        mixed = (
            "bot=xoxb-111-222-abc "
            "app=xapp-1-ABC-xyz "
            "gh=ghp_secrettoken "
            "claude=sk-ant-api03-key"
        )
        scrubbed = scrub_secrets(mixed)
        for prefix in ("xoxb-", "xapp-", "ghp_", "sk-ant-"):
            assert prefix not in scrubbed


# =========================================================================
# Container hardening (REQUIREMENTS: cap_drop, no-new-privileges, limits)
# =========================================================================


class TestContainerHardeningConfig:
    """Verify that WorkerManager passes the right security options to Docker."""

    def test_containers_run_receives_security_options(self, config_with_harness):
        """containers.run must include cap_drop, security_opt, mem_limit, pids_limit."""
        from pipeline.worker_manager import WorkerManager

        with patch("pipeline.worker_manager.docker") as mock_docker:
            mock_client = MagicMock()
            mock_docker.from_env.return_value = mock_client
            container = MagicMock()
            container.id = "abc" + "0" * 61
            mock_client.containers.run.return_value = container
            mock_client.images.get.return_value = MagicMock()

            with patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "test"}):
                wm = WorkerManager(config_with_harness, "test-run")
                wm.start("task")

            kwargs = mock_client.containers.run.call_args[1]
            assert kwargs["cap_drop"] == ["ALL"]
            assert kwargs["security_opt"] == ["no-new-privileges"]
            assert kwargs["mem_limit"] == "2g"
            assert kwargs["pids_limit"] == 256
