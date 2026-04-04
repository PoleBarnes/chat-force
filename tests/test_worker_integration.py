"""Real-Worker integration tests (Tier 3b).

These tests spin up the REAL Worker Docker image with the REAL Claude
Agent SDK and verify the full Worker lifecycle. They catch bugs at the
boundary between our Python code and:
  - The Docker daemon
  - The claude-agent-sdk Python package
  - The bundled Claude CLI subprocess

Tests are SLOW (20-60 seconds each) and require:
  - Docker daemon running
  - ANTHROPIC_API_KEY environment variable set (via `doppler run`)
  - The worker/Dockerfile image buildable

Run with:
    doppler run --project chat-force --config dev -- \\
        uv run --python 3.13 --with docker,"slack_sdk>=3.41.0","slack_bolt>=1.27.0",claude-agent-sdk,pytest \\
        pytest tests/test_worker_integration.py -v -s

These tests are gated on ANTHROPIC_API_KEY so they skip automatically
in environments without the token.
"""

import json
import os
import time
import pytest

import docker as docker_mod
from docker.errors import DockerException

from pipeline.config import PipelineConfig
from pipeline.worker_manager import WorkerManager
from pipeline.changeset_extractor import ChangesetExtractor


def _docker_available() -> bool:
    try:
        docker_mod.from_env().ping()
        return True
    except (DockerException, Exception):
        return False


def _token_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


pytestmark = [
    pytest.mark.skipif(not _docker_available(), reason="Docker daemon not available"),
    pytest.mark.skipif(not _token_available(), reason="ANTHROPIC_API_KEY not set"),
    pytest.mark.slow,
]


@pytest.fixture(scope="module")
def worker_image():
    """Ensure the worker image is built. Reused across all tests in this module."""
    client = docker_mod.from_env()
    config = PipelineConfig()

    # Use WorkerManager's smart image ensure logic.
    wm = WorkerManager(config, "image-build")
    wm._ensure_network()
    wm._ensure_image()

    return config.worker_image


@pytest.fixture
def worker(worker_image, tmp_path):
    """Start a fresh Worker container with a deterministic task."""
    config = PipelineConfig(output_base=str(tmp_path))
    wm = WorkerManager(config, f"test-{int(time.time())}")

    task = (
        "Create a file at /workspace/config/test-output.txt with exactly "
        "this content: 'integration test marker'. Do not create any other "
        "files. Do not modify any other files. Just the one file."
    )
    wm.start(task)

    try:
        wm.wait_for_completion()
        yield wm
    finally:
        try:
            wm.cleanup()
        except Exception:
            pass


# =========================================================================
# Worker lifecycle tests
# =========================================================================


def test_worker_completes_simple_task(worker):
    """Worker should complete a simple file-creation task."""
    # Sentinel detection is the completion signal — if we got here, it worked.
    response = worker.get_response()
    assert response, "Worker did not write a response"
    # The response should mention the task or file.
    assert len(response) > 0


def test_worker_tool_log_is_parseable(worker):
    """get_tool_log() should return parsed JSONL entries from the real container."""
    tool_log = worker.get_tool_log()
    assert isinstance(tool_log, list)
    assert len(tool_log) > 0, "Tool log should have at least one entry"

    # Every entry should have the fields our hooks write.
    for entry in tool_log:
        assert "event" in entry
        assert entry["event"] in ("PreToolUse", "PostToolUse")
        assert "tool_name" in entry
        assert "timestamp" in entry

    # The Worker should have used the Write tool.
    tool_names = {e["tool_name"] for e in tool_log}
    assert "Write" in tool_names, f"Expected Write tool usage, got: {tool_names}"


def test_worker_usage_is_parseable(worker):
    """get_usage() should return parsed token/cost data."""
    usage = worker.get_usage()
    assert isinstance(usage, dict)
    assert "input_tokens" in usage
    assert "output_tokens" in usage
    assert usage["input_tokens"] > 0
    assert usage["output_tokens"] > 0


def test_worker_no_crash_error(worker):
    """get_error() should return None when the Worker completed normally."""
    error = worker.get_error()
    assert error is None, f"Unexpected worker error: {error}"


def test_worker_multi_turn_follow_up(worker_image, tmp_path):
    """REGRESSION: send_message() must work against the real Worker container.

    This is the test that would have caught the non-root chmod bug we hit
    in live Slack testing. It exercises the full multi-turn flow:
      1. Worker processes the initial TASK_INSTRUCTION (first turn)
      2. Orchestrator sends a follow-up via send_message()
      3. Worker reads /tmp/next-message.txt and processes it (second turn)
      4. wait_for_completion() detects the new sentinel
      5. get_response() returns the second turn's response
    """
    config = PipelineConfig(output_base=str(tmp_path))
    wm = WorkerManager(config, f"multiturn-{int(time.time())}")

    initial_task = "Reply with exactly: FIRST_TURN_DONE. Do not create any files."
    wm.start(initial_task)

    try:
        wm.wait_for_completion()
        first_response = wm.get_response()
        assert "FIRST_TURN_DONE" in first_response, (
            f"First turn failed: {first_response!r}"
        )

        # Now send a follow-up message — this exercises send_message()
        # which writes /tmp/next-message.txt via docker cp.
        wm.send_message(
            "Reply with exactly: SECOND_TURN_DONE. Do not create any files."
        )
        wm.wait_for_completion()

        second_response = wm.get_response()
        assert "SECOND_TURN_DONE" in second_response, (
            f"Second turn failed (likely permission/sentinel bug): "
            f"{second_response!r}"
        )

        # Verify no error from the Worker entrypoint.
        assert wm.get_error() is None

    finally:
        try:
            wm.cleanup()
        except Exception:
            pass


def test_changeset_extraction_from_real_container(worker):
    """ChangesetExtractor.extract() should capture real file changes.

    Verifies the extractor works against a real container with real
    git diffs, real docker diffs, and real agent artifacts.
    """
    config = PipelineConfig(output_base=worker.config.output_base)
    extractor = ChangesetExtractor(config, worker.run_id)

    bundle = extractor.extract(
        worker._container.id,
        task="test task",
    )

    # Basic structure
    assert bundle["run_id"] == worker.run_id
    assert bundle["worker_container"] == worker._container.id

    # Git changes should reflect the file the worker created
    git = bundle["git_changes"]
    assert isinstance(git, dict)
    # The worker was told to create test-output.txt — verify it shows up
    # in new_files or file_contents.
    new_files = git.get("new_files", [])
    file_contents = git.get("file_contents", {})
    found_it = any("test-output.txt" in f for f in new_files) or any(
        "test-output.txt" in k for k in file_contents
    )
    assert found_it, (
        f"Expected test-output.txt in git_changes; "
        f"new_files={new_files}, file_contents keys={list(file_contents.keys())[:10]}"
    )

    # Tool log and usage should be parsed into the bundle (not just file paths)
    assert "tool_log" in bundle
    assert isinstance(bundle["tool_log"], list)
    assert len(bundle["tool_log"]) > 0

    assert "usage" in bundle
    assert isinstance(bundle["usage"], dict)
    assert bundle["usage"].get("input_tokens", 0) > 0
