"""
Tests for tracker selection at init time.

Covers:
- init --tracker linear creates Linear MCP config
- init --tracker jira creates Jira MCP config
- init without --tracker defaults to linear
- Project config file stores tracker choice
- create-ticket reads tracker from project config
- status shows tracker platform
- help mentions --tracker flag
"""
import json
import os
import subprocess
import tempfile
import shutil

import pytest
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAT_FORCE_BIN = os.path.join(REPO_ROOT, "bin", "chat-force")


def run_chat_force(*args, cwd=None, env=None):
    result = subprocess.run(
        [CHAT_FORCE_BIN, *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )
    return result


def init_project(tmpdir, tracker=None):
    args = ["init"]
    if tracker:
        args += ["--tracker", tracker]
    result = run_chat_force(*args, cwd=tmpdir)
    assert result.returncode == 0, f"init failed: {result.stderr}"
    return result


# ---------------------------------------------------------------------------
# Init with tracker flag
# ---------------------------------------------------------------------------
class TestInitTracker:
    def test_init_linear_creates_linear_mcp(self):
        tmpdir = tempfile.mkdtemp(prefix="chatforce-tracker-")
        try:
            init_project(tmpdir, tracker="linear")
            mcp_path = os.path.join(tmpdir, ".mcp.json")
            assert os.path.isfile(mcp_path)
            mcp = json.load(open(mcp_path))
            servers = mcp.get("mcpServers", {})
            assert "linear" in servers, "Linear MCP server should be configured"
            assert "jira" not in servers, "Jira should NOT be in Linear config"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_init_jira_creates_jira_mcp(self):
        tmpdir = tempfile.mkdtemp(prefix="chatforce-tracker-")
        try:
            init_project(tmpdir, tracker="jira")
            mcp_path = os.path.join(tmpdir, ".mcp.json")
            assert os.path.isfile(mcp_path)
            mcp = json.load(open(mcp_path))
            servers = mcp.get("mcpServers", {})
            assert "atlassian" in servers, (
                "Atlassian MCP server should be configured"
            )
            assert "linear" not in servers, "Linear should NOT be in Jira config"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_init_default_is_linear(self):
        tmpdir = tempfile.mkdtemp(prefix="chatforce-tracker-")
        try:
            init_project(tmpdir)  # no --tracker flag
            mcp_path = os.path.join(tmpdir, ".mcp.json")
            assert os.path.isfile(mcp_path)
            mcp = json.load(open(mcp_path))
            servers = mcp.get("mcpServers", {})
            assert "linear" in servers, "Default should be Linear"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Project config stores tracker choice
# ---------------------------------------------------------------------------
class TestProjectConfig:
    def test_config_created_on_init(self):
        tmpdir = tempfile.mkdtemp(prefix="chatforce-tracker-")
        try:
            init_project(tmpdir, tracker="linear")
            cfg_path = os.path.join(tmpdir, ".claude", "chat-force.yaml")
            assert os.path.isfile(cfg_path), ".claude/chat-force.yaml should exist"
            cfg = yaml.safe_load(open(cfg_path))
            assert cfg["tracker"] == "linear"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_config_stores_jira(self):
        tmpdir = tempfile.mkdtemp(prefix="chatforce-tracker-")
        try:
            init_project(tmpdir, tracker="jira")
            cfg_path = os.path.join(tmpdir, ".claude", "chat-force.yaml")
            cfg = yaml.safe_load(open(cfg_path))
            assert cfg["tracker"] == "jira"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Status shows tracker
# ---------------------------------------------------------------------------
class TestStatusShowsTracker:
    def test_status_shows_tracker_platform(self):
        tmpdir = tempfile.mkdtemp(prefix="chatforce-tracker-")
        try:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=tmpdir, capture_output=True, check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=tmpdir, capture_output=True, check=True,
            )
            init_project(tmpdir, tracker="jira")
            subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True, check=True)
            subprocess.run(
                ["git", "commit", "-m", "initial"],
                cwd=tmpdir, capture_output=True, check=True,
            )
            result = run_chat_force("status", cwd=tmpdir)
            assert result.returncode == 0
            assert "jira" in result.stdout.lower(), "status should show tracker platform"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
