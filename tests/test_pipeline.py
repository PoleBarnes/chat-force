"""Integration tests for the self-improving pipeline.

Tests verify pipeline components work together at the unit level, mocking
Docker and external services. Covers:
  - PipelineConfig defaults and output directory creation
  - WebhookServer lifecycle and HTTP handler behavior
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
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from pipeline.config import PipelineConfig
from pipeline.webhook_server import WebhookServer
from pipeline.changeset_extractor import ChangesetExtractor, _is_noise
from pipeline.mechanic_manager import MechanicManager
from pipeline.pr_creator import PRCreator, _slugify
from pipeline.slack_handler import SlackHandler

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
        assert config.mechanic_image == "chat-force-mechanic:latest"
        assert config.worker_timeout == 600
        assert config.mechanic_timeout == 300
        assert config.webhook_port == 8787
        assert config.github_repo == "PoleBarnes/chat-force"
        assert config.pr_branch_prefix == "openclaw/auto"

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
            output_base=str(tmp_path),
        )
        assert config.worker_timeout == 60
        assert config.mechanic_timeout == 30


# =========================================================================
# WebhookServer tests
# =========================================================================


class TestWebhookServer:
    """Test the webhook server lifecycle and HTTP handling."""

    @pytest.fixture
    def free_port(self):
        """Find a free TCP port for the test server."""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    @pytest.fixture
    def server(self, free_port):
        """Create and start a WebhookServer, tearing it down after the test."""
        ws = WebhookServer("127.0.0.1", free_port)
        ws.start()
        yield ws
        ws.stop()

    def test_start_and_stop(self, free_port):
        """Server should start and stop without errors."""
        ws = WebhookServer("127.0.0.1", free_port)
        ws.start()
        ws.stop()

    def test_wait_for_completion_returns_false_on_timeout(self, free_port):
        """wait_for_completion should return False if no signal arrives."""
        ws = WebhookServer("127.0.0.1", free_port)
        ws.start()
        try:
            result = ws.wait_for_completion(timeout=0.1)
            assert result is False
        finally:
            ws.stop()

    def test_wait_for_completion_returns_true_on_signal(self, server, free_port):
        """wait_for_completion should return True when task-complete is POSTed."""
        def send_signal():
            # Small delay to ensure wait_for_completion is blocking first
            time.sleep(0.05)
            payload = json.dumps({"status": "done"}).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{free_port}/hooks/task-complete",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=2)

        t = threading.Thread(target=send_signal)
        t.start()
        result = server.wait_for_completion(timeout=5)
        t.join(timeout=2)

        assert result is True

    def test_task_complete_stores_payload(self, server, free_port):
        """POST to /hooks/task-complete should store the payload."""
        payload = json.dumps({"task_id": "abc123"}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{free_port}/hooks/task-complete",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=2)
        assert resp.status == 200

        body = json.loads(resp.read())
        assert body["status"] == "accepted"
        assert server.last_payload == {"task_id": "abc123"}

    def test_after_turn_returns_200(self, server, free_port):
        """POST to /hooks/after-turn should return 200 acknowledged."""
        payload = json.dumps({"turn": 1}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{free_port}/hooks/after-turn",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=2)
        assert resp.status == 200
        body = json.loads(resp.read())
        assert body["status"] == "acknowledged"

    def test_unknown_path_returns_404(self, server, free_port):
        """POST to an unknown path should return 404."""
        payload = json.dumps({}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{free_port}/hooks/unknown",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=2)
            pytest.fail("Expected HTTP 404 error")
        except urllib.error.HTTPError as e:
            assert e.code == 404


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
        """extract() should call git, docker-diff, telemetry, and openclaw layers."""
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
        assert "openclaw_logs" in bundle
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
        assert branch.startswith("openclaw/auto/")

    def test_branch_contains_timestamp(self, pr_creator):
        """Branch name should contain a YYYYMMDD-HHMMSS timestamp."""
        branch = pr_creator._make_branch_name("Update tests")
        # After the prefix, the timestamp is the next 15 chars (YYYYMMDD-HHMMSS)
        parts = branch.split("/")
        # parts: ["openclaw", "auto", "YYYYMMDD-HHMMSS-slug"]
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
    def test_client_created_with_token(self, config):
        """SlackHandler should create a WebClient when token is available."""
        handler = SlackHandler(config)
        assert handler._client is not None


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
            "openclaw_logs": {},
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
            "openclaw_logs": {},
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
            "openclaw_logs": {},
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
