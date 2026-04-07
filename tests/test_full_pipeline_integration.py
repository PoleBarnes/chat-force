"""Full pipeline integration test (Tier 5).

Runs pipeline.main.run_pipeline() end-to-end with ALL real components:
  - Real Docker Worker image + real container
  - Real Agent SDK subprocess
  - Real Claude API call (Worker + Mechanic)
  - Real git clone/push
  - Real GitHub PR creation via gh CLI

The test creates a throwaway PR and immediately closes + deletes the
branch to avoid polluting the repo. This is the ultimate smoke test.

SLOW (~2-3 minutes) and costs ~$0.10-0.30 per run. Gated on:
  - Docker daemon
  - ANTHROPIC_API_KEY
  - GITHUB_TOKEN

Run with:
    doppler run --project chat-force --config dev -- \\
        uv run --python 3.13 --with docker,"slack_sdk>=3.41.0","slack_bolt>=1.27.0",claude-agent-sdk,pytest \\
        pytest tests/test_full_pipeline_integration.py -v -s
"""

import os
import subprocess
import time
import pytest

import docker as docker_mod
from docker.errors import DockerException

from pipeline.config import PipelineConfig
from pipeline.main import run_pipeline


def _docker_available() -> bool:
    try:
        docker_mod.from_env().ping()
        return True
    except (DockerException, Exception):
        return False


def _tokens_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and bool(os.environ.get("GITHUB_TOKEN"))


pytestmark = [
    pytest.mark.skipif(not _docker_available(), reason="Docker daemon not available"),
    pytest.mark.skipif(not _tokens_available(), reason="ANTHROPIC_API_KEY or GITHUB_TOKEN not set"),
    pytest.mark.slow,
]


def _close_pr_if_exists(pr_url: str) -> None:
    """Best-effort cleanup: close the PR and delete its branch."""
    if not pr_url:
        return
    # pr_url looks like https://github.com/PoleBarnes/chat-force/pull/N
    try:
        pr_num = pr_url.rstrip("/").split("/")[-1]
        subprocess.run(
            ["gh", "pr", "close", pr_num, "--repo", "PoleBarnes/chat-force", "--delete-branch",
             "--comment", "Automated integration test cleanup."],
            capture_output=True,
            timeout=30,
        )
    except Exception:
        pass


def test_full_pipeline_creates_pr(tmp_path):
    """run_pipeline() should produce a PR end-to-end.

    This is the ultimate smoke test: every component runs for real.
    If this test passes, the whole system works.
    """
    config = PipelineConfig(output_base=str(tmp_path))

    # Use a unique file name so repeated runs don't conflict
    marker = f"integration-test-{int(time.time())}"
    task = (
        f"Create a file at PIPELINE-TEST-{marker}.md in the repo root "
        f"with exactly this content: 'Full pipeline integration test {marker}'. "
        "Keep it minimal. Do not create other files."
    )

    result = run_pipeline(task, config)

    pr_url = result.get("pr_url")

    try:
        # Hard assertions
        assert result["status"] == "approved", (
            f"Pipeline did not approve. status={result['status']}, "
            f"verdict={result.get('verdict')}, error={result.get('error')}"
        )
        assert pr_url, f"No PR URL in result: {result}"
        assert "github.com" in pr_url
        assert "/pull/" in pr_url

        # The Mechanic's verdict should have structured data
        verdict = result.get("verdict", {})
        assert verdict.get("verdict") == "approve" or verdict.get("approved") is True
        assert "pr_title" in verdict
        assert "files_to_include" in verdict

        # Iterations should be 1 (approved on first try for a trivial task)
        assert result["iterations"] == 1

    finally:
        # Always clean up the test PR
        _close_pr_if_exists(pr_url)
