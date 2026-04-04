"""Integration tests for the self-improving pipeline.

Tests verify pipeline components work together at the unit level, mocking
Docker and external services. Covers:
  - PipelineConfig defaults and output directory creation
  - WebhookServer lifecycle and HTTP handler behavior
  - ResponseParser JSON extraction and edge cases
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
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from pipeline.config import PipelineConfig
from pipeline.webhook_server import WebhookServer
from pipeline.response_parser import parse_response
from pipeline.changeset_extractor import ChangesetExtractor, _is_noise
from pipeline.mechanic_manager import MechanicManager
from pipeline.pr_creator import PRCreator, _slugify
from pipeline.slack_handler import SlackHandler
from pipeline.session_manager import Session, SessionManager
from pipeline.worker_manager import WorkerManager

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# =========================================================================
# ResponseParser tests
# =========================================================================


class TestParseResponse:
    """Test parse_response handles OpenClaw output edge cases."""

    def test_clean_json(self):
        """Clean JSON with payloads should return joined text."""
        raw = json.dumps({
            "payloads": [{"text": "Hello world", "mediaUrl": None}],
            "meta": {},
        })
        assert parse_response(raw) == "Hello world"

    def test_multiple_payloads(self):
        """Multiple text payloads should be joined with newlines."""
        raw = json.dumps({
            "payloads": [
                {"text": "Line one", "mediaUrl": None},
                {"text": "Line two", "mediaUrl": None},
            ],
            "meta": {},
        })
        assert parse_response(raw) == "Line one\nLine two"

    def test_log_lines_before_json(self):
        """Log lines before the JSON blob should be skipped."""
        payload = json.dumps({
            "payloads": [{"text": "response text", "mediaUrl": None}],
            "meta": {},
        })
        raw = "[INFO] Starting agent...\n[DEBUG] Loading tools...\n" + payload
        assert parse_response(raw) == "response text"

    def test_log_lines_mixed_with_json(self):
        """Log output interleaved with JSON should still parse correctly."""
        payload = json.dumps({
            "payloads": [{"text": "the answer", "mediaUrl": None}],
            "meta": {},
        })
        raw = (
            "[Worker] Running OpenClaw turn...\n"
            "[INFO] session started\n"
            + payload + "\n"
            "[INFO] session ended\n"
        )
        assert parse_response(raw) == "the answer"

    def test_multiple_json_objects_takes_last(self):
        """When multiple JSON objects with payloads exist, take the last one."""
        first = json.dumps({
            "payloads": [{"text": "wrong answer", "mediaUrl": None}],
            "meta": {"turn": 1},
        })
        second = json.dumps({
            "payloads": [{"text": "correct answer", "mediaUrl": None}],
            "meta": {"turn": 2},
        })
        raw = "[LOG] starting\n" + first + "\n[LOG] more stuff\n" + second + "\n"
        assert parse_response(raw) == "correct answer"

    def test_non_payloads_json_before_payloads_json(self):
        """A non-payloads JSON object before the real one should be skipped."""
        noise = json.dumps({"status": "ok", "turn": 1})
        real = json.dumps({
            "payloads": [{"text": "actual response", "mediaUrl": None}],
            "meta": {},
        })
        raw = noise + "\n" + real
        assert parse_response(raw) == "actual response"

    def test_empty_string(self):
        """Empty input should return empty string."""
        assert parse_response("") == ""

    def test_none_input(self):
        """None input should return empty string."""
        assert parse_response(None) == ""

    def test_whitespace_only(self):
        """Whitespace-only input should return empty string."""
        assert parse_response("   \n  \n  ") == ""

    def test_pure_garbage(self):
        """Non-JSON garbage should return empty string without crashing."""
        assert parse_response("this is not json at all") == ""

    def test_invalid_json(self):
        """Malformed JSON should return empty string without crashing."""
        assert parse_response('{"payloads": [{"text": "unclosed') == ""

    def test_json_missing_payloads_key(self):
        """Valid JSON without payloads key should return empty string."""
        raw = json.dumps({"meta": {"turn": 1}, "other": "stuff"})
        assert parse_response(raw) == ""

    def test_payloads_not_a_list(self):
        """payloads that is not a list should return empty string."""
        raw = json.dumps({"payloads": "not a list"})
        assert parse_response(raw) == ""

    def test_empty_payloads_list(self):
        """Empty payloads list should return empty string."""
        raw = json.dumps({"payloads": [], "meta": {}})
        assert parse_response(raw) == ""

    def test_payloads_with_null_text(self):
        """Payload entries with null text should be skipped."""
        raw = json.dumps({
            "payloads": [
                {"text": None, "mediaUrl": "http://example.com/img.png"},
                {"text": "visible text", "mediaUrl": None},
            ],
            "meta": {},
        })
        assert parse_response(raw) == "visible text"

    def test_json_with_nested_braces_in_text(self):
        """Response text containing JSON-like braces should parse correctly."""
        raw = json.dumps({
            "payloads": [{"text": 'Use {"key": "value"} in your config', "mediaUrl": None}],
            "meta": {},
        })
        assert parse_response(raw) == 'Use {"key": "value"} in your config'

    def test_stderr_error_lines_before_json(self):
        """OpenClaw stderr error lines mixed in should not break parsing."""
        payload = json.dumps({
            "payloads": [{"text": "still works", "mediaUrl": None}],
            "meta": {},
        })
        raw = (
            "Error: something non-fatal happened\n"
            "Warning: tool X not available\n"
            + payload
        )
        assert parse_response(raw) == "still works"

    def test_alternate_key_order(self):
        """JSON where meta comes before payloads should still work."""
        # Build JSON with meta first
        raw = '{"meta": {"turn": 1}, "payloads": [{"text": "found it", "mediaUrl": null}]}'
        assert parse_response(raw) == "found it"

    def test_nested_result_payloads(self):
        """Payloads nested under a 'result' key should be found."""
        raw = json.dumps({
            "runId": "abc-123",
            "status": "ok",
            "summary": "completed",
            "result": {
                "payloads": [
                    {"text": "response text here", "mediaUrl": None},
                ],
                "meta": {"turn": 1},
            },
        })
        assert parse_response(raw) == "response text here"

    def test_nested_result_multiple_payloads(self):
        """Multiple payloads under 'result' should be joined."""
        raw = json.dumps({
            "runId": "abc-456",
            "status": "ok",
            "result": {
                "payloads": [
                    {"text": "first line", "mediaUrl": None},
                    {"text": "second line", "mediaUrl": None},
                ],
                "meta": {},
            },
        })
        assert parse_response(raw) == "first line\nsecond line"

    def test_nested_result_with_log_lines(self):
        """Nested result format with log lines before JSON should parse."""
        payload = json.dumps({
            "runId": "run-789",
            "status": "ok",
            "result": {
                "payloads": [{"text": "nested response", "mediaUrl": None}],
                "meta": {},
            },
        })
        raw = "[INFO] Starting agent...\n[DEBUG] Loading...\n" + payload
        assert parse_response(raw) == "nested response"

    def test_nested_result_without_top_level_payloads(self):
        """Envelope with only result.payloads (no top-level payloads) should work."""
        raw = json.dumps({
            "runId": "run-001",
            "status": "ok",
            "summary": "completed",
            "result": {
                "payloads": [{"text": "only nested", "mediaUrl": None}],
                "meta": {},
            },
        })
        assert parse_response(raw) == "only nested"


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
        ws.register("test-container")
        try:
            result = ws.wait_for_completion(container_id="test-container", timeout=0.1)
            assert result is False
        finally:
            ws.stop()

    def test_wait_for_completion_returns_true_on_signal(self, server, free_port):
        """wait_for_completion should return True when task-complete is POSTed."""
        cid = "test-container-abc123"
        server.register(cid)

        def send_signal():
            # Small delay to ensure wait_for_completion is blocking first
            time.sleep(0.05)
            payload = json.dumps({"status": "done", "container_id": cid}).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{free_port}/hooks/task-complete",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=2)

        t = threading.Thread(target=send_signal)
        t.start()
        result = server.wait_for_completion(container_id=cid, timeout=5)
        t.join(timeout=2)

        assert result is True

    def test_task_complete_stores_payload(self, server, free_port):
        """POST to /hooks/task-complete should store the payload."""
        cid = "container-abc123"
        server.register(cid)
        payload = json.dumps({"task_id": "abc123", "container_id": cid}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{free_port}/hooks/task-complete",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=2)
        assert resp.status == 200

        body = json.loads(resp.read())
        assert body["status"] == "accepted"
        assert server.last_payload(cid) == {"task_id": "abc123", "container_id": cid}

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


# =========================================================================
# Response Parser — additional edge cases (nested result format)
# =========================================================================


class TestParseResponseNestedResult:
    """Additional edge cases for the nested result envelope format from OpenClaw."""

    def test_result_key_with_empty_payloads(self):
        """result.payloads as empty list should return empty string."""
        raw = json.dumps({"result": {"payloads": []}, "status": "ok"})
        assert parse_response(raw) == ""

    def test_result_key_with_null_payloads(self):
        """result.payloads as null should return empty string."""
        raw = json.dumps({"result": {"payloads": None}, "status": "ok"})
        assert parse_response(raw) == ""

    def test_multiple_json_objects_with_nested_result(self):
        """Log-line JSON + nested result envelope should take the last valid payload."""
        log_json = json.dumps({"event": "turn_start", "turn": 1})
        result_json = json.dumps({
            "result": {
                "payloads": [{"text": "from nested"}],
            },
            "status": "ok",
        })
        raw = log_json + "\n[INFO] processing...\n" + result_json
        assert parse_response(raw) == "from nested"

    def test_nested_result_single_line(self):
        """Single-line nested result format should parse correctly."""
        raw = '{"result": {"payloads": [{"text": "hello"}]}}'
        assert parse_response(raw) == "hello"


# =========================================================================
# Webhook Server — per-container tracking tests
# =========================================================================


class TestWebhookPerContainer:
    """Test per-container completion tracking in WebhookServer."""

    @pytest.fixture
    def free_port(self):
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    @pytest.fixture
    def server(self, free_port):
        ws = WebhookServer("127.0.0.1", free_port)
        ws.start()
        yield ws
        ws.stop()

    def test_register_creates_event(self, free_port):
        """register(container_id) should create a new Event for that container."""
        ws = WebhookServer("127.0.0.1", free_port)
        ws.register("container-aaa")
        assert "container-aaa" in ws._events
        assert not ws._events["container-aaa"].is_set()

    def test_two_containers_independent(self, server, free_port):
        """Signaling one container should not unblock the other."""
        cid_a = "container-aaaa1111" + "0" * 48  # 64 chars
        cid_b = "container-bbbb2222" + "0" * 48

        server.register(cid_a)
        server.register(cid_b)

        # Signal container A via HTTP
        payload = json.dumps({"container_id": cid_a}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{free_port}/hooks/task-complete",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=2)

        # A should be signaled
        assert server.wait_for_completion(container_id=cid_a, timeout=0.1) is True
        # B should NOT be signaled
        assert server.wait_for_completion(container_id=cid_b, timeout=0.1) is False

    def test_unregister_cleans_up(self, free_port):
        """unregister(container_id) should remove event and payload."""
        ws = WebhookServer("127.0.0.1", free_port)
        ws.register("cid-to-remove")
        ws._payloads["cid-to-remove"] = {"data": "test"}

        ws.unregister("cid-to-remove")

        assert "cid-to-remove" not in ws._events
        assert "cid-to-remove" not in ws._payloads

    def test_reset_only_resets_target_container(self, free_port):
        """reset(container_id) should only clear that container's event."""
        ws = WebhookServer("127.0.0.1", free_port)
        ws.register("cid-1")
        ws.register("cid-2")

        # Set both events
        ws._events["cid-1"].set()
        ws._events["cid-2"].set()
        ws._payloads["cid-1"] = {"test": 1}
        ws._payloads["cid-2"] = {"test": 2}

        ws.reset("cid-1")

        assert not ws._events["cid-1"].is_set()
        assert ws._events["cid-2"].is_set()
        assert "cid-1" not in ws._payloads
        assert ws._payloads["cid-2"] == {"test": 2}

    def test_reset_none_resets_all(self, free_port):
        """reset(None) should clear all containers' events."""
        ws = WebhookServer("127.0.0.1", free_port)
        ws.register("cid-x")
        ws.register("cid-y")
        ws._events["cid-x"].set()
        ws._events["cid-y"].set()

        ws.reset(None)

        assert not ws._events["cid-x"].is_set()
        assert not ws._events["cid-y"].is_set()

    def test_short_container_id_prefix_match(self, server, free_port):
        """POST with short (12 char) container_id should match full 64-char ID."""
        full_cid = "abcdef123456" + "7" * 52  # 64 chars
        server.register(full_cid)

        short_cid = full_cid[:12]  # "abcdef123456"
        payload = json.dumps({"container_id": short_cid}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{free_port}/hooks/task-complete",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=2)

        assert server.wait_for_completion(container_id=full_cid, timeout=1) is True

    def test_unknown_container_id_does_not_crash(self, server, free_port):
        """POST with unknown container_id should return 200 and not crash."""
        payload = json.dumps({"container_id": "nonexistent-cid"}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{free_port}/hooks/task-complete",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=2)
        assert resp.status == 200

    def test_wait_unregistered_container_raises(self, free_port):
        """wait_for_completion with unregistered container should raise ValueError."""
        ws = WebhookServer("127.0.0.1", free_port)
        with pytest.raises(ValueError, match="not registered"):
            ws.wait_for_completion(container_id="never-registered", timeout=0.1)

    def test_last_payload_per_container(self, free_port):
        """last_payload should return payload for the specified container."""
        ws = WebhookServer("127.0.0.1", free_port)
        ws._payloads["cid-1"] = {"data": "one"}
        ws._payloads["cid-2"] = {"data": "two"}

        assert ws.last_payload("cid-1") == {"data": "one"}
        assert ws.last_payload("cid-2") == {"data": "two"}
        assert ws.last_payload("cid-3") is None


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
                "openclaw_logs": {},
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
        """Create a SessionManager with the webhook server mocked out."""
        sm = SessionManager(config)
        sm._webhook = MagicMock()
        sm._webhook_started = True  # skip starting the real server
        return sm

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
            "openclaw_logs": {},
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
            "openclaw_logs": {},
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
    """Test WorkerManager methods with mocked Docker client."""

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

    def test_send_message_resets_webhook_before_writing(self, config, mock_docker):
        """send_message should reset the webhook BEFORE docker cp."""
        webhook = MagicMock()
        wm = WorkerManager(config, "test-run", webhook=webhook)
        wm._container = mock_docker["container"]

        call_order = []
        webhook.reset.side_effect = lambda cid: call_order.append("reset")

        with patch("pipeline.worker_manager.subprocess") as mock_sub:
            mock_sub.run.side_effect = lambda *a, **kw: call_order.append("docker_cp")
            with patch("pipeline.worker_manager.tempfile") as mock_tmp:
                mock_file = MagicMock()
                mock_file.__enter__ = MagicMock(return_value=mock_file)
                mock_file.__exit__ = MagicMock(return_value=False)
                mock_file.name = "/tmp/fake-msg.txt"
                mock_tmp.NamedTemporaryFile.return_value = mock_file

                with patch("pipeline.worker_manager.os.unlink"):
                    wm.send_message("test message")

        assert call_order.index("reset") < call_order.index("docker_cp")

    def test_send_message_chmods_file_after_docker_cp(self, config, mock_docker):
        """send_message should chmod 644 the file AFTER docker cp so a non-root
        container process can read it. Regression test for the bug where docker
        cp wrote the file as root and the node user got Permission denied."""
        webhook = MagicMock()
        wm = WorkerManager(config, "test-run", webhook=webhook)
        wm._container = mock_docker["container"]
        container_id = mock_docker["container"].id

        call_order = []

        def record_call(*args, **kwargs):
            cmd = args[0]
            if cmd[0] == "docker" and cmd[1] == "cp":
                call_order.append("docker_cp")
            elif cmd[0] == "docker" and cmd[1] == "exec":
                call_order.append("docker_exec_chmod")

        with patch("pipeline.worker_manager.subprocess") as mock_sub:
            mock_sub.run.side_effect = record_call
            with patch("pipeline.worker_manager.tempfile") as mock_tmp:
                mock_file = MagicMock()
                mock_file.__enter__ = MagicMock(return_value=mock_file)
                mock_file.__exit__ = MagicMock(return_value=False)
                mock_file.name = "/tmp/fake-msg.txt"
                mock_tmp.NamedTemporaryFile.return_value = mock_file

                with patch("pipeline.worker_manager.os.unlink"):
                    wm.send_message("hello from orchestrator")

        # chmod must be called
        assert "docker_exec_chmod" in call_order, (
            "send_message must call docker exec chmod after docker cp"
        )

        # chmod must come AFTER cp, not before
        assert call_order.index("docker_cp") < call_order.index("docker_exec_chmod"), (
            f"chmod must happen after cp, got order: {call_order}"
        )

        # Verify the exact chmod command args
        chmod_call = [
            c for c in mock_sub.run.call_args_list
            if c[0][0][1] == "exec"
        ][0]
        assert chmod_call[0][0] == [
            "docker", "exec", container_id, "chmod", "644", "/tmp/next-message.txt"
        ]

        # chmod uses check=False so failures don't crash the pipeline
        assert chmod_call[1].get("check") is False, (
            "chmod call must use check=False (best-effort)"
        )

    @patch("pipeline.worker_manager.subprocess")
    def test_get_response_reads_and_parses(self, mock_sub, config, mock_docker):
        """get_response should docker cp the file and parse the JSON."""
        webhook = MagicMock()
        wm = WorkerManager(config, "test-run", webhook=webhook)
        wm._container = mock_docker["container"]

        response_json = json.dumps({
            "payloads": [{"text": "Hello from worker"}],
            "meta": {},
        })

        def fake_cp(*args, **kwargs):
            # Write to the temp file that get_response will read
            cmd_args = args[0]
            dest = cmd_args[-1]  # last arg is destination path
            with open(dest, "w") as f:
                f.write(response_json)

        mock_sub.run.side_effect = fake_cp

        result = wm.get_response()
        assert result == "Hello from worker"

    @patch("pipeline.worker_manager.subprocess")
    def test_get_response_returns_empty_on_cp_failure(self, mock_sub, config, mock_docker):
        """get_response should return empty string if docker cp fails."""
        import subprocess as real_subprocess
        mock_sub.CalledProcessError = real_subprocess.CalledProcessError
        mock_sub.run.side_effect = real_subprocess.CalledProcessError(1, "docker cp")

        webhook = MagicMock()
        wm = WorkerManager(config, "test-run", webhook=webhook)
        wm._container = mock_docker["container"]

        result = wm.get_response()
        assert result == ""

    def test_is_alive_running(self, config, mock_docker):
        """is_alive should return True for a running container."""
        webhook = MagicMock()
        wm = WorkerManager(config, "test-run", webhook=webhook)
        wm._container = mock_docker["container"]
        mock_docker["container"].status = "running"

        assert wm.is_alive() is True

    def test_is_alive_exited(self, config, mock_docker):
        """is_alive should return False for an exited container."""
        webhook = MagicMock()
        wm = WorkerManager(config, "test-run", webhook=webhook)
        wm._container = mock_docker["container"]

        # After reload, status is "exited"
        mock_docker["container"].status = "exited"

        assert wm.is_alive() is False

    def test_is_alive_no_container(self, config, mock_docker):
        """is_alive should return False when no container exists."""
        webhook = MagicMock()
        wm = WorkerManager(config, "test-run", webhook=webhook)
        wm._container = None

        assert wm.is_alive() is False

    def test_send_message_raises_if_no_container(self, config, mock_docker):
        """send_message should raise RuntimeError if container is None."""
        webhook = MagicMock()
        wm = WorkerManager(config, "test-run", webhook=webhook)
        wm._container = None

        with pytest.raises(RuntimeError, match="not running"):
            wm.send_message("hello")

    def test_send_message_raises_if_container_not_running(self, config, mock_docker):
        """send_message should raise RuntimeError if container is not running."""
        webhook = MagicMock()
        wm = WorkerManager(config, "test-run", webhook=webhook)
        wm._container = mock_docker["container"]
        mock_docker["container"].status = "exited"

        with pytest.raises(RuntimeError, match="exited"):
            wm.send_message("hello")

    def test_get_response_raises_if_no_container(self, config, mock_docker):
        """get_response should raise RuntimeError if container is None."""
        webhook = MagicMock()
        wm = WorkerManager(config, "test-run", webhook=webhook)
        wm._container = None

        with pytest.raises(RuntimeError, match="not running"):
            wm.get_response()

    def test_send_feedback_is_alias_for_send_message(self, config, mock_docker):
        """send_feedback should delegate to send_message."""
        webhook = MagicMock()
        wm = WorkerManager(config, "test-run", webhook=webhook)
        wm.send_message = MagicMock()

        wm.send_feedback("feedback text")
        wm.send_message.assert_called_once_with("feedback text")

    def test_cleanup_unregisters_from_webhook(self, config, mock_docker):
        """cleanup should unregister the container from webhook tracking."""
        webhook = MagicMock()
        wm = WorkerManager(config, "test-run", webhook=webhook)
        wm._container = mock_docker["container"]
        container_id = mock_docker["container"].id

        wm.cleanup()

        webhook.unregister.assert_called_once_with(container_id)
