"""
Tests for tracker selection at init time.
"""
import json
import os
import subprocess
import tempfile
import shutil

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_chat_force(*args, cwd=None, env=None):
    base_env = os.environ.copy()
    base_env["PYTHONPATH"] = REPO_ROOT
    if env:
        base_env.update(env)
    return subprocess.run(
        ["python3", "-m", "chat_force.cli", *args],
        capture_output=True, text=True, cwd=cwd, env=base_env,
    )


def init_project(tmpdir, tracker=None, stdin=None):
    args = ["init"]
    if tracker:
        args += ["--tracker", tracker]
    base_env = os.environ.copy()
    base_env["PYTHONPATH"] = REPO_ROOT
    result = subprocess.run(
        ["python3", "-m", "chat_force.cli", *args],
        capture_output=True, text=True, cwd=tmpdir, env=base_env,
        input=stdin,
    )
    assert result.returncode == 0, f"init failed: {result.stderr}"
    return result


class TestInitTracker:
    def test_init_linear_creates_linear_mcp(self):
        tmpdir = tempfile.mkdtemp(prefix="chatforce-tracker-")
        try:
            init_project(tmpdir, tracker="linear")
            mcp = json.loads(open(os.path.join(tmpdir, ".mcp.json")).read())
            servers = mcp.get("mcpServers", {})
            assert "linear" in servers
            assert "atlassian" not in servers
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_init_jira_creates_jira_mcp(self):
        tmpdir = tempfile.mkdtemp(prefix="chatforce-tracker-")
        try:
            init_project(tmpdir, tracker="jira")
            mcp = json.loads(open(os.path.join(tmpdir, ".mcp.json")).read())
            servers = mcp.get("mcpServers", {})
            assert "atlassian" in servers
            assert "linear" not in servers
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_init_prompts_when_no_tracker_flag(self):
        """init without --tracker should prompt; selecting 1 gives Linear."""
        tmpdir = tempfile.mkdtemp(prefix="chatforce-tracker-")
        try:
            init_project(tmpdir, stdin="1\n")
            mcp = json.loads(open(os.path.join(tmpdir, ".mcp.json")).read())
            assert "linear" in mcp.get("mcpServers", {})
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestProjectConfig:
    def test_config_created_on_init(self):
        tmpdir = tempfile.mkdtemp(prefix="chatforce-tracker-")
        try:
            init_project(tmpdir, tracker="linear")
            cfg = json.loads(open(os.path.join(tmpdir, ".claude", "chat-force.json")).read())
            assert cfg["tracker"] == "linear"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_config_stores_jira(self):
        tmpdir = tempfile.mkdtemp(prefix="chatforce-tracker-")
        try:
            init_project(tmpdir, tracker="jira")
            cfg = json.loads(open(os.path.join(tmpdir, ".claude", "chat-force.json")).read())
            assert cfg["tracker"] == "jira"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestStatusShowsTracker:
    def test_status_shows_tracker_platform(self):
        tmpdir = tempfile.mkdtemp(prefix="chatforce-tracker-")
        try:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, check=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"],
                           cwd=tmpdir, capture_output=True, check=True)
            subprocess.run(["git", "config", "user.name", "Test"],
                           cwd=tmpdir, capture_output=True, check=True)
            init_project(tmpdir, tracker="jira")
            subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True, check=True)
            subprocess.run(["git", "commit", "-m", "initial"],
                           cwd=tmpdir, capture_output=True, check=True)
            result = run_chat_force("status", cwd=tmpdir)
            assert result.returncode == 0
            assert "jira" in result.stdout.lower()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
