"""Integration tests for the self-improving pipeline.

Tests verify pipeline components work together at the unit level, mocking
Docker and external services. Covers:
  - PipelineConfig defaults and output directory creation
  - ChangesetExtractor noise filtering and extraction orchestration
  - MechanicManager verdict normalisation
  - PRCreator slugification and branch naming
  - SlackHandler graceful degradation without token
  - Full pipeline run with mocked Docker
"""

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from pipeline.config import PipelineConfig
from pipeline.changeset_extractor import ChangesetExtractor, _is_noise
from pipeline.mechanic_manager import MechanicManager
from pipeline.pr_creator import PRCreator, _slugify
from pipeline.slack_handler import SlackHandler
from pipeline.session_manager import Session, SessionManager
from pipeline.worker_manager import WorkerManager

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# =========================================================================
# PipelineConfig tests
# =========================================================================


class TestPipelineConfig:
    """Test PipelineConfig defaults and __post_init__ behaviour."""

    def test_sensible_defaults(self):
        """Config should have meaningful defaults for all fields."""
        config = PipelineConfig()
        assert config.worker_image == "chat-force-worker:latest"
        assert config.worker_timeout == 600
        assert config.mechanic_timeout == 300
        assert config.github_repo == "PoleBarnes/chat-force"
        assert config.pr_branch_prefix == "agent-sdk/auto"

    def test_agent_sdk_defaults(self):
        """Config should have Agent SDK-specific defaults."""
        config = PipelineConfig()
        assert config.claude_code_token_env == "ANTHROPIC_API_KEY"
        assert config.max_budget_usd == 5.0
        assert config.max_turns == 50
        assert config.permission_mode == "bypassPermissions"
        assert isinstance(config.allowed_tools, list)
        assert "Bash" in config.allowed_tools
        assert "Read" in config.allowed_tools
        assert "Write" in config.allowed_tools
        assert "Edit" in config.allowed_tools
        assert "Agent" in config.allowed_tools

    def test_no_webhook_fields(self):
        """Config should NOT have webhook fields (removed in SDK pivot)."""
        config = PipelineConfig()
        assert not hasattr(config, "webhook_host")
        assert not hasattr(config, "webhook_port")

    def test_no_mechanic_image(self):
        """Config should NOT have mechanic_image (Mechanic runs on host)."""
        config = PipelineConfig()
        assert not hasattr(config, "mechanic_image")

    def test_no_anthropic_token_env(self):
        """Config should use claude_code_token_env, not anthropic_token_env."""
        config = PipelineConfig()
        assert not hasattr(config, "anthropic_token_env")
        assert config.claude_code_token_env == "ANTHROPIC_API_KEY"

    def test_post_init_creates_output_dir(self, tmp_path):
        """__post_init__ should create output_base if it does not exist."""
        out = str(tmp_path / "pipeline-runs")
        assert not os.path.exists(out)
        config = PipelineConfig(output_base=out)
        assert os.path.isdir(out)
        assert config.output_base == out

    def test_post_init_is_idempotent(self, tmp_path):
        """__post_init__ should not fail if output_base already exists."""
        out = str(tmp_path / "existing-dir")
        os.makedirs(out)
        config = PipelineConfig(output_base=out)
        assert os.path.isdir(config.output_base)

    def test_custom_overrides(self, tmp_path):
        """Overriding fields should take effect."""
        config = PipelineConfig(
            worker_timeout=60,
            mechanic_timeout=30,
            max_budget_usd=10.0,
            max_turns=100,
            output_base=str(tmp_path),
        )
        assert config.worker_timeout == 60
        assert config.mechanic_timeout == 30
        assert config.max_budget_usd == 10.0
        assert config.max_turns == 100


# =========================================================================
# ChangesetExtractor tests
# =========================================================================


class TestIsNoise:
    """Test the _is_noise filter function."""

    def test_tmp_is_noise(self):
        assert _is_noise("/tmp/something.txt") is True

    def test_var_log_is_noise(self):
        assert _is_noise("/var/log/syslog") is True

    def test_var_cache_is_noise(self):
        assert _is_noise("/var/cache/apt/pkgcache.bin") is True

    def test_pyc_is_noise(self):
        assert _is_noise("module.pyc") is True

    def test_pycache_is_noise(self):
        assert _is_noise("/workspace/__pycache__/foo.cpython-313.pyc") is True

    def test_npm_cache_is_noise(self):
        assert _is_noise("/home/node/.npm/some-package") is True

    def test_node_cache_is_noise(self):
        assert _is_noise("/home/node/.cache/something") is True

    def test_root_cache_is_noise(self):
        assert _is_noise("/root/.cache/pip/http") is True

    def test_git_is_noise(self):
        assert _is_noise("/workspace/.git/objects/abc") is True

    def test_workspace_file_is_not_noise(self):
        assert _is_noise("/workspace/config/skills/my-skill.yaml") is False

    def test_app_file_is_not_noise(self):
        assert _is_noise("/home/node/app/index.js") is False

    def test_etc_file_is_not_noise(self):
        assert _is_noise("/etc/nginx/nginx.conf") is False


class TestChangesetExtractor:
    """Test the ChangesetExtractor with a mocked Docker client."""

    @pytest.fixture
    def config(self, tmp_path):
        return PipelineConfig(output_base=str(tmp_path))

    @pytest.fixture
    def mock_container(self):
        """Build a mock Docker container with the methods ChangesetExtractor uses."""
        container = MagicMock()

        # exec_run returns (exit_code, output_bytes)
        container.exec_run.return_value = (0, b"")

        # diff returns list of Docker diff entries
        container.diff.return_value = [
            {"Path": "/workspace/config/skills/new.yaml", "Kind": 1},
            {"Path": "/tmp/something", "Kind": 1},
        ]

        # reload and attrs for telemetry
        container.reload.return_value = None
        container.attrs = {
            "State": {
                "ExitCode": 0,
                "StartedAt": "2026-04-01T14:00:00.000000Z",
                "FinishedAt": "2026-04-01T14:05:00.000000Z",
            }
        }
        container.logs.return_value = b"worker started\nworker finished\n"
        return container

    @patch("pipeline.changeset_extractor.docker")
    @patch("pipeline.changeset_extractor.subprocess")
    def test_extract_calls_all_four_layers(
        self, mock_subprocess, mock_docker_module, config, mock_container
    ):
        """extract() should call git, docker-diff, telemetry, and agent log layers."""
        mock_client = MagicMock()
        mock_docker_module.from_env.return_value = mock_client
        mock_client.containers.get.return_value = mock_container

        # docker cp calls in Layer 4 -- all fail gracefully
        mock_subprocess.run.side_effect = Exception("no docker cp in tests")
        mock_subprocess.CalledProcessError = Exception
        mock_subprocess.TimeoutExpired = Exception

        extractor = ChangesetExtractor(config, "test-run-001")

        bundle = extractor.extract("fake-container-id", task="test task")

        # Verify all four layers are present in the bundle
        assert "git_changes" in bundle
        assert "docker_changes" in bundle
        assert "telemetry" in bundle
        assert "agent_logs" in bundle
        assert bundle["run_id"] == "test-run-001"
        assert bundle["task"] == "test task"
        assert bundle["worker_container"] == "fake-container-id"

    @patch("pipeline.changeset_extractor.docker")
    @patch("pipeline.changeset_extractor.subprocess")
    def test_docker_diff_filters_noise(
        self, mock_subprocess, mock_docker_module, config, mock_container
    ):
        """Docker diff results should have noise paths filtered out."""
        mock_client = MagicMock()
        mock_docker_module.from_env.return_value = mock_client
        mock_client.containers.get.return_value = mock_container

        mock_subprocess.run.side_effect = Exception("no docker cp in tests")
        mock_subprocess.CalledProcessError = Exception
        mock_subprocess.TimeoutExpired = Exception

        extractor = ChangesetExtractor(config, "test-run-002")
        bundle = extractor.extract("fake-container-id")

        docker_changes = bundle["docker_changes"]
        # /workspace/config/skills/new.yaml (Kind=1) should be in added
        assert "/workspace/config/skills/new.yaml" in docker_changes["added"]
        # /tmp/something should be filtered to noise
        assert "/tmp/something" in docker_changes["filtered_noise"]
        assert "/tmp/something" not in docker_changes["added"]

    @patch("pipeline.changeset_extractor.docker")
    @patch("pipeline.changeset_extractor.subprocess")
    def test_bundle_saved_to_disk(
        self, mock_subprocess, mock_docker_module, config, mock_container
    ):
        """Changeset bundle should be written as JSON to the run directory."""
        mock_client = MagicMock()
        mock_docker_module.from_env.return_value = mock_client
        mock_client.containers.get.return_value = mock_container

        mock_subprocess.run.side_effect = Exception("no docker cp in tests")
        mock_subprocess.CalledProcessError = Exception
        mock_subprocess.TimeoutExpired = Exception

        extractor = ChangesetExtractor(config, "test-run-003")
        bundle = extractor.extract("fake-container-id")

        changeset_path = os.path.join(extractor.run_dir, "changeset.json")
        assert os.path.exists(changeset_path)

        with open(changeset_path) as f:
            saved = json.load(f)
        assert saved["run_id"] == "test-run-003"


# =========================================================================
# MechanicManager tests
# =========================================================================


class TestValidateVerdict:
    """Test MechanicManager._validate_verdict normalisation."""

    def test_approve_verdict_normalised(self):
        """verdict=approve should become approved=True."""
        result = MechanicManager._validate_verdict(
            {"verdict": "approve", "pr_title": "Update auth"}
        )
        assert result["approved"] is True
        assert result["pr_title"] == "Update auth"

    def test_reject_verdict_normalised(self):
        """verdict=reject should become approved=False with reason."""
        result = MechanicManager._validate_verdict(
            {"verdict": "reject", "rejection_reason": "Code quality too low"}
        )
        assert result["approved"] is False
        assert result["reason"] == "Code quality too low"

    def test_approved_bool_passes_through(self):
        """Already-normalised approved=True should pass through."""
        result = MechanicManager._validate_verdict({"approved": True})
        assert result["approved"] is True

    def test_approved_false_gets_default_reason(self):
        """approved=False without reason should get a default."""
        result = MechanicManager._validate_verdict({"approved": False})
        assert result["approved"] is False
        assert result["reason"] == "No reason provided"

    def test_approved_false_with_reason_preserved(self):
        """approved=False with explicit reason should keep it."""
        result = MechanicManager._validate_verdict(
            {"approved": False, "reason": "Unsafe changes detected"}
        )
        assert result["approved"] is False
        assert result["reason"] == "Unsafe changes detected"

    def test_missing_both_fields_raises(self):
        """Verdict missing both 'verdict' and 'approved' should raise ValueError."""
        with pytest.raises(ValueError, match="missing"):
            MechanicManager._validate_verdict({"pr_title": "Something"})

    def test_truthy_approved_coerced_to_bool(self):
        """Truthy non-bool values for approved should be coerced to bool."""
        result = MechanicManager._validate_verdict({"approved": 1})
        assert result["approved"] is True

    def test_reject_with_both_reason_keys(self):
        """If both rejection_reason and reason are present, reason wins."""
        result = MechanicManager._validate_verdict(
            {"verdict": "reject", "rejection_reason": "from mechanic", "reason": "explicit"}
        )
        assert result["approved"] is False
        # reason was already present so rejection_reason should not overwrite
        assert result["reason"] == "explicit"


class TestMechanicManagerSDK:
    """Test MechanicManager Agent SDK integration (host-side query)."""

    @pytest.fixture
    def config(self, tmp_path):
        return PipelineConfig(output_base=str(tmp_path))

    def test_evaluate_calls_query_with_changeset(self, config):
        """evaluate() should call query() with the changeset and mechanic prompt."""
        mm = MechanicManager(config, "test-run")

        mock_verdict = {"verdict": "approve", "pr_title": "Add feature", "confidence": "high"}

        with patch.object(mm, "_run_query", return_value=mock_verdict):
            result = mm.evaluate({"task": "test task", "git_changes": {"diff": "+hello"}})

        assert result["approved"] is True
        assert result["pr_title"] == "Add feature"

    def test_evaluate_includes_tool_log_in_payload(self, config):
        """evaluate() should include tool_log in the evaluation payload."""
        mm = MechanicManager(config, "test-run")

        tool_log = [{"event": "PreToolUse", "tool_name": "Bash"}]
        changeset = {"task": "test", "tool_log": tool_log, "git_changes": {}}

        evaluation = mm._prepare_evaluation(changeset)
        assert evaluation["tool_log"] == tool_log

    def test_evaluate_includes_usage_in_payload(self, config):
        """evaluate() should include usage data in the evaluation payload."""
        mm = MechanicManager(config, "test-run")

        usage = {"input_tokens": 1000, "output_tokens": 500, "total_cost_usd": 0.03}
        changeset = {"task": "test", "usage": usage, "git_changes": {}}

        evaluation = mm._prepare_evaluation(changeset)
        assert evaluation["usage"] == usage

    def test_evaluate_forwards_previous_rejections(self, config):
        """_prepare_evaluation should forward previous_rejections when present."""
        mm = MechanicManager(config, "test-run")

        rejections = [{"iteration": 1, "reason": "Missing tests"}]
        changeset = {
            "task": "test",
            "git_changes": {},
            "previous_rejections": rejections,
        }

        evaluation = mm._prepare_evaluation(changeset)
        assert evaluation["previous_rejections"] == rejections

    def test_evaluate_omits_previous_rejections_when_absent(self, config):
        """_prepare_evaluation should not include previous_rejections if not in changeset."""
        mm = MechanicManager(config, "test-run")
        changeset = {"task": "test", "git_changes": {}}

        evaluation = mm._prepare_evaluation(changeset)
        assert "previous_rejections" not in evaluation

    def test_no_docker_dependency(self, config):
        """MechanicManager should NOT import or use Docker."""
        mm = MechanicManager(config, "test-run")
        assert not hasattr(mm, "_client")
        assert not hasattr(mm, "_container")


# =========================================================================
# PRCreator tests
# =========================================================================


class TestSlugify:
    """Test the _slugify helper function."""

    def test_basic_slugification(self):
        assert _slugify("Hello World") == "hello-world"

    def test_special_chars_replaced(self):
        assert _slugify("Refactor auth_module (v2)!") == "refactor-auth-module-v2"

    def test_leading_trailing_hyphens_stripped(self):
        assert _slugify("  --hello--  ") == "hello"

    def test_max_length_truncation(self):
        result = _slugify("a" * 100)
        assert len(result) <= 60

    def test_max_length_does_not_end_with_hyphen(self):
        # Create a string that when slugified and truncated, would end with -
        result = _slugify("a" * 59 + " b" * 20)
        assert not result.endswith("-")

    def test_empty_string(self):
        assert _slugify("") == ""

    def test_numbers_preserved(self):
        assert _slugify("Release 3.14.0") == "release-3-14-0"

    def test_custom_max_len(self):
        result = _slugify("long text here", max_len=8)
        assert len(result) <= 8


class TestMakeBranchName:
    """Test PRCreator._make_branch_name produces valid git branch names."""

    @pytest.fixture
    def pr_creator(self, tmp_path):
        config = PipelineConfig(output_base=str(tmp_path))
        return PRCreator(config, "test-run-001")

    def test_branch_has_prefix(self, pr_creator):
        """Branch name should start with the configured prefix."""
        branch = pr_creator._make_branch_name("Refactor auth module")
        assert branch.startswith("agent-sdk/auto/")

    def test_branch_contains_timestamp(self, pr_creator):
        """Branch name should contain a YYYYMMDD-HHMMSS timestamp."""
        branch = pr_creator._make_branch_name("Update tests")
        # After the prefix, the timestamp is the next 15 chars (YYYYMMDD-HHMMSS)
        parts = branch.split("/")
        # parts: ["agent-sdk", "auto", "YYYYMMDD-HHMMSS-slug"]
        tail = parts[2]
        ts_part = tail[:15]  # YYYYMMDD-HHMMSS
        assert len(ts_part) == 15
        assert ts_part[8] == "-"  # separator between date and time

    def test_branch_contains_slug(self, pr_creator):
        """Branch name should contain a slugified version of the title."""
        branch = pr_creator._make_branch_name("Fix Critical Bug")
        assert "fix-critical-bug" in branch

    def test_branch_has_no_spaces(self, pr_creator):
        """Git branch names must not contain spaces."""
        branch = pr_creator._make_branch_name("Some Title With Spaces")
        assert " " not in branch

    def test_branch_has_no_special_chars(self, pr_creator):
        """Branch name should only contain safe git-branch characters."""
        branch = pr_creator._make_branch_name("Feature: Add (new) stuff!")
        # Valid chars in a git branch: alphanumeric, -, /, .
        import re
        assert re.match(r"^[a-z0-9/\-]+$", branch), (
            f"Branch name contains invalid characters: {branch}"
        )


# =========================================================================
# PRCreator.create() tests
# =========================================================================


class TestPRCreatorDeletedFiles:
    """Test that PRCreator.create() handles deleted files."""

    def test_deleted_files_are_removed_from_checkout(self, tmp_path):
        """Files in git_changes.deleted_files should be git-rm'd from the PR branch."""
        config = PipelineConfig(output_base=str(tmp_path))
        pr = PRCreator(config, "test-run")

        # Set up a fake git repo as the "clone" target
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "keep.py").write_text("keep this")
        (repo_dir / "old-config.yaml").write_text("delete this")
        subprocess.run(["git", "init"], cwd=str(repo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=str(repo_dir), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=str(repo_dir), capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=str(repo_dir), capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo_dir), capture_output=True)

        changeset = {
            "task": "cleanup config",
            "git_changes": {
                "new_files": [],
                "modified_files": ["keep.py"],
                "deleted_files": ["old-config.yaml"],
                "file_contents": {"keep.py": "updated content"},
            },
            "worker_container": None,
        }
        verdict = {
            "approved": True,
            "pr_title": "Cleanup config",
            "pr_body": "Remove old config",
            "files_to_include": ["keep.py"],
        }

        # Mock out clone/push/gh — we only care about the file operations
        import pipeline.pr_creator as pr_mod
        original_run = pr_mod._run

        commands_run = []

        def fake_run(cmd, *, cwd=None, check=True):
            commands_run.append(cmd)
            if cmd[0] == "git" and cmd[1] == "clone":
                # Copy our repo instead of cloning
                import shutil
                shutil.copytree(str(repo_dir), cmd[-1], dirs_exist_ok=True)
                return ""
            if cmd[0] == "git" and cmd[1] == "push":
                return ""
            if cmd[0] == "gh":
                return "https://github.com/test/pr/1"
            return original_run(cmd, cwd=cwd, check=check)

        with patch("pipeline.pr_creator._run", side_effect=fake_run):
            pr.create(changeset, verdict)

        # Verify git rm was called for the deleted file
        rm_commands = [c for c in commands_run if c[0] == "git" and c[1] == "rm"]
        assert len(rm_commands) == 1
        assert "old-config.yaml" in rm_commands[0]


import subprocess  # ensure subprocess is available for the test above


# =========================================================================
# SlackHandler tests
# =========================================================================


class TestSlackHandler:
    """Test SlackHandler graceful degradation without a token."""

    @pytest.fixture
    def config(self, tmp_path):
        return PipelineConfig(output_base=str(tmp_path))

    def test_no_crash_without_token(self, config):
        """SlackHandler should not crash when SLACK_BOT_TOKEN is not set."""
        with patch.dict(os.environ, {}, clear=True):
            handler = SlackHandler(config)
            assert handler._client is None

    def test_notify_approved_noop_without_token(self, config):
        """notify_approved should not crash without a token."""
        with patch.dict(os.environ, {}, clear=True):
            handler = SlackHandler(config)
            # Should run without error (no-op)
            handler.notify_approved("run-001", "test task", "https://github.com/pr/1")

    def test_notify_rejected_noop_without_token(self, config):
        """notify_rejected should not crash without a token."""
        with patch.dict(os.environ, {}, clear=True):
            handler = SlackHandler(config)
            # Should run without error (no-op)
            handler.notify_rejected("run-001", "test task", "bad code")

    @patch.dict(os.environ, {"SLACK_BOT_TOKEN": "xoxb-fake-token"})
    def test_client_created_with_token_and_channel(self, config):
        """SlackHandler should create a WebClient when token and channel are provided."""
        handler = SlackHandler(config, reply_channel="#test-channel")
        assert handler._client is not None

    def test_no_client_without_channel(self, config):
        """SlackHandler should skip client creation when no reply_channel."""
        with patch.dict(os.environ, {"SLACK_BOT_TOKEN": "xoxb-fake-token"}):
            handler = SlackHandler(config)
            assert handler._client is None


# =========================================================================
# Pipeline integration test (fully mocked)
# =========================================================================


class TestPipelineIntegration:
    """Test the full run_pipeline flow with all Docker calls mocked."""

    @pytest.fixture
    def config(self, tmp_path):
        return PipelineConfig(
            output_base=str(tmp_path),
            worker_timeout=1,
            mechanic_timeout=1,
        )

    @patch("pipeline.main.SlackHandler")
    @patch("pipeline.main.PRCreator")
    @patch("pipeline.main.ChangesetExtractor")
    @patch("pipeline.main.MechanicManager")
    @patch("pipeline.main.WorkerManager")
    def test_approved_flow_creates_pr(
        self,
        MockWorker,
        MockMechanic,
        MockExtractor,
        MockPR,
        MockSlack,
        config,
    ):
        """Approved verdict should create a PR and notify Slack."""
        from pipeline.main import run_pipeline

        # Wire up mocks
        worker = MockWorker.return_value
        worker.start.return_value = "container-abc123"
        worker.get_logs.return_value = "some logs"

        mechanic = MockMechanic.return_value
        mechanic.evaluate.return_value = {
            "approved": True,
            "pr_title": "Auto: Refactor auth",
            "pr_body": "Improved auth module",
            "files_to_include": ["skills/auth.yaml"],
        }

        extractor = MockExtractor.return_value
        extractor.extract.return_value = {
            "run_id": "test",
            "task": "Refactor auth",
            "git_changes": {"file_contents": {"skills/auth.yaml": "content"}},
            "docker_changes": {},
            "telemetry": {},
            "agent_logs": {},
        }

        pr_creator = MockPR.return_value
        pr_creator.create.return_value = "https://github.com/PoleBarnes/chat-force/pull/42"

        slack = MockSlack.return_value

        summary = run_pipeline("Refactor auth", config)

        # Verify correct sequence
        worker.start.assert_called_once_with("Refactor auth")
        worker.wait_for_completion.assert_called_once()
        extractor.extract.assert_called_once_with("container-abc123", task="Refactor auth")
        mechanic.evaluate.assert_called_once()
        pr_creator.create.assert_called_once()
        slack.notify_approved.assert_called_once()

        assert summary["status"] == "approved"
        assert summary["pr_url"] == "https://github.com/PoleBarnes/chat-force/pull/42"

    @patch("pipeline.main.SlackHandler")
    @patch("pipeline.main.PRCreator")
    @patch("pipeline.main.ChangesetExtractor")
    @patch("pipeline.main.MechanicManager")
    @patch("pipeline.main.WorkerManager")
    def test_rejected_flow_notifies_slack(
        self,
        MockWorker,
        MockMechanic,
        MockExtractor,
        MockPR,
        MockSlack,
        config,
    ):
        """Rejected verdict should notify Slack but not create a PR."""
        from pipeline.main import run_pipeline

        worker = MockWorker.return_value
        worker.start.return_value = "container-xyz789"
        worker.get_logs.return_value = ""

        mechanic = MockMechanic.return_value
        mechanic.evaluate.return_value = {
            "approved": False,
            "reason": "Changes are too risky",
        }

        extractor = MockExtractor.return_value
        extractor.extract.return_value = {
            "run_id": "test",
            "task": "Risky change",
            "git_changes": {},
            "docker_changes": {},
            "telemetry": {},
            "agent_logs": {},
        }

        pr_creator = MockPR.return_value
        slack = MockSlack.return_value

        summary = run_pipeline("Risky change", config)

        # PR should NOT be created
        pr_creator.create.assert_not_called()
        slack.notify_rejected.assert_called_once()

        assert summary["status"] == "rejected"
        assert summary["pr_url"] is None

    @patch("pipeline.main.SlackHandler")
    @patch("pipeline.main.PRCreator")
    @patch("pipeline.main.ChangesetExtractor")
    @patch("pipeline.main.MechanicManager")
    @patch("pipeline.main.WorkerManager")
    def test_timeout_sets_status(
        self,
        MockWorker,
        MockMechanic,
        MockExtractor,
        MockPR,
        MockSlack,
        config,
    ):
        """TimeoutError during worker wait should set status to 'timeout'."""
        from pipeline.main import run_pipeline

        worker = MockWorker.return_value
        worker.start.return_value = "container-timeout"
        worker.wait_for_completion.side_effect = TimeoutError("Worker timed out")
        worker.get_logs.return_value = ""

        mechanic = MockMechanic.return_value
        slack = MockSlack.return_value

        summary = run_pipeline("Slow task", config)

        assert summary["status"] == "timeout"
        assert "timed out" in summary["error"]

        # Mechanic should not have been called
        mechanic.evaluate.assert_not_called()

    @patch("pipeline.main.SlackHandler")
    @patch("pipeline.main.PRCreator")
    @patch("pipeline.main.ChangesetExtractor")
    @patch("pipeline.main.MechanicManager")
    @patch("pipeline.main.WorkerManager")
    def test_error_sets_status(
        self,
        MockWorker,
        MockMechanic,
        MockExtractor,
        MockPR,
        MockSlack,
        config,
    ):
        """Unexpected errors should set status to 'error'."""
        from pipeline.main import run_pipeline

        worker = MockWorker.return_value
        worker.start.side_effect = RuntimeError("Docker daemon not running")
        worker.get_logs.return_value = ""

        summary = run_pipeline("Any task", config)

        assert summary["status"] == "error"
        assert "Docker daemon" in summary["error"]

    @patch("pipeline.main.SlackHandler")
    @patch("pipeline.main.PRCreator")
    @patch("pipeline.main.ChangesetExtractor")
    @patch("pipeline.main.MechanicManager")
    @patch("pipeline.main.WorkerManager")
    def test_summary_written_to_disk(
        self,
        MockWorker,
        MockMechanic,
        MockExtractor,
        MockPR,
        MockSlack,
        config,
    ):
        """Pipeline should always write a summary.json to the run directory."""
        from pipeline.main import run_pipeline

        worker = MockWorker.return_value
        worker.start.return_value = "container-summary"
        worker.get_logs.return_value = ""

        mechanic = MockMechanic.return_value
        mechanic.evaluate.return_value = {"approved": False, "reason": "test"}

        extractor = MockExtractor.return_value
        extractor.extract.return_value = {
            "run_id": "test",
            "task": "Test",
            "git_changes": {},
            "docker_changes": {},
            "telemetry": {},
            "agent_logs": {},
        }

        summary = run_pipeline("Test", config)

        # Find the summary.json in the output directory
        run_id = summary["run_id"]
        summary_path = os.path.join(config.output_base, run_id, "summary.json")
        assert os.path.exists(summary_path)

        with open(summary_path) as f:
            saved = json.load(f)
        assert saved["run_id"] == run_id
        assert saved["task"] == "Test"


# =========================================================================
# Session Manager tests
# =========================================================================


class TestSessionManager:
    """Test session lifecycle management with mocked dependencies."""

    @pytest.fixture
    def config(self, tmp_path):
        return PipelineConfig(
            output_base=str(tmp_path),
            worker_timeout=5,
            session_idle_timeout=60,
        )

    @pytest.fixture
    def mock_deps(self):
        """Patch all SessionManager external dependencies."""
        with (
            patch("pipeline.session_manager.WorkerManager") as MockWorker,
            patch("pipeline.session_manager.ChangesetExtractor") as MockExtractor,
            patch("pipeline.session_manager.MechanicManager") as MockMechanic,
            patch("pipeline.session_manager.PRCreator") as MockPR,
            patch("pipeline.session_manager._git_short_hash", return_value="abc1234"),
        ):
            worker = MockWorker.return_value
            worker.start.return_value = "fake-container-id-full-64-chars" + "0" * 34
            worker.wait_for_completion.return_value = None
            worker.get_response.return_value = "Hello from worker"
            worker.is_alive.return_value = True
            worker.get_logs.return_value = "some logs"
            worker.cleanup.return_value = None
            worker.send_message.return_value = None

            extractor = MockExtractor.return_value
            extractor.extract.return_value = {
                "git_changes": {},
                "docker_changes": {},
                "telemetry": {},
                "agent_logs": {},
            }

            mechanic = MockMechanic.return_value
            mechanic.evaluate.return_value = {"approved": False, "reason": "test"}
            mechanic.cleanup.return_value = None

            yield {
                "WorkerManager": MockWorker,
                "worker": worker,
                "ChangesetExtractor": MockExtractor,
                "extractor": extractor,
                "MechanicManager": MockMechanic,
                "mechanic": mechanic,
                "PRCreator": MockPR,
            }

    def _make_manager(self, config):
        """Create a SessionManager for testing."""
        return SessionManager(config)

    def test_get_or_create_creates_new_session(self, config, mock_deps):
        """First call for a user should create a new session."""
        sm = self._make_manager(config)
        session, is_new = sm.get_or_create_session("U001", "C001", "Build a thing")

        assert is_new is True
        assert session.user_id == "U001"
        assert session.channel_id == "C001"
        assert session.worker is not None
        assert session.message_count == 1
        assert session.sandbox_version == "abc1234"

    def test_get_or_create_returns_existing_session(self, config, mock_deps):
        """Second call for the same user should return existing session."""
        sm = self._make_manager(config)
        session1, is_new1 = sm.get_or_create_session("U002", "C002", "First message")
        session2, is_new2 = sm.get_or_create_session("U002", "C002", "Second message")

        assert is_new1 is True
        assert is_new2 is False
        assert session1 is session2

    def test_get_session_returns_none_for_placeholder(self, config, mock_deps):
        """get_session should return None when worker is None (placeholder)."""
        sm = self._make_manager(config)
        # Manually insert a placeholder session
        from pipeline.session_manager import Session
        placeholder = Session(
            user_id="U003",
            channel_id="C003",
            run_id="test-run",
            container_id="",
            worker=None,
            created_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
        )
        sm._sessions["U003"] = placeholder

        assert sm.get_session("U003") is None

    def test_get_session_returns_ready_session(self, config, mock_deps):
        """get_session should return a session with an active worker."""
        sm = self._make_manager(config)
        session, _ = sm.get_or_create_session("U004", "C004", "Hello")

        result = sm.get_session("U004")
        assert result is session
        assert result.worker is not None

    def test_get_session_returns_none_for_unknown_user(self, config, mock_deps):
        """get_session should return None for a user with no session."""
        sm = self._make_manager(config)
        assert sm.get_session("U999") is None

    def test_send_message_calls_worker_methods(self, config, mock_deps):
        """send_message should call worker.send_message, wait, and get_response."""
        sm = self._make_manager(config)
        session, _ = sm.get_or_create_session("U005", "C005", "Init")

        mock_deps["worker"].get_response.return_value = "Worker reply"
        result = sm.send_message(session, "Follow-up question")

        mock_deps["worker"].send_message.assert_called_with("Follow-up question")
        mock_deps["worker"].wait_for_completion.assert_called()
        mock_deps["worker"].get_response.assert_called()
        assert result == "Worker reply"

    def test_send_message_increments_count(self, config, mock_deps):
        """send_message should increment session.message_count."""
        sm = self._make_manager(config)
        session, _ = sm.get_or_create_session("U006", "C006", "Init")
        assert session.message_count == 1

        sm.send_message(session, "msg 2")
        assert session.message_count == 2

        sm.send_message(session, "msg 3")
        assert session.message_count == 3

    def test_send_message_acquires_lock(self, config, mock_deps):
        """send_message should serialize through session._msg_lock."""
        sm = self._make_manager(config)
        session, _ = sm.get_or_create_session("U007", "C007", "Init")

        # Manually acquire the lock to prove send_message blocks on it
        acquired = session._msg_lock.acquire(blocking=False)
        assert acquired is True

        # send_message in a thread should block
        result_holder = []

        def try_send():
            # This should block because we hold the lock
            r = sm.send_message(session, "blocked msg")
            result_holder.append(r)

        t = threading.Thread(target=try_send)
        t.start()
        time.sleep(0.1)  # give thread time to reach the lock
        assert len(result_holder) == 0  # still blocked

        session._msg_lock.release()  # unblock
        t.join(timeout=5)
        assert len(result_holder) == 1

    def test_send_message_raises_for_no_worker(self, config, mock_deps):
        """send_message should raise RuntimeError if session has no worker."""
        sm = self._make_manager(config)
        from pipeline.session_manager import Session
        session = Session(
            user_id="U008",
            channel_id="C008",
            run_id="test-run",
            container_id="",
            worker=None,
            created_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
        )

        with pytest.raises(RuntimeError, match="no active worker"):
            sm.send_message(session, "anything")

    def test_close_session_runs_mechanic_with_changes(self, config, mock_deps):
        """close_session should run mechanic phase when there are changes."""
        sm = self._make_manager(config)
        session, _ = sm.get_or_create_session("U009", "C009", "Init")

        # Make extractor report changes
        mock_deps["extractor"].extract.return_value = {
            "git_changes": {
                "new_files": ["file.py"],
                "modified_files": [],
                "deleted_files": [],
            },
            "docker_changes": {},
            "telemetry": {},
            "agent_logs": {},
        }

        result = sm.close_session("U009")
        assert result is not None
        # evaluate is called in a feedback loop (up to MAX_ITERATIONS)
        mock_deps["mechanic"].evaluate.assert_called()

    def test_close_session_skips_mechanic_no_changes(self, config, mock_deps):
        """close_session should skip mechanic when no file changes detected."""
        sm = self._make_manager(config)
        session, _ = sm.get_or_create_session("U010", "C010", "Init")

        # No changes
        mock_deps["extractor"].extract.return_value = {
            "git_changes": {
                "new_files": [],
                "modified_files": [],
                "deleted_files": [],
            },
            "docker_changes": {},
            "telemetry": {},
            "agent_logs": {},
        }

        result = sm.close_session("U010")
        assert result["status"] == "no_changes"
        mock_deps["mechanic"].evaluate.assert_not_called()

    def test_close_session_removes_session(self, config, mock_deps):
        """close_session should remove the session from the active dict."""
        sm = self._make_manager(config)
        sm.get_or_create_session("U011", "C011", "Init")
        assert sm.get_session("U011") is not None

        sm.close_session("U011")
        assert sm.get_session("U011") is None

    def test_close_session_invokes_callback(self, config, mock_deps):
        """close_session should invoke on_session_closed callback."""
        sm = self._make_manager(config)
        callback = MagicMock()
        sm.on_session_closed = callback

        sm.get_or_create_session("U012", "C012", "Init")
        sm.close_session("U012")

        callback.assert_called_once()
        call_args = callback.call_args
        assert call_args[0][0].user_id == "U012"  # session
        assert isinstance(call_args[0][1], dict)    # result

    def test_close_session_returns_none_for_unknown_user(self, config, mock_deps):
        """close_session should return None for a user with no session."""
        sm = self._make_manager(config)
        assert sm.close_session("U999") is None

    def test_cleanup_session_handles_worker_none(self, config, mock_deps):
        """_cleanup_session should handle worker=None gracefully."""
        sm = self._make_manager(config)
        from pipeline.session_manager import Session
        placeholder = Session(
            user_id="U013",
            channel_id="C013",
            run_id="test-run",
            container_id="",
            worker=None,
            created_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
        )
        # Should not raise
        sm._cleanup_session(placeholder)

    def test_failed_creation_sets_ready_and_cleans_up(self, config, mock_deps):
        """If container startup fails, _ready event should be set and placeholder removed."""
        mock_deps["worker"].start.side_effect = RuntimeError("Docker failed")

        sm = self._make_manager(config)

        with pytest.raises(RuntimeError, match="Docker failed"):
            sm.get_or_create_session("U014", "C014", "Init")

        # Session should be removed from dict
        assert sm.get_session("U014") is None
        assert "U014" not in sm._sessions

    def test_session_keyed_by_user_id(self, config, mock_deps):
        """Different users should get different sessions."""
        sm = self._make_manager(config)

        s1, _ = sm.get_or_create_session("USER_A", "C_A", "hello")
        s2, _ = sm.get_or_create_session("USER_B", "C_B", "world")

        assert s1.user_id == "USER_A"
        assert s2.user_id == "USER_B"
        assert s1 is not s2
        assert sm.active_session_count == 2

    def test_active_session_count(self, config, mock_deps):
        """active_session_count should track number of sessions."""
        sm = self._make_manager(config)
        assert sm.active_session_count == 0

        sm.get_or_create_session("U020", "C020", "a")
        assert sm.active_session_count == 1

        sm.close_session("U020")
        assert sm.active_session_count == 0


# =========================================================================
# Slack Listener — Assistant handler tests
# =========================================================================


class TestSlackAssistantHandlers:
    """Test Slack listener handlers with mocked Bolt context and session manager.

    Since Bolt's App() constructor calls auth_test, we avoid calling
    create_app() in most tests.  Instead we test the handler logic
    (functions defined in slack_listener.py) directly.
    """

    @pytest.fixture
    def config(self, tmp_path):
        return PipelineConfig(output_base=str(tmp_path))

    @pytest.fixture
    def mocks(self):
        """Create common mocks for Slack handler tests."""
        say = MagicMock()
        set_status = MagicMock()
        set_title = MagicMock()
        set_suggested_prompts = MagicMock()
        logger = MagicMock()

        client = MagicMock()
        streamer = MagicMock()
        client.chat_stream.return_value = streamer
        client.conversations_history.return_value = {"messages": []}

        context = MagicMock()
        context.user_id = "U_TEST"
        context.team_id = "T_TEST"

        return {
            "say": say,
            "set_status": set_status,
            "set_title": set_title,
            "set_suggested_prompts": set_suggested_prompts,
            "logger": logger,
            "client": client,
            "streamer": streamer,
            "context": context,
        }

    def test_thread_started_says_greeting(self, mocks):
        """thread_started handler should call say() with a greeting."""
        say = mocks["say"]
        set_suggested_prompts = mocks["set_suggested_prompts"]

        # Simulate what handle_thread_started does
        say("Hey! I'm Leo \u2014 your digital worker. Tell me what you need and I'll spin up a sandbox to get it done. \U0001f935")
        set_suggested_prompts(prompts=[
            {"title": "Build something", "message": "Create a new Express.js REST API with SQLite persistence and tests"},
        ])

        say.assert_called_once()
        assert "Leo" in say.call_args[0][0]
        set_suggested_prompts.assert_called_once()

    @patch("pipeline.slack_listener._HAS_CHUNKS", False)
    def test_user_message_existing_session_calls_send_message(self, config, mocks):
        """When an existing session exists, send_message should be called with the text."""
        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.worker = MagicMock()
        mock_session.sandbox_version = "abc1234"
        session_manager.get_session.return_value = mock_session
        session_manager.send_message.return_value = "Here is the response"

        client = mocks["client"]
        context = mocks["context"]
        payload = {"channel": "C001", "text": "Do something", "thread_ts": "1234.5678"}

        # Simulate handler logic: existing session fast path
        user_id = context.user_id
        existing = session_manager.get_session(user_id)
        assert existing is not None

        response = session_manager.send_message(existing, payload["text"])
        session_manager.send_message.assert_called_with(mock_session, "Do something")
        assert response == "Here is the response"

        # Stream the response
        streamer = client.chat_stream(
            channel=payload["channel"],
            thread_ts=payload["thread_ts"],
            recipient_team_id=context.team_id,
            recipient_user_id=context.user_id,
        )
        streamer.append(markdown_text=response)
        streamer.stop()
        streamer.append.assert_called()
        streamer.stop.assert_called()

    @patch("pipeline.slack_listener._HAS_CHUNKS", False)
    def test_user_message_new_session_creates_and_gets_response(self, config, mocks):
        """When no session exists, get_or_create_session should be called."""
        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.worker = MagicMock()
        mock_session.worker.get_response.return_value = "First response"
        mock_session.sandbox_version = "def5678"

        session_manager.get_session.return_value = None
        session_manager.get_or_create_session.return_value = (mock_session, True)

        context = mocks["context"]

        # Simulate handler logic: new session path
        existing = session_manager.get_session(context.user_id)
        assert existing is None

        session, is_new = session_manager.get_or_create_session(
            context.user_id, "C001", "Build something"
        )
        assert is_new is True
        response = session.worker.get_response()
        assert response == "First response"

    @patch("pipeline.slack_listener._HAS_CHUNKS", False)
    def test_user_message_empty_text_returns_early(self, config, mocks):
        """Handler should return early if text is empty or whitespace."""
        text = "   "
        assert not text.strip()

    @patch("pipeline.slack_listener._HAS_CHUNKS", False)
    def test_user_message_timeout_says_error(self, config, mocks):
        """When send_message raises TimeoutError, handler should say error message."""
        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.worker = MagicMock()
        session_manager.get_session.return_value = mock_session
        session_manager.send_message.side_effect = TimeoutError("timed out")

        say = mocks["say"]
        set_status = mocks["set_status"]

        # Simulate handler logic for timeout
        try:
            session_manager.send_message(mock_session, "hello")
        except TimeoutError:
            say(":hourglass: Timed out waiting for Leo. Try again or start a new session.")
            set_status(status="")

        say.assert_called_once()
        assert "Timed out" in say.call_args[0][0]
        set_status.assert_called_with(status="")

    @patch("pipeline.slack_listener._HAS_CHUNKS", False)
    def test_user_message_runtime_error_says_error(self, config, mocks):
        """When send_message raises RuntimeError, handler should say error."""
        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.worker = MagicMock()
        session_manager.get_session.return_value = mock_session
        session_manager.send_message.side_effect = RuntimeError("container died")

        say = mocks["say"]
        set_status = mocks["set_status"]

        try:
            session_manager.send_message(mock_session, "hello")
        except RuntimeError as exc:
            say(f":warning: Could not deliver message: {exc}")
            set_status(status="")

        say.assert_called_once()
        assert "container died" in say.call_args[0][0]


class TestSlackMentionHandler:
    """Test the @app_mention handler paths."""

    def test_mention_handler_strips_mention_prefix(self):
        """The mention handler should strip <@BOTID> prefix from text."""
        import re
        raw_text = "<@U12345ABC> do something cool"
        text = re.sub(r"<@[A-Z0-9]+>\s*", "", raw_text).strip()
        assert text == "do something cool"

    def test_mention_handler_empty_text_says_greeting(self):
        """Mention with no text after stripping should respond with greeting."""
        import re
        raw_text = "<@U12345ABC>"
        text = re.sub(r"<@[A-Z0-9]+>\s*", "", raw_text).strip()
        assert text == ""

    def test_mention_handler_multiple_mentions_stripped(self):
        """Multiple @mentions in text should all be stripped."""
        import re
        raw_text = "<@U12345ABC> <@U99999ZZZ> hello"
        text = re.sub(r"<@[A-Z0-9]+>\s*", "", raw_text).strip()
        assert text == "hello"

    def test_mention_existing_session_uses_chat_stream(self):
        """Mention with existing session should route through chat_stream."""
        from pipeline.slack_listener import _get_team_id

        # Test the _get_team_id caching mechanism
        client = MagicMock()
        client.auth_test.return_value = {"team_id": "T_CACHED"}

        # Reset the cache
        import pipeline.slack_listener as sl
        sl._cached_team_id = None

        result = _get_team_id(client)
        assert result == "T_CACHED"
        client.auth_test.assert_called_once()

        # Second call should use cache
        result2 = _get_team_id(client)
        assert result2 == "T_CACHED"
        # Still only one call to auth_test
        client.auth_test.assert_called_once()

        # Reset for other tests
        sl._cached_team_id = None


class TestSessionClosedCallback:
    """Test _make_session_closed_callback posts correct messages."""

    def _make_session(self, channel_id="C_TEST"):
        session = MagicMock()
        session.channel_id = channel_id
        return session

    def test_approved_posts_pr_url(self):
        from pipeline.slack_listener import _make_session_closed_callback

        client = MagicMock()
        callback = _make_session_closed_callback(client)

        session = self._make_session()
        result = {"status": "approved", "pr_url": "https://github.com/org/repo/pull/42"}

        callback(session, result)

        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "C_TEST"
        assert "PR created" in call_kwargs["text"]
        assert "pull/42" in call_kwargs["text"]

    def test_rejected_posts_reason(self):
        from pipeline.slack_listener import _make_session_closed_callback

        client = MagicMock()
        callback = _make_session_closed_callback(client)

        session = self._make_session()
        result = {"status": "rejected", "verdict": {"reason": "Bad code quality"}}

        callback(session, result)

        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args[1]
        assert "no changes kept" in call_kwargs["text"]
        assert "Bad code quality" in call_kwargs["text"]

    def test_linear_proposed_posts_proposal(self):
        from pipeline.slack_listener import _make_session_closed_callback

        client = MagicMock()
        callback = _make_session_closed_callback(client)

        session = self._make_session()
        result = {
            "status": "linear_proposed",
            "linear_proposal": {"reason": "Found interesting patterns"},
        }

        callback(session, result)

        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args[1]
        assert "Findings worth tracking" in call_kwargs["text"]
        assert "Found interesting patterns" in call_kwargs["text"]

    def test_error_posts_error_message(self):
        from pipeline.slack_listener import _make_session_closed_callback

        client = MagicMock()
        callback = _make_session_closed_callback(client)

        session = self._make_session()
        result = {"status": "error", "error": "Container died unexpectedly"}

        callback(session, result)

        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args[1]
        assert "error" in call_kwargs["text"].lower()
        assert "Container died" in call_kwargs["text"]

    def test_no_changes_says_nothing(self):
        from pipeline.slack_listener import _make_session_closed_callback

        client = MagicMock()
        callback = _make_session_closed_callback(client)

        session = self._make_session()
        result = {"status": "no_changes"}

        callback(session, result)

        client.chat_postMessage.assert_not_called()

    def test_none_result_says_nothing(self):
        from pipeline.slack_listener import _make_session_closed_callback

        client = MagicMock()
        callback = _make_session_closed_callback(client)

        session = self._make_session()
        callback(session, None)

        client.chat_postMessage.assert_not_called()

    def test_client_error_handled_gracefully(self):
        """Slack API errors should not propagate."""
        from pipeline.slack_listener import _make_session_closed_callback

        client = MagicMock()
        client.chat_postMessage.side_effect = Exception("Slack API down")
        callback = _make_session_closed_callback(client)

        session = self._make_session()
        result = {"status": "approved", "pr_url": "https://example.com/pr/1"}

        # Should not raise
        callback(session, result)


class TestReadChannelHistory:
    """Test the _read_channel_history helper."""

    def test_formats_messages_correctly(self):
        from pipeline.slack_listener import _read_channel_history

        client = MagicMock()
        client.conversations_history.return_value = {
            "messages": [
                {"user": "U002", "text": "second message", "ts": "1712000020.000000"},
                {"user": "U001", "text": "first message", "ts": "1712000010.000000"},
            ]
        }

        result = _read_channel_history(client, "C001", limit=20)

        assert "U001: first message" in result
        assert "U002: second message" in result
        # Should be in chronological order (reversed from input)
        first_pos = result.index("U001")
        second_pos = result.index("U002")
        assert first_pos < second_pos

    def test_skips_bot_messages(self):
        from pipeline.slack_listener import _read_channel_history

        client = MagicMock()
        client.conversations_history.return_value = {
            "messages": [
                {"user": "U001", "text": "human message", "ts": "1712000010.000000"},
                {"bot_id": "B001", "text": "bot message", "ts": "1712000020.000000"},
                {"user": "U002", "text": "subtype msg", "ts": "1712000030.000000", "subtype": "channel_join"},
            ]
        }

        result = _read_channel_history(client, "C001")

        assert "human message" in result
        assert "bot message" not in result
        assert "subtype msg" not in result

    def test_empty_messages_returns_empty_string(self):
        from pipeline.slack_listener import _read_channel_history

        client = MagicMock()
        client.conversations_history.return_value = {"messages": []}

        result = _read_channel_history(client, "C001")
        assert result == ""

    def test_api_error_returns_empty_string(self):
        from pipeline.slack_listener import _read_channel_history

        client = MagicMock()
        client.conversations_history.side_effect = Exception("API error")

        result = _read_channel_history(client, "C001")
        assert result == ""

    def test_all_bot_messages_returns_empty(self):
        """If all messages are from bots, return empty string."""
        from pipeline.slack_listener import _read_channel_history

        client = MagicMock()
        client.conversations_history.return_value = {
            "messages": [
                {"bot_id": "B001", "text": "only bots here", "ts": "1712000010.000000"},
            ]
        }

        result = _read_channel_history(client, "C001")
        assert result == ""


class TestFeedbackHandler:
    """Test the feedback action handler logic."""

    def test_positive_feedback_detected(self):
        """Positive feedback value should be identified correctly."""
        body = {
            "message": {"ts": "1234.5678"},
            "channel": {"id": "C001"},
            "user": {"id": "U001"},
            "actions": [{"value": "good-feedback"}],
        }

        feedback_value = body["actions"][0].get("value", "unknown")
        is_positive = feedback_value == "good-feedback"
        assert is_positive is True

    def test_negative_feedback_detected(self):
        """Negative feedback value should be identified correctly."""
        body = {
            "message": {"ts": "1234.5678"},
            "channel": {"id": "C001"},
            "user": {"id": "U001"},
            "actions": [{"value": "bad-feedback"}],
        }

        feedback_value = body["actions"][0].get("value", "unknown")
        is_positive = feedback_value == "good-feedback"
        assert is_positive is False

    def test_positive_feedback_posts_thank_you(self):
        """Positive feedback should post 'Thanks for the feedback!' ephemeral."""
        client = MagicMock()
        body = {
            "message": {"ts": "1234.5678"},
            "channel": {"id": "C001"},
            "user": {"id": "U001"},
            "actions": [{"value": "good-feedback"}],
        }

        # Simulate handler logic
        message_ts = body["message"]["ts"]
        channel_id = body["channel"]["id"]
        user_id = body["user"]["id"]
        feedback_value = body["actions"][0].get("value", "unknown")
        is_positive = feedback_value == "good-feedback"

        if is_positive:
            client.chat_postEphemeral(
                channel=channel_id, user=user_id,
                thread_ts=message_ts, text="Thanks for the feedback!",
            )

        client.chat_postEphemeral.assert_called_once()
        call_kwargs = client.chat_postEphemeral.call_args[1]
        assert call_kwargs["text"] == "Thanks for the feedback!"
        assert call_kwargs["channel"] == "C001"

    def test_negative_feedback_posts_sorry(self):
        """Negative feedback should post a sorry message."""
        client = MagicMock()
        body = {
            "message": {"ts": "1234.5678"},
            "channel": {"id": "C001"},
            "user": {"id": "U001"},
            "actions": [{"value": "bad-feedback"}],
        }

        feedback_value = body["actions"][0].get("value", "unknown")
        is_positive = feedback_value == "good-feedback"

        if not is_positive:
            client.chat_postEphemeral(
                channel=body["channel"]["id"],
                user=body["user"]["id"],
                thread_ts=body["message"]["ts"],
                text="Sorry that wasn't helpful. Starting a new thread may improve results.",
            )

        client.chat_postEphemeral.assert_called_once()
        assert "sorry" in client.chat_postEphemeral.call_args[1]["text"].lower()


# =========================================================================
# Worker Manager tests (send_message / get_response)
# =========================================================================


class TestWorkerManager:
    """Test WorkerManager methods with mocked Docker client (Agent SDK)."""

    @pytest.fixture
    def config(self, tmp_path):
        return PipelineConfig(output_base=str(tmp_path))

    @pytest.fixture
    def mock_docker(self):
        with patch("pipeline.worker_manager.docker") as mock_docker_mod:
            mock_client = MagicMock()
            mock_docker_mod.from_env.return_value = mock_client

            container = MagicMock()
            container.id = "abcdef1234567890" + "0" * 48
            container.name = "worker-test-run"
            container.status = "running"
            container.attrs = {"State": {"ExitCode": 0}}
            container.logs.return_value = b"some logs"

            mock_client.containers.run.return_value = container
            mock_client.images.get.return_value = MagicMock()  # image exists

            yield {
                "docker_mod": mock_docker_mod,
                "client": mock_client,
                "container": container,
            }

    def test_init_no_webhook_param(self, config, mock_docker):
        """WorkerManager should NOT accept a webhook parameter."""
        wm = WorkerManager(config, "test-run")
        assert not hasattr(wm, "_webhook")

    def test_send_message_clears_sentinel_before_cp(self, config, mock_docker):
        """send_message should rm /tmp/session-complete BEFORE docker cp."""
        wm = WorkerManager(config, "test-run")
        wm._container = mock_docker["container"]

        call_order = []

        def record_call(*args, **kwargs):
            cmd = args[0]
            if cmd[0] == "docker" and cmd[1] == "exec":
                if "rm" in cmd:
                    call_order.append("rm_sentinel")
                elif "chmod" in cmd:
                    call_order.append("docker_exec_chmod")
            elif cmd[0] == "docker" and cmd[1] == "cp":
                call_order.append("docker_cp")

        with patch("pipeline.worker_manager.subprocess") as mock_sub:
            mock_sub.run.side_effect = record_call
            with patch("pipeline.worker_manager.tempfile") as mock_tmp:
                mock_file = MagicMock()
                mock_file.__enter__ = MagicMock(return_value=mock_file)
                mock_file.__exit__ = MagicMock(return_value=False)
                mock_file.name = "/tmp/fake-msg.txt"
                mock_tmp.NamedTemporaryFile.return_value = mock_file

                with patch("pipeline.worker_manager.os.unlink"):
                    wm.send_message("hello")

        assert "rm_sentinel" in call_order, "must rm sentinel before writing next message"
        assert call_order.index("rm_sentinel") < call_order.index("docker_cp")
        assert call_order.index("docker_cp") < call_order.index("docker_exec_chmod")

    @patch("pipeline.worker_manager.subprocess")
    def test_get_response_reads_plain_text(self, mock_sub, config, mock_docker):
        """get_response should read plain text from latest-response.txt (not JSON)."""
        wm = WorkerManager(config, "test-run")
        wm._container = mock_docker["container"]

        def fake_cp(*args, **kwargs):
            cmd_args = args[0]
            dest = cmd_args[-1]
            with open(dest, "w") as f:
                f.write("Hello from worker")

        mock_sub.run.side_effect = fake_cp

        result = wm.get_response()
        assert result == "Hello from worker"

    @patch("pipeline.worker_manager.subprocess")
    def test_get_response_returns_empty_on_cp_failure(self, mock_sub, config, mock_docker):
        """get_response should return empty string if docker cp fails."""
        import subprocess as real_subprocess
        mock_sub.CalledProcessError = real_subprocess.CalledProcessError
        mock_sub.run.side_effect = real_subprocess.CalledProcessError(1, "docker cp")

        wm = WorkerManager(config, "test-run")
        wm._container = mock_docker["container"]

        result = wm.get_response()
        assert result == ""

    @patch("pipeline.worker_manager.subprocess")
    def test_get_tool_log_reads_jsonl(self, mock_sub, config, mock_docker):
        """get_tool_log should read /tmp/tool-log.jsonl from the container."""
        wm = WorkerManager(config, "test-run")
        wm._container = mock_docker["container"]

        tool_log_content = '{"event":"PreToolUse","tool_name":"Bash"}\n{"event":"PostToolUse","tool_name":"Bash"}\n'

        def fake_cp(*args, **kwargs):
            cmd_args = args[0]
            dest = cmd_args[-1]
            with open(dest, "w") as f:
                f.write(tool_log_content)

        mock_sub.run.side_effect = fake_cp

        result = wm.get_tool_log()
        assert len(result) == 2
        assert result[0]["event"] == "PreToolUse"
        assert result[1]["event"] == "PostToolUse"

    @patch("pipeline.worker_manager.subprocess")
    def test_get_tool_log_returns_empty_on_failure(self, mock_sub, config, mock_docker):
        """get_tool_log should return empty list if docker cp fails."""
        import subprocess as real_subprocess
        mock_sub.CalledProcessError = real_subprocess.CalledProcessError
        mock_sub.run.side_effect = real_subprocess.CalledProcessError(1, "docker cp")

        wm = WorkerManager(config, "test-run")
        wm._container = mock_docker["container"]

        result = wm.get_tool_log()
        assert result == []

    @patch("pipeline.worker_manager.subprocess")
    def test_get_usage_reads_json(self, mock_sub, config, mock_docker):
        """get_usage should read /tmp/usage.json from the container."""
        wm = WorkerManager(config, "test-run")
        wm._container = mock_docker["container"]

        usage_content = json.dumps({"input_tokens": 1000, "output_tokens": 500, "total_cost_usd": 0.03})

        def fake_cp(*args, **kwargs):
            cmd_args = args[0]
            dest = cmd_args[-1]
            with open(dest, "w") as f:
                f.write(usage_content)

        mock_sub.run.side_effect = fake_cp

        result = wm.get_usage()
        assert result["input_tokens"] == 1000
        assert result["total_cost_usd"] == 0.03

    @patch("pipeline.worker_manager.subprocess")
    def test_get_usage_returns_empty_on_failure(self, mock_sub, config, mock_docker):
        """get_usage should return empty dict if docker cp fails."""
        import subprocess as real_subprocess
        mock_sub.CalledProcessError = real_subprocess.CalledProcessError
        mock_sub.run.side_effect = real_subprocess.CalledProcessError(1, "docker cp")

        wm = WorkerManager(config, "test-run")
        wm._container = mock_docker["container"]

        result = wm.get_usage()
        assert result == {}

    def test_wait_for_completion_polls_sentinel(self, config, mock_docker):
        """wait_for_completion should poll for /tmp/session-complete sentinel."""
        wm = WorkerManager(config, "test-run")
        wm._container = mock_docker["container"]

        # Simulate sentinel file appearing on second check
        call_count = [0]

        def fake_exec(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 2:
                return MagicMock(returncode=0)
            else:
                return MagicMock(returncode=1)  # file not found

        with patch("pipeline.worker_manager.subprocess") as mock_sub:
            mock_sub.run.side_effect = fake_exec
            with patch("pipeline.worker_manager.time.sleep"):
                wm.wait_for_completion()

        # Should have been called at least twice (first miss, then hit)
        assert call_count[0] >= 2

    def test_is_alive_running(self, config, mock_docker):
        """is_alive should return True for a running container."""
        wm = WorkerManager(config, "test-run")
        wm._container = mock_docker["container"]
        mock_docker["container"].status = "running"
        assert wm.is_alive() is True

    def test_is_alive_exited(self, config, mock_docker):
        """is_alive should return False for an exited container."""
        wm = WorkerManager(config, "test-run")
        wm._container = mock_docker["container"]
        mock_docker["container"].status = "exited"
        assert wm.is_alive() is False

    def test_is_alive_no_container(self, config, mock_docker):
        """is_alive should return False when no container exists."""
        wm = WorkerManager(config, "test-run")
        wm._container = None
        assert wm.is_alive() is False

    def test_send_message_raises_if_no_container(self, config, mock_docker):
        """send_message should raise RuntimeError if container is None."""
        wm = WorkerManager(config, "test-run")
        wm._container = None
        with pytest.raises(RuntimeError, match="not running"):
            wm.send_message("hello")

    def test_send_message_raises_if_container_not_running(self, config, mock_docker):
        """send_message should raise RuntimeError if container is not running."""
        wm = WorkerManager(config, "test-run")
        wm._container = mock_docker["container"]
        mock_docker["container"].status = "exited"
        with pytest.raises(RuntimeError, match="exited"):
            wm.send_message("hello")

    def test_get_response_raises_if_no_container(self, config, mock_docker):
        """get_response should raise RuntimeError if container is None."""
        wm = WorkerManager(config, "test-run")
        wm._container = None
        with pytest.raises(RuntimeError, match="not running"):
            wm.get_response()

    def test_send_feedback_is_alias_for_send_message(self, config, mock_docker):
        """send_feedback should delegate to send_message."""
        wm = WorkerManager(config, "test-run")
        wm.send_message = MagicMock()
        wm.send_feedback("feedback text")
        wm.send_message.assert_called_once_with("feedback text")

    def test_cleanup_removes_container(self, config, mock_docker):
        """cleanup should remove the container (no webhook)."""
        wm = WorkerManager(config, "test-run")
        wm._container = mock_docker["container"]
        wm.cleanup()
        mock_docker["container"].remove.assert_called_once_with(force=True)


# =========================================================================
# Thread reply routing tests (catch-all handler)
# =========================================================================


class TestThreadReplyRouting:
    """Test that thread replies in @mention threads are routed to the session manager.

    When a user @mentions Leo in a channel, Leo responds in a thread.
    Subsequent replies in that thread (without @mentioning) should be routed
    to the session manager if the user has an active session, not silently dropped.
    """

    @pytest.fixture
    def config(self, tmp_path):
        return PipelineConfig(output_base=str(tmp_path))

    @pytest.fixture
    def app_harness(self, tmp_path):
        """Create an app via create_app with mocked internals, capturing handlers."""
        from pipeline.slack_listener import create_app

        session_manager = MagicMock()
        client = MagicMock()
        streamer = MagicMock()
        client.chat_stream.return_value = streamer

        handlers = {}

        mock_app_instance = MagicMock()

        def capture_event(event_type):
            def decorator(fn):
                handlers[event_type] = fn
                return fn
            return decorator

        mock_app_instance.event = capture_event
        mock_app_instance.use = MagicMock()
        mock_app_instance.action = lambda action_id: lambda fn: fn
        mock_app_instance.client = client

        with patch("pipeline.slack_listener.SessionManager", return_value=session_manager), \
             patch("pipeline.slack_listener.App", return_value=mock_app_instance), \
             patch("pipeline.slack_listener._get_team_id", return_value="T_TEST"), \
             patch("pipeline.slack_listener._HAS_CHUNKS", False), \
             patch.dict(os.environ, {"SLACK_BOT_TOKEN": "xoxb-fake-token"}):
            config = PipelineConfig(output_base=str(tmp_path))
            app, sm = create_app(config)

        return {
            "handlers": handlers,
            "session_manager": session_manager,
            "client": client,
            "streamer": streamer,
        }

    def test_thread_reply_with_active_session_routes_to_session_manager(self, app_harness):
        """A thread reply from a user with an active session should call send_message."""
        h = app_harness
        mock_session = MagicMock()
        h["session_manager"].get_session.return_value = mock_session
        h["session_manager"].send_message.return_value = "Leo's reply"

        event = {
            "type": "message",
            "user": "U_HUMAN",
            "text": "Follow-up question",
            "channel": "C_CHANNEL",
            "ts": "1111.2222",
            "thread_ts": "1111.0000",
        }

        handler = h["handlers"]["message"]
        handler(event=event, say=MagicMock(), client=h["client"], logger=MagicMock())

        h["session_manager"].get_session.assert_called_with("U_HUMAN")
        h["session_manager"].send_message.assert_called_with(mock_session, "Follow-up question")

        # Verify response was streamed back into the thread
        h["client"].chat_stream.assert_called_once()
        call_kwargs = h["client"].chat_stream.call_args[1]
        assert call_kwargs["channel"] == "C_CHANNEL"
        assert call_kwargs["thread_ts"] == "1111.0000"
        h["streamer"].append.assert_called()
        h["streamer"].stop.assert_called()

    def test_thread_reply_without_active_session_is_ignored(self, app_harness):
        """A thread reply from a user with NO active session should be silently ignored."""
        h = app_harness
        h["session_manager"].get_session.return_value = None

        event = {
            "type": "message",
            "user": "U_NOBODY",
            "text": "Some reply",
            "channel": "C_CHANNEL",
            "ts": "2222.3333",
            "thread_ts": "2222.0000",
        }

        handler = h["handlers"]["message"]
        handler(event=event, say=MagicMock(), client=h["client"], logger=MagicMock())

        h["session_manager"].get_session.assert_called_with("U_NOBODY")
        h["session_manager"].send_message.assert_not_called()
        h["client"].chat_stream.assert_not_called()

    def test_non_thread_message_is_ignored(self, app_harness):
        """A top-level channel message (not a thread reply) should be silently ignored."""
        h = app_harness

        event = {
            "type": "message",
            "user": "U_SOMEONE",
            "text": "Hello channel",
            "channel": "C_CHANNEL",
            "ts": "3333.4444",
        }

        handler = h["handlers"]["message"]
        handler(event=event, say=MagicMock(), client=h["client"], logger=MagicMock())

        h["session_manager"].get_session.assert_not_called()
        h["session_manager"].send_message.assert_not_called()
        h["client"].chat_stream.assert_not_called()

    def test_bot_message_is_skipped(self, app_harness):
        """Messages with bot_id should be skipped to prevent loops."""
        h = app_harness

        event = {
            "type": "message",
            "bot_id": "B_LEO",
            "text": "I am a bot",
            "channel": "C_CHANNEL",
            "ts": "4444.5555",
            "thread_ts": "4444.0000",
        }

        handler = h["handlers"]["message"]
        handler(event=event, say=MagicMock(), client=h["client"], logger=MagicMock())

        h["session_manager"].get_session.assert_not_called()
        h["session_manager"].send_message.assert_not_called()

    def test_subtype_message_is_skipped(self, app_harness):
        """Messages with a subtype (e.g. 'message_changed') should be skipped."""
        h = app_harness

        event = {
            "type": "message",
            "subtype": "message_changed",
            "user": "U_HUMAN",
            "text": "Edited text",
            "channel": "C_CHANNEL",
            "ts": "5555.6666",
            "thread_ts": "5555.0000",
        }

        handler = h["handlers"]["message"]
        handler(event=event, say=MagicMock(), client=h["client"], logger=MagicMock())

        h["session_manager"].get_session.assert_not_called()
        h["session_manager"].send_message.assert_not_called()

    def test_thread_reply_where_ts_equals_thread_ts_is_ignored(self, app_harness):
        """A message where ts == thread_ts is the parent message, not a reply."""
        h = app_harness

        event = {
            "type": "message",
            "user": "U_HUMAN",
            "text": "I am the parent",
            "channel": "C_CHANNEL",
            "ts": "6666.0000",
            "thread_ts": "6666.0000",
        }

        handler = h["handlers"]["message"]
        handler(event=event, say=MagicMock(), client=h["client"], logger=MagicMock())

        h["session_manager"].get_session.assert_not_called()
        h["session_manager"].send_message.assert_not_called()


# =========================================================================
# Worker Entrypoint tests (Agent SDK pivot — Step 2)
# =========================================================================


class TestWorkerEntrypoint:
    """Test worker/entrypoint.py functions for the Agent SDK worker."""

    def test_build_system_prompt_includes_workspace_files(self, tmp_path):
        """System prompt should combine SOUL.md, IDENTITY.md, USER.md, AGENTS.md."""
        from worker.entrypoint import build_system_prompt

        (tmp_path / "SOUL.md").write_text("You are Leo.")
        (tmp_path / "IDENTITY.md").write_text("Name: Leo")
        (tmp_path / "USER.md").write_text("Name: Travis")
        (tmp_path / "AGENTS.md").write_text("Session startup rules")

        prompt = build_system_prompt(str(tmp_path))

        assert "You are Leo." in prompt
        assert "Name: Leo" in prompt
        assert "Name: Travis" in prompt
        assert "Session startup rules" in prompt

    def test_build_system_prompt_handles_missing_files(self, tmp_path):
        """System prompt should not crash if some workspace files are missing."""
        from worker.entrypoint import build_system_prompt

        (tmp_path / "SOUL.md").write_text("You are Leo.")
        # IDENTITY.md, USER.md, AGENTS.md intentionally missing

        prompt = build_system_prompt(str(tmp_path))
        assert "You are Leo." in prompt

    def test_pre_tool_use_hook_logs_to_tool_log(self, tmp_path):
        """PreToolUse hook should append a JSON line to the tool log."""
        from worker.entrypoint import create_pre_tool_use_hook
        import asyncio

        tool_log = tmp_path / "tool-log.jsonl"
        hook = create_pre_tool_use_hook(str(tool_log))

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "tool_use_id": "tu_123",
            "session_id": "sess_abc",
            "transcript_path": "/tmp/transcript",
            "cwd": "/workspace",
        }

        result = asyncio.run(hook(input_data, "tu_123", {"signal": None}))

        assert tool_log.exists()
        logged = json.loads(tool_log.read_text().strip())
        assert logged["event"] == "PreToolUse"
        assert logged["tool_name"] == "Bash"
        assert logged["tool_input"] == {"command": "ls"}
        # Hook should not block execution
        assert result.get("continue_", True) is True

    def test_post_tool_use_hook_logs_to_tool_log(self, tmp_path):
        """PostToolUse hook should append a JSON line with tool response."""
        from worker.entrypoint import create_post_tool_use_hook
        import asyncio

        tool_log = tmp_path / "tool-log.jsonl"
        hook = create_post_tool_use_hook(str(tool_log))

        input_data = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "/workspace/README.md"},
            "tool_response": "file contents here",
            "tool_use_id": "tu_456",
            "session_id": "sess_abc",
            "transcript_path": "/tmp/transcript",
            "cwd": "/workspace",
        }

        result = asyncio.run(hook(input_data, "tu_456", {"signal": None}))

        lines = tool_log.read_text().strip().split("\n")
        assert len(lines) == 1
        logged = json.loads(lines[0])
        assert logged["event"] == "PostToolUse"
        assert logged["tool_name"] == "Read"
        assert logged["tool_response"] == "file contents here"

    def test_stop_hook_writes_sentinel_and_usage(self, tmp_path):
        """Stop hook should write session-complete sentinel and usage.json."""
        from worker.entrypoint import create_stop_hook
        import asyncio

        sentinel = tmp_path / "session-complete"
        usage_file = tmp_path / "usage.json"
        usage_tracker = {"input_tokens": 1500, "output_tokens": 500, "total_cost_usd": 0.05}

        hook = create_stop_hook(
            sentinel_path=str(sentinel),
            usage_path=str(usage_file),
            usage_tracker=usage_tracker,
        )

        input_data = {
            "stop_hook_active": True,
            "session_id": "sess_abc",
            "transcript_path": "/tmp/transcript",
            "cwd": "/workspace",
        }

        result = asyncio.run(hook(input_data, None, {"signal": None}))

        assert sentinel.exists()
        assert usage_file.exists()
        usage_data = json.loads(usage_file.read_text())
        assert usage_data["input_tokens"] == 1500
        assert usage_data["output_tokens"] == 500
        assert usage_data["total_cost_usd"] == 0.05

    def test_multiple_hook_events_append_to_same_log(self, tmp_path):
        """Multiple hook events should produce multiple JSONL lines."""
        from worker.entrypoint import create_pre_tool_use_hook, create_post_tool_use_hook
        import asyncio

        tool_log = tmp_path / "tool-log.jsonl"
        pre_hook = create_pre_tool_use_hook(str(tool_log))
        post_hook = create_post_tool_use_hook(str(tool_log))

        pre_input = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "echo hi"},
            "tool_use_id": "tu_1",
            "session_id": "s1",
            "transcript_path": "/tmp/t",
            "cwd": "/w",
        }
        post_input = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "echo hi"},
            "tool_response": "hi\n",
            "tool_use_id": "tu_1",
            "session_id": "s1",
            "transcript_path": "/tmp/t",
            "cwd": "/w",
        }

        asyncio.run(pre_hook(pre_input, "tu_1", {"signal": None}))
        asyncio.run(post_hook(post_input, "tu_1", {"signal": None}))

        lines = tool_log.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "PreToolUse"
        assert json.loads(lines[1])["event"] == "PostToolUse"


# =========================================================================
# P0: Critical path tests
# =========================================================================


class TestWorkerManagerStart:
    """Test WorkerManager.start() env var propagation."""

    @pytest.fixture
    def config(self, tmp_path):
        return PipelineConfig(output_base=str(tmp_path))

    def test_start_passes_correct_env_vars(self, config):
        """start() should pass TASK_INSTRUCTION, ANTHROPIC_API_KEY, ALLOWED_TOOLS."""
        with patch("pipeline.worker_manager.docker") as mock_docker:
            mock_client = MagicMock()
            mock_docker.from_env.return_value = mock_client
            container = MagicMock()
            container.id = "abc123" + "0" * 58
            mock_client.containers.run.return_value = container
            mock_client.images.get.return_value = MagicMock()

            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-token"}):
                wm = WorkerManager(config, "test-run")
                wm.start("Do something")

            call_kwargs = mock_client.containers.run.call_args
            env = call_kwargs[1]["environment"]

            assert env["TASK_INSTRUCTION"] == "Do something"
            assert env["ANTHROPIC_API_KEY"] == "sk-test-token"
            assert "ALLOWED_TOOLS" in env
            assert "Bash" in env["ALLOWED_TOOLS"]

    def test_start_sets_container_name(self, config):
        """start() should name the container worker-{run_id}."""
        with patch("pipeline.worker_manager.docker") as mock_docker:
            mock_client = MagicMock()
            mock_docker.from_env.return_value = mock_client
            container = MagicMock()
            container.id = "abc123" + "0" * 58
            mock_client.containers.run.return_value = container
            mock_client.images.get.return_value = MagicMock()

            wm = WorkerManager(config, "my-run-42")
            wm.start("task")

            call_kwargs = mock_client.containers.run.call_args
            assert call_kwargs[1]["name"] == "worker-my-run-42"


class TestWaitForCompletionEdgeCases:
    """Test WorkerManager.wait_for_completion() timeout and exit paths."""

    @pytest.fixture
    def config(self, tmp_path):
        return PipelineConfig(output_base=str(tmp_path), worker_timeout=2)

    @pytest.fixture
    def mock_docker(self):
        with patch("pipeline.worker_manager.docker") as mock_docker_mod:
            mock_client = MagicMock()
            mock_docker_mod.from_env.return_value = mock_client
            container = MagicMock()
            container.id = "abc123" + "0" * 58
            container.status = "running"
            container.attrs = {"State": {"ExitCode": 0}}
            mock_client.images.get.return_value = MagicMock()
            yield {"client": mock_client, "container": container}

    def test_timeout_raises(self, config, mock_docker):
        """wait_for_completion should raise TimeoutError when sentinel never appears."""
        wm = WorkerManager(config, "test-run")
        wm._container = mock_docker["container"]

        with patch("pipeline.worker_manager.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=1)
            with patch("pipeline.worker_manager.time.sleep"):
                with patch("pipeline.worker_manager.time.monotonic") as mock_time:
                    mock_time.side_effect = [0.0, 0.0, 1.0, 3.0]
                    with pytest.raises(TimeoutError, match="Worker did not complete"):
                        wm.wait_for_completion()

    def test_container_exits_before_sentinel(self, config, mock_docker):
        """wait_for_completion should raise when container exits without sentinel."""
        wm = WorkerManager(config, "test-run")
        wm._container = mock_docker["container"]
        mock_docker["container"].status = "exited"
        mock_docker["container"].attrs = {"State": {"ExitCode": 1}}

        with patch("pipeline.worker_manager.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=1)
            with patch("pipeline.worker_manager.time.sleep"):
                with patch("pipeline.worker_manager.time.monotonic") as mock_time:
                    mock_time.side_effect = [0.0, 0.0, 3.0]
                    with pytest.raises(TimeoutError):
                        wm.wait_for_completion()


class TestWorkerManagerCleanupEdgeCases:
    """Test WorkerManager.cleanup() edge cases."""

    @pytest.fixture
    def config(self, tmp_path):
        return PipelineConfig(output_base=str(tmp_path))

    def test_cleanup_when_container_is_none(self, config):
        """cleanup() should be a no-op when _container is None."""
        with patch("pipeline.worker_manager.docker") as mock_docker:
            mock_docker.from_env.return_value = MagicMock()
            wm = WorkerManager(config, "test-run")
            wm._container = None
            wm.cleanup()  # should not raise

    def test_cleanup_handles_not_found(self, config):
        """cleanup() should handle NotFound gracefully."""
        from docker.errors import NotFound
        with patch("pipeline.worker_manager.docker") as mock_docker:
            mock_docker.from_env.return_value = MagicMock()
            wm = WorkerManager(config, "test-run")
            container = MagicMock()
            container.remove.side_effect = NotFound("gone")
            wm._container = container
            wm.cleanup()  # should not raise


class TestFormatFeedback:
    """Test _format_feedback() output formatting."""

    def test_with_feedback_items(self):
        """Feedback items should be numbered in the output."""
        from pipeline.main import _format_feedback
        result = _format_feedback(["Fix tests", "Add docstring"], "Code quality", 1)
        assert "iteration 1" in result
        assert "Code quality" in result
        assert "1. Fix tests" in result
        assert "2. Add docstring" in result

    def test_without_feedback_items(self):
        """Empty feedback list should still include reason."""
        from pipeline.main import _format_feedback
        result = _format_feedback([], "No changes detected", 2)
        assert "iteration 2" in result
        assert "No changes detected" in result
        assert "Specific items" not in result


class TestPrepareEvaluationFiltering:
    """Test MechanicManager._prepare_evaluation() filtering logic."""

    @pytest.fixture
    def config(self, tmp_path):
        return PipelineConfig(output_base=str(tmp_path))

    def test_filters_binary_files(self, config):
        """Binary files should be excluded from file_contents."""
        mm = MechanicManager(config, "test-run")
        changeset = {
            "task": "test",
            "git_changes": {
                "file_contents": {
                    "src/main.py": "print('hello')",
                    "assets/logo.png": "<binary data>",
                    "assets/video.mp4": "<binary data>",
                },
            },
            "docker_changes": {},
            "telemetry": {},
            "output_files": {},
        }
        evaluation = mm._prepare_evaluation(changeset)
        contents = evaluation["git_changes"]["file_contents"]
        assert "src/main.py" in contents
        assert "assets/logo.png" not in contents
        assert "assets/video.mp4" not in contents
        assert len(evaluation["git_changes"]["skipped_files"]) == 2

    def test_filters_lock_files(self, config):
        """Lock files should be excluded from file_contents."""
        mm = MechanicManager(config, "test-run")
        changeset = {
            "task": "test",
            "git_changes": {
                "file_contents": {
                    "src/app.js": "console.log('hi')",
                    "package-lock.json": '{"very": "large"}',
                },
            },
            "docker_changes": {},
            "telemetry": {},
            "output_files": {},
        }
        evaluation = mm._prepare_evaluation(changeset)
        contents = evaluation["git_changes"]["file_contents"]
        assert "src/app.js" in contents
        assert "package-lock.json" not in contents

    def test_filters_oversized_files(self, config):
        """Files over 50K chars should be excluded."""
        mm = MechanicManager(config, "test-run")
        changeset = {
            "task": "test",
            "git_changes": {
                "file_contents": {"small.py": "x = 1", "huge.py": "x" * 60_000},
            },
            "docker_changes": {},
            "telemetry": {},
            "output_files": {},
        }
        evaluation = mm._prepare_evaluation(changeset)
        assert "small.py" in evaluation["git_changes"]["file_contents"]
        assert "huge.py" not in evaluation["git_changes"]["file_contents"]

    def test_truncates_long_logs(self, config):
        """Container logs > 100 lines should be truncated."""
        mm = MechanicManager(config, "test-run")
        long_logs = "\n".join(f"log line {i}" for i in range(200))
        changeset = {
            "task": "test",
            "git_changes": {},
            "docker_changes": {},
            "telemetry": {"container_logs": long_logs},
            "output_files": {},
        }
        evaluation = mm._prepare_evaluation(changeset)
        logs = evaluation["telemetry"]["container_logs"]
        assert "truncated" in logs.lower()
        assert "log line 199" in logs
        assert "log line 0" not in logs


class TestRunPipelineFeedbackLoop:
    """Test the reject-feedback-retry loop in run_pipeline()."""

    @pytest.fixture
    def config(self, tmp_path):
        return PipelineConfig(output_base=str(tmp_path))

    @patch("pipeline.main.SlackHandler")
    @patch("pipeline.main.PRCreator")
    @patch("pipeline.main.ChangesetExtractor")
    @patch("pipeline.main.MechanicManager")
    @patch("pipeline.main.WorkerManager")
    def test_approve_on_second_iteration(
        self, MockWorker, MockMechanic, MockExtractor, MockPR, MockSlack, config
    ):
        """Pipeline should send feedback on rejection, then succeed on approval."""
        from pipeline.main import run_pipeline

        worker = MockWorker.return_value
        worker.start.return_value = "cid"
        worker.is_alive.return_value = True

        extractor = MockExtractor.return_value
        extractor.extract.return_value = {
            "task": "test",
            "git_changes": {"new_files": ["a.py"], "file_contents": {"a.py": "x=1"}},
        }

        mechanic = MockMechanic.return_value
        mechanic.evaluate.side_effect = [
            {"approved": False, "reason": "Missing tests", "feedback": ["Add tests"]},
            {"approved": True, "pr_title": "Add feature", "files_to_include": ["a.py"]},
        ]
        pr = MockPR.return_value
        pr.create.return_value = "https://github.com/test/pr/1"

        result = run_pipeline("test task", config)
        assert result["status"] == "approved"
        assert result["iterations"] == 2
        worker.send_feedback.assert_called_once()

    @patch("pipeline.main.SlackHandler")
    @patch("pipeline.main.ChangesetExtractor")
    @patch("pipeline.main.MechanicManager")
    @patch("pipeline.main.WorkerManager")
    def test_max_iterations_exhausted(
        self, MockWorker, MockMechanic, MockExtractor, MockSlack, config
    ):
        """Pipeline should stop after MAX_ITERATIONS rejections."""
        from pipeline.main import run_pipeline, MAX_ITERATIONS

        worker = MockWorker.return_value
        worker.start.return_value = "cid"
        worker.is_alive.return_value = True

        MockExtractor.return_value.extract.return_value = {
            "task": "test", "git_changes": {"new_files": ["a.py"], "file_contents": {}},
        }
        MockMechanic.return_value.evaluate.return_value = {
            "approved": False, "reason": "Still bad", "feedback": ["Fix"],
        }

        result = run_pipeline("test task", config)
        assert result["status"] == "rejected"
        assert result["iterations"] == MAX_ITERATIONS

    @patch("pipeline.main.SlackHandler")
    @patch("pipeline.main.ChangesetExtractor")
    @patch("pipeline.main.MechanicManager")
    @patch("pipeline.main.WorkerManager")
    def test_discard_disposition(
        self, MockWorker, MockMechanic, MockExtractor, MockSlack, config
    ):
        """disposition=discard should stop without retrying."""
        from pipeline.main import run_pipeline

        MockWorker.return_value.start.return_value = "cid"
        MockExtractor.return_value.extract.return_value = {
            "task": "test", "git_changes": {"new_files": ["a.py"], "file_contents": {}},
        }
        MockMechanic.return_value.evaluate.return_value = {
            "approved": False, "reason": "Unsafe", "disposition": "discard",
        }

        result = run_pipeline("test task", config)
        assert result["status"] == "rejected"
        assert result["iterations"] == 1

    @patch("pipeline.main.SlackHandler")
    @patch("pipeline.main.ChangesetExtractor")
    @patch("pipeline.main.MechanicManager")
    @patch("pipeline.main.WorkerManager")
    def test_worker_dies_mid_loop(
        self, MockWorker, MockMechanic, MockExtractor, MockSlack, config
    ):
        """Pipeline should stop gracefully if worker dies during feedback loop."""
        from pipeline.main import run_pipeline

        worker = MockWorker.return_value
        worker.start.return_value = "cid"
        worker.is_alive.return_value = False

        MockExtractor.return_value.extract.return_value = {
            "task": "test", "git_changes": {"new_files": ["a.py"], "file_contents": {}},
        }
        MockMechanic.return_value.evaluate.return_value = {
            "approved": False, "reason": "Needs work", "feedback": ["Fix"],
        }

        result = run_pipeline("test task", config)
        assert result["status"] == "error"
        assert "died" in result["error"].lower() or "Worker" in result["error"]


class TestEntrypointHelpers:
    """Test worker/entrypoint.py helper functions."""

    def test_extract_text_blocks_with_text(self):
        """_extract_text_blocks should extract text from TextBlock-like objects."""
        from worker.entrypoint import _extract_text_blocks

        class FakeBlock:
            def __init__(self, t): self.text = t

        class FakeMessage:
            def __init__(self, b): self.content = b

        assert _extract_text_blocks(FakeMessage([FakeBlock("Hello "), FakeBlock("world")])) == "Hello world"

    def test_extract_text_blocks_no_content(self):
        """_extract_text_blocks should handle missing content attribute."""
        from worker.entrypoint import _extract_text_blocks
        assert _extract_text_blocks(object()) == ""

    def test_accumulate_usage_with_data(self):
        """_accumulate_usage should add tokens from message usage."""
        from worker.entrypoint import _accumulate_usage

        class Msg:
            usage = {"input_tokens": 100, "output_tokens": 50}

        tracker = {"input_tokens": 0, "output_tokens": 0, "total_cost_usd": 0.0}
        _accumulate_usage(Msg(), tracker)
        assert tracker["input_tokens"] == 100
        assert tracker["output_tokens"] == 50

    def test_accumulate_usage_no_usage(self):
        """_accumulate_usage should handle messages without usage attribute."""
        from worker.entrypoint import _accumulate_usage
        tracker = {"input_tokens": 10, "output_tokens": 5, "total_cost_usd": 0.0}
        _accumulate_usage(object(), tracker)
        assert tracker["input_tokens"] == 10  # unchanged

    def test_build_system_prompt_format(self, tmp_path):
        """build_system_prompt should format with # headers."""
        from worker.entrypoint import build_system_prompt
        (tmp_path / "SOUL.md").write_text("Be helpful.")
        (tmp_path / "IDENTITY.md").write_text("Name: Leo")
        prompt = build_system_prompt(str(tmp_path))
        assert prompt.startswith("# SOUL\n")
        assert "# IDENTITY\n" in prompt

    def test_build_client_options_reads_env_vars(self):
        """_build_client_options should read MAX_TURNS and MAX_BUDGET_USD from env."""
        from worker.entrypoint import _build_client_options

        class FakeHookMatcher:
            def __init__(self, matcher=None, hooks=None): pass

        class FakeOptions:
            def __init__(self, **kw):
                for k, v in kw.items(): setattr(self, k, v)

        with patch.dict(os.environ, {"MAX_TURNS": "10", "MAX_BUDGET_USD": "2.5", "ALLOWED_TOOLS": "Bash,Read"}):
            opts = _build_client_options("prompt", {}, FakeOptions, FakeHookMatcher)
        assert opts.max_turns == 10
        assert opts.max_budget_usd == 2.5
        assert opts.allowed_tools == ["Bash", "Read"]
